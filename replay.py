import sys
import json
import chess


def board_to_ascii(board: chess.Board) -> str:
    lines = ["  a b c d e f g h"]
    for rank in range(7, -1, -1):
        row = [str(rank + 1)]
        for file in range(8):
            piece = board.piece_at(chess.square(file, rank))
            row.append(piece.symbol() if piece else ".")
        lines.append(" ".join(row))
    return "\n".join(lines)


def square_name(sq):
    if sq is None:
        return "—"
    return chess.square_name(sq)


def unwrap(x, key="value"):
    """JSON entries may be raw values or {'value': ...} dicts depending on reconchess version."""
    if isinstance(x, dict):
        return x.get(key) if key in x else x.get("square")
    return x


def main(path: str):
    with open(path) as f:
        data = json.load(f)

    senses = data.get("senses", {"true": [], "false": []})
    requested = data.get("requested_moves", {"true": [], "false": []})
    taken = data.get("taken_moves", {"true": [], "false": []})
    fens_before = data.get("fens_before_move", {"true": [], "false": []})
    fens_after = data.get("fens_after_move", {"true": [], "false": []})
    winner = data.get("winner_color")
    win_reason = data.get("win_reason")

    white_turns = max(len(senses["true"]), len(taken["true"]))
    black_turns = max(len(senses["false"]), len(taken["false"]))
    total = white_turns + black_turns

    turn_no = 0
    for i in range(max(white_turns, black_turns)):
        for color_key, color_label in [("true", "WHITE"), ("false", "BLACK")]:
            if i >= len(senses[color_key]) and i >= len(taken[color_key]):
                continue
            turn_no += 1
            print("=" * 60)
            print(f"Turn {turn_no} — {color_label}")
            print("=" * 60)

            if i < len(fens_before[color_key]):
                fen = unwrap(fens_before[color_key][i])
                if fen:
                    board = chess.Board(fen)
                    print("Board before:")
                    print(board_to_ascii(board))

            if i < len(senses[color_key]):
                sense_sq = unwrap(senses[color_key][i], "square")
                print(f"Sensed at: {square_name(sense_sq)}")

            if i < len(requested[color_key]) and i < len(taken[color_key]):
                req_uci = unwrap(requested[color_key][i])
                tk_uci = unwrap(taken[color_key][i])
                print(f"Requested move: {req_uci}   Taken move: {tk_uci}")

            input("[enter for next turn]")

    print("=" * 60)
    print(f"Winner: {'WHITE' if winner else 'BLACK'}   Reason: {win_reason}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 replay.py <history.json>")
        sys.exit(1)
    main(sys.argv[1])
