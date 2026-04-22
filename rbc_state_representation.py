import chess
 
def display_board_from_fen(fen_string: str) -> None:
    board = chess.Board(fen_string)
    
    for rank in range(7, -1, -1):
        line = []
        for file in range(8):
            square = chess.square(file, rank)
            piece = board.piece_at(square)
            line.append(piece.symbol() if piece else '.')
        print(' '.join(line))
 
 
if __name__ == "__main__":
    fen = input().strip()
    display_board_from_fen(fen)