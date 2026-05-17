import chess
import chess.engine
import random
import os
from collections import Counter
from reconchess import *

STOCKFISH_ENV_VAR = "STOCKFISH_EXECUTABLE"
MAX_STATES = 10000


class RandomSensing(Player):

    def __init__(self):
        if STOCKFISH_ENV_VAR not in os.environ:
            raise KeyError(
                f'Missing environment variable "{STOCKFISH_ENV_VAR}"'
            )

        stockfish_path = os.environ[STOCKFISH_ENV_VAR]

        if not os.path.exists(stockfish_path):
            raise ValueError(f"Stockfish not found at {stockfish_path}")

        self.engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
        self.color = None
        self.possible_boards = set()
        
        self._board_cache = {}
        
        self.move_count = 0

    def _get_board(self, fen):
        """Cached board creation to avoid repeated parsing"""
        if fen not in self._board_cache:
            self._board_cache[fen] = chess.Board(fen)
        return self._board_cache[fen]

    def handle_game_start(self, color, board, opponent_name):
        self.color = color
        self.move_count = 0
        
        self.possible_boards = {board.fen()}
        
        self._board_cache.clear()
        self._board_cache[board.fen()] = board

    def handle_opponent_move_result(self, captured_my_piece, capture_square):
        self._trim_states()
        new_states = set()

        for fen in self.possible_boards:
            board = self._get_board(fen)

            board.turn = not self.color

            for move in board.legal_moves:
                new_board = board.copy()

                is_capture = new_board.is_capture(move)

                if is_capture != captured_my_piece:
                    continue

                if captured_my_piece and move.to_square != capture_square:
                    continue

                new_board.push(move)
                new_states.add(new_board.fen())

        if new_states:
            self.possible_boards = new_states

        self._trim_states()

    def choose_sense(self, sense_actions, move_actions, seconds_left):
        filtered = [
            sq for sq in sense_actions
            if 0 < chess.square_file(sq) < 7
            and 0 < chess.square_rank(sq) < 7
        ]
        
        if not filtered:
            filtered = sense_actions

        return random.choice(filtered)

    def handle_sense_result(self, sense_result):
        filtered_states = set()

        for fen in self.possible_boards:
            board = self._get_board(fen)
            
            valid = True
            
            for square, piece in sense_result:
                if board.piece_at(square) != piece:
                    valid = False
                    break
                    
            if valid:
                filtered_states.add(fen)

        if filtered_states:
            self.possible_boards = filtered_states
        
        self._trim_states()

    def choose_move(self, move_actions, seconds_left):
        self.move_count += 1
        
        if not move_actions:
            return None

        self._trim_states()
        
        if len(move_actions) == 1:
            return move_actions[0]
        
        if self.move_count <= 3 and len(self.possible_boards) > 500:
            center_squares = {chess.E4, chess.D4, chess.E5, chess.D5}
            for move in move_actions:
                if move.to_square in center_squares:
                    return move
            return random.choice(move_actions)


        if len(self.possible_boards) > 1000:
            sample_size = min(500, max(50, len(move_actions) * 10))
            sampled_boards = random.sample(list(self.possible_boards), sample_size)
        else:
            sampled_boards = self.possible_boards

        move_votes = Counter()
        
        N = len(sampled_boards)
        time_per_board = 10.0 / max(N, 1)
        
        time_per_board = min(0.5, time_per_board)  # Max 0.5 seconds per board
        time_per_board = max(0.01, time_per_board)  # Min 0.01 seconds per board

        for fen in sampled_boards:
            board = self._get_board(fen)
            
            try:
                board.turn = self.color
                
                result = self.engine.play(
                    board,
                    chess.engine.Limit(time=time_per_board)
                )
                
                if result.move in move_actions:
                    move_votes[result.move] += 1
                    
            except (chess.engine.EngineError, TimeoutError, BrokenPipeError):
                continue

        if move_votes:
            return move_votes.most_common(1)[0][0]
        
        return random.choice(move_actions)

    def handle_move_result(
        self,
        requested_move,
        taken_move,
        captured_opponent_piece,
        capture_square
    ):
        if taken_move is None:
            return

        new_states = set()

        for fen in self.possible_boards:
            board = self._get_board(fen)
            
            board.turn = self.color
            
            if taken_move in board.legal_moves:
                move_is_capture = board.is_capture(taken_move)
                
                if move_is_capture != captured_opponent_piece:
                    continue
                    
                if captured_opponent_piece and taken_move.to_square != capture_square:
                    continue
                    
                board.push(taken_move)
                new_states.add(board.fen())

        if new_states:
            self.possible_boards = new_states
            
        self._trim_states()

    def handle_game_end(self, winner_color, win_reason, game_history):
        try:
            self.engine.quit()
        except (chess.engine.EngineTerminatedError, BrokenPipeError):
            pass
        
        self._board_cache.clear()

    def _trim_states(self):
        """Keep state count under MAX_STATES as required by lecturer"""
        if len(self.possible_boards) > MAX_STATES:
            self.possible_boards = set(
                random.sample(
                    list(self.possible_boards),
                    MAX_STATES
                )
            )