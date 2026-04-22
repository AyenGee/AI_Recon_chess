import chess

def execute_move(fen_string: str, move_uci: str) -> str:

    board = chess.Board(fen_string)
    move = chess.Move.from_uci(move_uci)
    board.push(move)
    return board.fen()


if __name__ == "__main__":
    fen = input().strip()
    move = input().strip()
    result = execute_move(fen, move)
    print(result)