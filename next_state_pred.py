#Parse FEN - Create board object with chess library
#Add null move - Start with ["0000"]
#Get legal moves - Loop through board.legal_moves
#Covert to UCI - Use move.uci() ("e2e4")
#Sort and Ouput - Alphabetical order

#It seems that the output does not care about moves that will
#put the king in check, therefore states for the check in the list as well
#board.legal_moves prints only the moves that will not result in a check 
#what we want is board.psuedo_legal_moves
import chess

def get_next_moves(fen_string):
    board = chess.Board(fen_string)
    
    # Start with null move
    moves = set()
    moves.add("0000")
    
    # Get all pseudo-legal moves (ignores check)
    for move in board.pseudo_legal_moves:
        moves.add(move.uci())
    
    # Manually add castling moves (pseudo_legal_moves doesn't include them)
    if board.turn == chess.WHITE:
        # White kingside castling (e1g1)
        if board.has_kingside_castling_rights(chess.WHITE):
            if board.piece_at(chess.F1) is None and board.piece_at(chess.G1) is None:
                moves.add("e1g1")
        
        # White queenside castling (e1c1)
        if board.has_queenside_castling_rights(chess.WHITE):
            if (board.piece_at(chess.D1) is None and 
                board.piece_at(chess.C1) is None and 
                board.piece_at(chess.B1) is None):
                moves.add("e1c1")
    
    else:  # Black's turn
        # Black kingside castling (e8g8)
        if board.has_kingside_castling_rights(chess.BLACK):
            if board.piece_at(chess.F8) is None and board.piece_at(chess.G8) is None:
                moves.add("e8g8")
        
        # Black queenside castling (e8c8)
        if board.has_queenside_castling_rights(chess.BLACK):
            if (board.piece_at(chess.D8) is None and 
                board.piece_at(chess.C8) is None and 
                board.piece_at(chess.B8) is None):
                moves.add("e8c8")
    
    # Sort and return
    moves = sorted(moves)
    return "\n".join(moves)

def execute_move(fen_string: str, move_uci: str) -> str:

    board = chess.Board(fen_string)
    move = chess.Move.from_uci(move_uci)
    board.push(move)
    return board.fen()

if __name__ == "__main__":
    fen = input().strip()
    result = get_next_moves(fen)
    states = []
    for move in result.split("\n"):
        states.append(execute_move(fen, move))
    states.sort()
    print("\n".join(states))