import chess
import chess.engine
import random
import os
from reconchess import *
from collections import Counter, defaultdict
from typing import List, Optional, Tuple, Set
import math

STOCKFISH_ENV_VAR = 'STOCKFISH_EXECUTABLE'
MAX_BELIEF_STATES = 50000  
MAX_SAMPLE = 500  
SENSE_SAMPLE = 100  
VERBOSITY = False  
NULL_MOVE = chess.Move.null()  

class Logger:
    """Simple logging utility"""
    def __init__(self, verbosity: bool):
        self.verbosity = verbosity
    
    def log(self, message: str):
        if self.verbosity:
            print(f"[LOG] {message}")
    
    def error(self, message: str):
        if self.verbosity:
            print(f"[ERROR] {message}")

logger = Logger(VERBOSITY)


class BoardUtils:
    """Utility functions for board management"""
    
    @staticmethod
    def fast_copy_board(board: chess.Board) -> chess.Board:
        new_board = object.__new__(chess.Board)
        
        new_board.pawns = board.pawns
        new_board.knights = board.knights
        new_board.bishops = board.bishops
        new_board.rooks = board.rooks
        new_board.queens = board.queens
        new_board.kings = board.kings
        
        new_board.occupied_co = [*board.occupied_co]
        new_board.occupied = board.occupied
        new_board.promoted = board.promoted
        
        new_board.chess960 = board.chess960
        
        new_board.ep_square = board.ep_square
        new_board.castling_rights = board.castling_rights
        new_board.turn = board.turn
        new_board.fullmove_number = board.fullmove_number
        new_board.halfmove_clock = board.halfmove_clock
        
        new_board.move_stack = []
        new_board._stack = []
        
        return new_board
    
    @staticmethod
    def is_valid_board_given_sense(board: chess.Board, sense_result: List[Tuple[Square, Optional[chess.Piece]]]) -> bool:
        """Check if board is consistent with sense result"""
        for square, piece in sense_result:
            if board.piece_at(square) != piece:
                return False
        return True
    
    @staticmethod
    def get_3x3_window(center: Square) -> List[Square]:
        """Get 3x3 window of squares around center"""
        file = chess.square_file(center)
        rank = chess.square_rank(center)
        return [chess.square(f, r) for r in range(rank - 1, rank + 2) for f in range(file - 1, file + 2)
                if 0 <= f < 8 and 0 <= r < 8]
    
    @staticmethod
    def is_not_edge_square(square: Square) -> bool:
        """Filter out edge squares (less informative)"""
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        return 0 < file < 7 and 0 < rank < 7
    
    @staticmethod
    def check_for_king_capture(board: chess.Board, color: Color) -> Optional[chess.Move]:
        """Check if king can be captured"""
        enemy_king_square = board.king(not color)
        if enemy_king_square:
            enemy_king_attackers = board.attackers(color, enemy_king_square)
            if enemy_king_attackers:
                attacker_square = enemy_king_attackers.pop()
                return chess.Move(attacker_square, enemy_king_square)
        return None
    
    @staticmethod
    def move_heuristic_value(board: chess.Board, move: chess.Move) -> float:
        """Heuristic score for move selection"""
        if move == NULL_MOVE:
            return -2.0
        
        score = 1.0
        
        if board.is_capture(move):
            score += 0.5
        
        if board.gives_check(move):
            score += 0.8
        
        piece = board.piece_at(move.from_square)
        if piece and piece.piece_type in {chess.BISHOP}:
            score += 0.1 * chess.square_distance(move.from_square, move.to_square)
        
        return score
    
    @staticmethod
    def generate_valid_moves(board: chess.Board) -> Set[chess.Move]:
        """Generate all valid moves for the board including castling"""
        possible_moves = {NULL_MOVE}
        for move in board.pseudo_legal_moves:
            possible_moves.add(move)
        
        for move in utilities.without_opponent_pieces(board).generate_castling_moves():
            if not utilities.is_illegal_castle(board, move):
                possible_moves.add(move)
        return possible_moves


