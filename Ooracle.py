# =============================================================================
# Ooracle.py — verbose, walked-through version of the RBC Oracle bot.
#
# Same code as oracle_bot.py, but rewritten so a 15-year-old who has never
# touched python-chess can follow it method-by-method. Every method is
# its own little "beat" — read them in order:
#
#       1. __init__                       — the bot wakes up
#       2. handle_game_start              — game starts, belief set has 1 board
#       3. handle_opponent_move_result    — enemy moved INVISIBLY → belief grows
#       4. choose_sense                   — pick a 3×3 peek (random baseline)
#       5. handle_sense_result            — peeked → filter belief set down
#       6. choose_move                    — vote across surviving beliefs
#       7. handle_move_result             — push our move on every belief
#       8. handle_game_end                — clean up the Stockfish process
#
# The whole bot is just those 8 methods. Nothing magic.
# =============================================================================

import os                                  # to read the STOCKFISH_EXECUTABLE env var
import random                              # uniform-random sense + tiebreak
from collections import Counter            # tally votes from many Stockfish calls
from typing import List, Optional, Tuple   # type hints (purely cosmetic)

import chess                               # the python-chess library: boards, moves, FENs
import chess.engine                        # the bridge that talks to the Stockfish .exe
from reconchess import (                   # the framework. It calls our 8 methods.
    Player, Color, Square, WinReason, GameHistory,
)


# -----------------------------------------------------------------------------
# Constants — pulled out so they're easy to tweak.
# -----------------------------------------------------------------------------

# Name of the environment variable that points to the stockfish binary.
# In the shell:  export STOCKFISH_EXECUTABLE=/path/to/stockfish
STOCKFISH_ENV_VAR = "STOCKFISH_EXECUTABLE"

# A safety net. Belief sets can balloon fast (1 -> 20 -> ~400 -> ~8000 in four
# turns if no captures happen). If we ever go over this many beliefs, we
# down-sample randomly. 10000 is generous; you can lower it if turns get slow.
BELIEF_CAP = 10000

# Total seconds we allow Stockfish to spend on ONE choose_move() call,
# *spread across all the beliefs we sample*. So if we have 50 beliefs and
# budget = 10s, each board gets 0.2s. Smaller belief set ⇒ more time per
# board ⇒ stronger play. That's a feature, not a bug.
STOCKFISH_TIME_BUDGET = 10.0

# How many beliefs we sample for voting. Stockfish on 1000 boards is too slow.
# 50 is a reasonable balance: still smart, still fast.
VOTE_SAMPLE_SIZE = 50


