import chess

def get_next_states_with_capture(fen_string: str, target_square: str) -> list:
    board = chess.Board(fen_string)
    
    # Convert square string to square index (e.g., "d6" -> square index)
    target_sq = chess.parse_square(target_square)
    
    states = []
    
    # Get all pseudo-legal moves
    for move in board.pseudo_legal_moves:
        if move.to_square == target_sq:
            # Execute the move
            new_board = board.copy()
            new_board.push(move)
            # Add resulting FEN to list
            states.append(new_board.fen())
        
    # Sort alphabetically and return
    states.sort()
    return states


if __name__ == "__main__":
    fen = input().strip()
    target_square = input().strip()
    
    states = get_next_states_with_capture(fen, target_square)
    
    for state in states:
        print(state)