class ImprovedAgent(Player):
    """
    Advanced ReconChess agent combining:
    1. Entropy-based sensing (information theory)
    2. Probabilistic board state filtering (Bayesian inference)
    3. Expected board elimination heuristic (loopyfish strategy)
    4. Robust board management with failure recovery
    5. Confidence-weighted move selection
    6. King capture and checkmate detection
    """
    
    def __init__(self):
        if STOCKFISH_ENV_VAR not in os.environ:
            raise KeyError(f'Missing environment variable "{STOCKFISH_ENV_VAR}"')
        
        stockfish_path = os.environ[STOCKFISH_ENV_VAR]
        if not os.path.exists(stockfish_path):
            raise ValueError(f"Stockfish not found at {stockfish_path}")
        
        self.engine = chess.engine.SimpleEngine.popen_uci(stockfish_path, setpgrp=True)
        self.color = None
        self.belief_states: List[chess.Board] = []
        self.fail_safe_board: Optional[chess.Board] = None
        self.move_count = 0
        self.opponent_name = ""
    
    def _ensure_engine_alive(self):
        """Check if engine is responsive; restart if needed"""
        try:
            self.engine.ping()
        except (chess.engine.EngineTerminatedError, Exception):
            logger.log("Engine died, restarting...")
            self._start_engine()
    
    def _start_engine(self):
        """Restart the Stockfish engine"""
        try:
            self.engine.quit()
        except:
            pass
        
        stockfish_path = os.environ[STOCKFISH_ENV_VAR]
        self.engine = chess.engine.SimpleEngine.popen_uci(stockfish_path, setpgrp=True)
    
    def handle_game_start(self, color: Color, board: chess.Board, opponent_name: str):
        self.color = color
        self.belief_states = [board.copy()]
        self.fail_safe_board = board.copy()
        self.move_count = 0
        self.opponent_name = opponent_name
        logger.log(f"Game started: {opponent_name}, playing as {'WHITE' if color else 'BLACK'}")
    
    def handle_opponent_move_result(self, captured_my_piece: bool, capture_square: Optional[Square]):
        """Update belief state based on opponent's move"""
        self.move_count += 1
        
        # Update fail-safe board
        if captured_my_piece:
            self.fail_safe_board.remove_piece_at(capture_square)
        
        # Don't generate new states on first move if we're white
        if self.move_count == 1 and self.color == chess.WHITE:
            return
        
        new_belief_states: List[chess.Board] = []
        
        for state in self.belief_states:
            state.turn = not self.color
            
            possible_moves = BoardUtils.generate_valid_moves(state)
            
            for move in possible_moves:
                if captured_my_piece and move != NULL_MOVE and move.to_square != capture_square:
                    continue
                
                if not captured_my_piece and move != NULL_MOVE and state.is_capture(move):
                    continue
                
                try:
                    candidate = BoardUtils.fast_copy_board(state)
                    if move != NULL_MOVE:
                        candidate.push(move)
                    new_belief_states.append(candidate)
                except Exception as e:
                    logger.error(f"Error pushing move {move}: {e}")
                    continue
        
        if new_belief_states:
            if len(new_belief_states) > MAX_BELIEF_STATES:
                new_belief_states = random.sample(new_belief_states, MAX_BELIEF_STATES)
            self.belief_states = new_belief_states
        else:
            logger.error("No valid belief states after opponent move")
            self.belief_states = [self.fail_safe_board.copy()]
        
        logger.log(f"After opponent move: {len(self.belief_states)} belief states")
    
    def _calculate_square_entropy(self, square: int, sample: List[chess.Board]) -> float:

        if not sample:
            return 0.0
        
        piece_counts = Counter()
        for board in sample:
            piece = board.piece_at(square)
            piece_counts[piece] += 1
        
        total = len(sample)
        entropy = 0.0
        
        for count in piece_counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        
        return entropy
    
    def _calculate_expected_eliminations(self, square: int, sample: List[chess.Board]) -> float:
 
        window = BoardUtils.get_3x3_window(square)
        sense_results_counter = defaultdict(int)
        
        for board in sample:
            result = tuple((sq, board.piece_at(sq)) for sq in window)
            sense_results_counter[result] += 1
        
        total_boards = len(sample)
        expected_eliminations = 0.0
        
        for count in sense_results_counter.values():
            eliminations = total_boards - count
            probability = count / total_boards
            expected_eliminations += probability * eliminations
        
        return expected_eliminations
    
    def choose_sense(self, sense_actions: List[Square], move_actions: List[chess.Move], seconds_left: float) -> Optional[Square]:

        if not sense_actions:
            return None
        
        # Filter edge squares
        filtered_actions = [sq for sq in sense_actions if BoardUtils.is_not_edge_square(sq)]
        if not filtered_actions:
            filtered_actions = sense_actions
        
        sample = self.belief_states if len(self.belief_states) <= SENSE_SAMPLE else random.sample(self.belief_states, SENSE_SAMPLE)
        
        best_square = None
        best_score = -float('inf')
        
        for square in filtered_actions:
            entropy = self._calculate_square_entropy(square, sample)
            
            expected_elim = self._calculate_expected_eliminations(square, sample)
            
            total_boards = len(sample) if len(sample) > 0 else 1
            combined_score = entropy * 0.6 + (expected_elim / total_boards) * 0.4
            
            if combined_score > best_score:
                best_score = combined_score
                best_square = square
        
        logger.log(f"Sensing at {chess.square_name(best_square) if best_square else 'None'} with score {best_score:.3f}")
        return best_square if best_square else random.choice(filtered_actions)
    
    def handle_sense_result(self, sense_result: List[Tuple[Square, Optional[chess.Piece]]]):
        """Update belief states and fail-safe board with sense result"""
        for square, piece in sense_result:
            self.fail_safe_board.set_piece_at(square, piece)
        
        consistent_states = []
        for state in self.belief_states:
            if BoardUtils.is_valid_board_given_sense(state, sense_result):
                consistent_states.append(state)
        
        if consistent_states:
            self.belief_states = consistent_states
        else:
            logger.error("No consistent belief states after sense")
            self.belief_states = [self.fail_safe_board.copy()]
        
        logger.log(f"After sense: {len(self.belief_states)} belief states")
    
    def _get_safe_stockfish_move(self, board: chess.Board, time_limit: float) -> Optional[chess.Move]:
        """
        Safely get a move from Stockfish, handling the ponder move error
        """
        try:
            limit = chess.engine.Limit(time=time_limit)
            result = self.engine.play(board, limit, ponder=False)
            return result.move
        except chess.engine.EngineError as e:
            logger.error(f"Stockfish engine error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error from Stockfish: {e}")
            return None
    
    def choose_move(self, move_actions: List[chess.Move], seconds_left: float) -> Optional[chess.Move]:

        self._ensure_engine_alive()
        
        if not move_actions:
            return None
        
        valid_moves = set(move_actions)
        
        king_capture = BoardUtils.check_for_king_capture(self.fail_safe_board, self.color)
        if king_capture and king_capture in valid_moves:
            logger.log(f"King capture available: {king_capture}")
            return king_capture
        
        if len(self.belief_states) > MAX_SAMPLE:
            sample = random.sample(self.belief_states, MAX_SAMPLE)
        else:
            sample = self.belief_states
        
        move_counter = Counter()
        king_capture_counter = Counter()
        
        for board in sample:
            try:
                self._ensure_engine_alive()
                
                king_capture = BoardUtils.check_for_king_capture(board, self.color)
                if king_capture and king_capture in valid_moves:
                    king_capture_counter[king_capture] += 1
                    continue
                
                board_copy = BoardUtils.fast_copy_board(board)
                board_copy.turn = self.color
                board_copy.clear_stack()
                
                time_per_board = max(0.05, min(0.5, seconds_left / max(len(sample), 1))) if seconds_left else 0.2
                result_move = self._get_safe_stockfish_move(board_copy, time_per_board)
                
                if result_move and result_move in valid_moves:
                    heuristic_value = BoardUtils.move_heuristic_value(board, result_move)
                    move_counter[result_move] += heuristic_value
                
            except Exception as e:
                logger.error(f"Error evaluating board: {e}")
                continue
        
        if king_capture_counter:
            total_king_votes = sum(king_capture_counter.values())
            best_king_move, best_king_votes = king_capture_counter.most_common(1)[0]
            
            local_uncertainty = best_king_votes / total_king_votes if total_king_votes > 0 else 0
            global_uncertainty = total_king_votes / len(sample) if len(sample) > 0 else 0
            
            if local_uncertainty > 0.5 and global_uncertainty > 0.35:
                logger.log(f"King capture move confirmed: {best_king_move}")
                return best_king_move
        
        if move_counter:
            best_move = max(move_counter, key=move_counter.get)
            if best_move in valid_moves:
                logger.log(f"Best move: {best_move} with score {move_counter[best_move]:.2f}")
                return best_move
        
        logger.log("Falling back to fail-safe board")
        try:
            self._ensure_engine_alive()
            self.fail_safe_board.turn = self.color
            self.fail_safe_board.clear_stack()
            result_move = self._get_safe_stockfish_move(self.fail_safe_board, 0.5)
            if result_move and result_move in valid_moves:
                return result_move
        except Exception as e:
            logger.error(f"Fail-safe board evaluation failed: {e}")
        
        return random.choice(move_actions)
    
    def handle_move_result(self, requested_move: Optional[chess.Move], taken_move: Optional[chess.Move],
                          captured_opponent_piece: bool, capture_square: Optional[Square]):
        """Update belief states after move execution"""
        if taken_move is None:
            return
        
        try:
            self.fail_safe_board.push(taken_move)
        except Exception as e:
            logger.error(f"Failed to push move {taken_move} on fail-safe board: {e}")
        
        consistent_states = []
        for state in self.belief_states:
            if taken_move in state.legal_moves:
                is_capture = state.is_capture(taken_move)
                
                if is_capture != captured_opponent_piece:
                    continue
                
                if captured_opponent_piece and taken_move.to_square != capture_square:
                    continue
                
                try:
                    new_state = BoardUtils.fast_copy_board(state)
                    new_state.push(taken_move)
                    consistent_states.append(new_state)
                except Exception as e:
                    logger.error(f"Error pushing move on state: {e}")
                    continue
        
        if consistent_states:
            self.belief_states = consistent_states
        else:
            logger.error("No consistent states after move result")
            self.belief_states = [self.fail_safe_board.copy()]
        
        logger.log(f"After move: {len(self.belief_states)} belief states")
    
    def handle_game_end(self, winner_color: Optional[Color], win_reason: Optional[WinReason],
                       game_history: GameHistory):
        try:
            self.engine.quit()
        except chess.engine.EngineTerminatedError:
            pass
        except Exception as e:
            logger.error(f"Error closing engine: {e}")
        
        logger.log(f"Game ended. Winner: {winner_color}, Reason: {win_reason}")