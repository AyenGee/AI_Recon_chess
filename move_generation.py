import chess
import chess.engine

engine = chess.engine.SimpleEngine.popen_uci('./stockfish', setpgrp=True)

def get_move(fen_string: str) -> list:
    board = chess.Board(fen_string)

    enemy_king_square = board.king(not board.turn)
    if enemy_king_square is not None:

        enemy_king_attackers = board.attackers(board.turn, enemy_king_square)
        if enemy_king_attackers:
            attacker_square = enemy_king_attackers.pop()
            capture_move = chess.Move(attacker_square, enemy_king_square)
            return capture_move.uci()

    # otherwise, try to move with the stockfish chess engine
    try:
        with chess.engine.SimpleEngine.popen_uci("./stockfish") as engine:
            result = engine.play(board, chess.engine.Limit(time=0.5))
            return result.move.uci()
    except chess.engine.EngineTerminatedError:
        print('Stockfish Engine died')
    


if __name__ == "__main__":
    fen = input().strip()
    # target_square = input().strip()
    
    move = get_move(fen)
    
    print(move)



engine.quit()