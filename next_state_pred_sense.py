import chess


def parse_window(window_str):
    window_dict = {}
    for square_piece in window_str.split(";"):
        square, piece = square_piece.split(":")
        window_dict[square] = piece
    return window_dict


def is_consistent_with_window(fen_string, window_dict):
    board = chess.Board(fen_string)
    
    for square_name, expected_piece in window_dict.items():
        # Convert square name to index
        sq_idx = chess.parse_square(square_name)
        
        # Get piece at that square
        piece_at_square = board.piece_at(sq_idx)
        
        # Check consistency
        if expected_piece == "?":
            # Window says empty, so square must be empty
            if piece_at_square is not None:
                return False
        else:
            # Window specifies exact piece, must match
            if piece_at_square is None:
                return False
            if piece_at_square.symbol() != expected_piece:
                return False
    
    return True


def filter_states_by_window(fen_list, window_str):

    window_dict = parse_window(window_str)
    
    # Filter consistent states
    consistent_states = []
    for fen in fen_list:
        if is_consistent_with_window(fen, window_dict):
            consistent_states.append(fen)
    
    consistent_states.sort()
    
    return consistent_states


if __name__ == "__main__":
    n = int(input().strip())
    
    fen_list = []
    for _ in range(n):
        fen = input().strip()
        fen_list.append(fen)
    
    window_str = input().strip()
    
    result = filter_states_by_window(fen_list, window_str)
    
    for fen in result:
        print(fen)