class OracleBot(Player):
    """
    The Oracle bot for Reconnaissance Blind Chess.

    Big idea (the apples-and-bananas recap):
        - We can't see the enemy's pieces.
        - So instead of one board, we keep a LIST of full boards (FENs)
          that *could* be the real one. That list is `self.beliefs`.
        - Every turn, the list grows (enemy moved invisibly) or shrinks
          (we sensed and filtered, or we moved and dropped impossible
          worlds).
        - To pick a move, we ask Stockfish on each surviving world and
          vote. Most-common move wins (random tiebreak).

    The whole class is just six callbacks the framework drives. Read them
    in the order listed in the module-level comment above.
    """

    # =========================================================================
    # BEAT 1 — __init__
    #
    # This runs ONCE, when the framework constructs our bot. The game hasn't
    # started yet. We set up empty state and we open Stockfish.
    # =========================================================================
    def __init__(self):

        # Our belief set. Each entry is a FULL FEN string for an 8x8 board.
        # Empty for now — handle_game_start (next beat) will put the real
        # starting position in here.
        self.beliefs: List[str] = []

        # Are we White or Black? The framework tells us in handle_game_start.
        # We need this in lots of places to flip whose turn it is when we
        # reason about hypothetical opponent moves.
        self.color: Optional[Color] = None

        # Find the stockfish binary using the env var STOCKFISH_EXECUTABLE.
        # If it's missing or the path doesn't point at a real file, we
        # blow up early with a clear message — better than a cryptic
        # error mid-game.
        path = os.environ.get(STOCKFISH_ENV_VAR)
        if not path or not os.path.exists(path):
            raise RuntimeError(
                f"set {STOCKFISH_ENV_VAR} to a valid stockfish binary"
            )

        # Open Stockfish as a long-running subprocess. We talk to it via
        # the UCI protocol (Universal Chess Interface) — but we don't have
        # to think about that, python-chess hides it.
        # setpgrp=True puts it in its own process group so it dies cleanly
        # if our bot dies.
        self.engine = chess.engine.SimpleEngine.popen_uci(path, setpgrp=True)

    # =========================================================================
    # BEAT 2 — handle_game_start
    #
    # The framework calls this exactly once, telling us:
    #   - what color we are
    #   - the starting board (chess.Board) — this is the SAME for both
    #     players because RBC starts in the standard position with full
    #     visibility for everyone
    #   - the opponent's name (we ignore it for now)
    #
    # At this very moment our belief set has exactly ONE entry: the real
    # board. No uncertainty yet — we know everything because the rules
    # fix the start.
    # =========================================================================
    def handle_game_start(
        self,
        color: Color,
        board: chess.Board,
        opponent_name: str,
    ):

        # Remember our color for later (used in every other method).
        self.color = color

        # Seed the belief set with the one true starting position.
        # board.fen() turns the chess.Board into a FEN string we can store.
        self.beliefs = [board.fen()]

    # =========================================================================
    # BEAT 3 — handle_opponent_move_result
    #
    # This is THE method where the belief set GROWS.
    #
    # The framework just told us: the opponent finished their turn. We
    # don't know what they did, but we know two facts:
    #     captured_my_piece  — True if they captured one of our pieces
    #     capture_square     — if so, on which square
    #
    # So we expand every belief board by every move the opponent could
    # have made on that board, then keep only the ones consistent with
    # those two facts.
    # =========================================================================
    def handle_opponent_move_result(
        self,
        captured_my_piece: bool,
        capture_square: Optional[Square],
    ):

        # Edge case: if we're White, then on the very first turn the
        # framework calls this BEFORE we've moved yet. Black hasn't moved
        # either. We have nothing to update. Just bail.
        # (We also bail if beliefs is somehow empty.)
        if self.color == chess.WHITE and not self.beliefs:
            return

        # We'll build the NEW belief set in a Python set (dedupes
        # automatically — different opponent moves can land in the same
        # FEN, e.g. transpositions).
        new_beliefs = set()

        # Walk every board we currently think the world might be in.
        for fen in self.beliefs:
            board = chess.Board(fen)

            # Make sure it's the OPPONENT's turn on this hypothetical
            # board — we're enumerating their moves, not ours.
            board.turn = not self.color

            # ---- option A: opponent passed (the null move) ----
            # In RBC the opponent is allowed to do nothing. But you can't
            # capture by passing, so this option is only valid if our
            # piece was NOT captured this turn.
            if not captured_my_piece:
                nb = board.copy(stack=False)        # cheap copy (no move history)
                nb.push(chess.Move.null())          # the "I pass" move
                new_beliefs.add(nb.fen())

            # ---- option B: opponent made a real pseudo-legal move ----
            # pseudo_legal_moves = follows piece movement rules, ignores
            # whether the king is in check. RBC has no check rule so
            # pseudo-legal is what we want.
            for move in board.pseudo_legal_moves:

                is_cap = board.is_capture(move)

                # If our piece WAS captured: keep only moves that
                # actually captured something AND landed on the right
                # square. Anything else is impossible.
                if captured_my_piece and (
                    not is_cap or move.to_square != capture_square
                ):
                    continue

                # If our piece was NOT captured: drop any opponent move
                # that captures (because if they had captured, we'd
                # have been told).
                if not captured_my_piece and is_cap:
                    continue

                # Survived both filters — apply this opponent move and
                # store the resulting FEN as a new belief.
                nb = board.copy(stack=False)
                nb.push(move)
                new_beliefs.add(nb.fen())

        # Replace beliefs with the expanded list.
        self.beliefs = list(new_beliefs)

        # Safety net: if the belief set has exploded past our cap,
        # randomly down-sample to keep the rest of the turn fast.
        # (A smarter bot would weight by likelihood, but the rubric
        # only asks for the random baseline.)
        if len(self.beliefs) > BELIEF_CAP:
            self.beliefs = random.sample(self.beliefs, BELIEF_CAP)

    # =========================================================================
    # BEAT 4 — choose_sense
    #
    # The framework hands us:
    #   sense_actions — list of legal sense centres (just the inner 6×6;
    #                   the 3×3 window has to fit on the board)
    #   move_actions  — list of legal moves we *could* make (we ignore
    #                   this for the baseline)
    #   seconds_left  — total seconds left on our game clock (also ignored)
    #
    # The rubric for the baseline says: pick a sense square uniformly at
    # random. That's literally one line. The "smart sensing" upgrade
    # (information gain etc.) goes here in the improved version.
    # =========================================================================
    def choose_sense(
        self,
        sense_actions: List[Square],
        move_actions: List[chess.Move],
        seconds_left: float,
    ) -> Optional[Square]:

        # The dumb-but-required baseline. Pure coin flip across all 36
        # legal centre squares.
        return random.choice(sense_actions)

    # =========================================================================
    # BEAT 5 — handle_sense_result
    #
    # The framework just sensed for us and is handing back:
    #   sense_result — list of 9 (square, piece-or-None) pairs telling
    #                  us exactly what was in the 3×3 window we picked.
    #
    # This is the ONLY method that SHRINKS the belief set via direct
    # observation. We walk every belief and ask: "does this board show
    # the same thing I just saw?" If not, drop it.
    # =========================================================================
    def handle_sense_result(
        self,
        sense_result: List[Tuple[Square, Optional[chess.Piece]]],
    ):

        kept = []  # the beliefs that survive the filter

        # Walk every candidate world.
        for fen in self.beliefs:
            board = chess.Board(fen)

            # This is a Python "for/else" trick: the else block runs
            # ONLY if the for loop ran to completion without `break`.
            # We use it to mean "all 9 squares matched ⇒ keep this
            # belief".
            for sq, piece in sense_result:
                actual = board.piece_at(sq)

                # If one says empty and the other doesn't, mismatch.
                if (piece is None) != (actual is None):
                    break

                # If both have a piece, but different pieces, mismatch.
                if piece is not None and actual.symbol() != piece.symbol():
                    break
            else:
                # Loop finished without breaking — all 9 squares matched.
                kept.append(fen)

        # Defensive: never wipe the belief set entirely. If the filter
        # somehow eliminated everything (shouldn't happen unless there's
        # a bug elsewhere), keep the old set so we don't crash later.
        if kept:
            self.beliefs = kept

    # =========================================================================
    # BEAT 6 — choose_move
    #
    # Now we actually decide what to play. The plan:
    #   1. Sample at most VOTE_SAMPLE_SIZE beliefs (Stockfish on 1000
    #      boards is unworkable in a real game).
    #   2. For each sampled belief:
    #        - if the enemy king is takeable RIGHT NOW, vote for that
    #          (king-grab heuristic borrowed from TroutBot — never miss
    #          a free king).
    #        - otherwise, ask Stockfish for the best move on that board.
    #   3. Tally votes. Most-common move wins. RANDOM tiebreak (rubric
    #      explicitly requires this).
    # =========================================================================
    def choose_move(
        self,
        move_actions: List[chess.Move],
        seconds_left: float,
    ) -> Optional[chess.Move]:

        # Defensive: if somehow we have no beliefs, just bail safely.
        # move_actions + [None] lets us include "pass" as an option.
        if not self.beliefs:
            return random.choice(move_actions + [None])

        # Sub-sample beliefs if the set is too big. Stockfish on every
        # belief is theoretically nicer but practically too slow.
        if len(self.beliefs) <= VOTE_SAMPLE_SIZE:
            sample = self.beliefs
        else:
            sample = random.sample(self.beliefs, VOTE_SAMPLE_SIZE)

        # Split the time budget across the sample. Floor at 0.05s so
        # Stockfish always has at least a tiny moment to think.
        per_board = max(0.05, STOCKFISH_TIME_BUDGET / len(sample))

        votes = []   # list of UCI move strings, one per board

        for fen in sample:
            board = chess.Board(fen)

            # Make sure it's our turn on this hypothetical board.
            # Without this, Stockfish would give the opponent's best
            # move, which is the opposite of what we want.
            board.turn = self.color
            board.clear_stack()  # forget any history; we just want
                                 # the static position.

            # ---- king-grab shortcut ----
            # If on this hypothetical board our pieces directly attack
            # the enemy king, just take it. This is "if you see a free
            # win, take the free win" — it can't be worse than asking
            # Stockfish, and it can be much better.
            enemy_king = board.king(not self.color)
            if enemy_king is not None:
                attackers = board.attackers(self.color, enemy_king)
                if attackers:
                    # attackers is a SquareSet; pop one. Pick that
                    # piece and capture the king with it.
                    attacker_sq = attackers.pop()
                    capture_move = chess.Move(attacker_sq, enemy_king)
                    votes.append(capture_move.uci())
                    continue  # next belief; skip Stockfish

            # ---- normal Stockfish call ----
            # Hand Stockfish the FEN, get back its best move.
            try:
                result = self.engine.play(
                    board,
                    chess.engine.Limit(time=per_board),
                )
                if result.move is not None:
                    votes.append(result.move.uci())
            except chess.engine.EngineError:
                # Stockfish complained about this position (rare —
                # usually a bad FEN). Skip and move on.
                continue

        # No votes means everything failed. Punt.
        if not votes:
            return random.choice(move_actions + [None])

        # ---- tally votes, with random tiebreak ----
        counts = Counter(votes)
        top_count = counts.most_common(1)[0][1]

        # All moves tied for first place.
        winners = [m for m, c in counts.items() if c == top_count]

        # Random tiebreak (rubric requirement).
        chosen_uci = random.choice(winners)
        chosen = chess.Move.from_uci(chosen_uci)

        # Final safety: only return moves the framework considers legal
        # for THIS move turn. If our voted move isn't in the legal list
        # (rare, e.g. it was a king-grab on a belief that's actually
        # impossible), fall back to a random legal move.
        if chosen in move_actions:
            return chosen
        return random.choice(move_actions + [None])

    # =========================================================================
    # BEAT 7 — handle_move_result
    #
    # The framework just executed our move. It tells us:
    #   requested_move — what we asked for
    #   taken_move     — what actually happened (might be None if it failed)
    #   captured_opponent_piece — did we capture?
    #   capture_square — if so, where?
    #
    # We update the belief set: push the *taken* move on every belief,
    # dropping beliefs where the move would've been illegal. The fact
    # that taken_move == None vs. == requested_move is FREE INFORMATION
    # — every move outcome tells us something about which world we're in.
    # =========================================================================
    def handle_move_result(
        self,
        requested_move: Optional[chess.Move],
        taken_move: Optional[chess.Move],
        captured_opponent_piece: bool,
        capture_square: Optional[Square],
    ):

        kept = []  # beliefs that are still consistent

        for fen in self.beliefs:
            board = chess.Board(fen)
            board.turn = self.color
            board.clear_stack()

            # ---- case A: taken_move is None (our move failed) ----
            # Keep this belief only if requested_move would ALSO have
            # failed on it (i.e. it wasn't pseudo-legal here). If
            # requested_move WOULD have been legal in this world but the
            # framework said it didn't go through, this world is wrong
            # and we drop it.
            if taken_move is None:
                if (
                    requested_move is None
                    or requested_move not in board.pseudo_legal_moves
                ):
                    kept.append(board.fen())
                continue

            # ---- case B: taken_move actually happened ----
            # Keep this belief only if the move was pseudo-legal here
            # AND the capture-flag matches AND (if captured) the square
            # matches. Anything else is impossible and we drop it.
            if taken_move not in board.pseudo_legal_moves:
                continue
            if captured_opponent_piece != board.is_capture(taken_move):
                continue
            if (
                captured_opponent_piece
                and taken_move.to_square != capture_square
            ):
                continue

            # Survivor — apply the move and store the new FEN.
            board.push(taken_move)
            kept.append(board.fen())

        # Defensive: if everything got eliminated (bug somewhere?), keep
        # what we had rather than crash on the next turn.
        if kept:
            self.beliefs = kept

    # =========================================================================
    # BEAT 8 — handle_game_end
    #
    # The framework calls this once at the end. Our only job is to shut
    # Stockfish down cleanly so we don't leak processes.
    # =========================================================================
    def handle_game_end(
        self,
        winner_color: Optional[Color],
        win_reason: Optional[WinReason],
        game_history: GameHistory,
    ):

        try:
            self.engine.quit()
        except chess.engine.EngineTerminatedError:
            # Already dead. No-op.
            pass
