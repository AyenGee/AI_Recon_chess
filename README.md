# Reconnaissance Chess (RBC) — Project Intro

> A short, lecture-style walkthrough of what we are building, why it matters,
> and how the pieces in this folder fit together.

---

## 1. What is Reconnaissance Chess?

**Reconnaissance Blind Chess (RBC)** is a variant of chess invented at
Johns Hopkins APL. The rules of moving the pieces are the same as in
ordinary chess, but **you cannot see your opponent's pieces**.

Each turn you do **two things**:

```
   ┌──────────────────────┐      ┌──────────────────────┐
   │   1. SENSE           │  →   │   2. MOVE            │
   │   pick a 3×3 window  │      │   pick a chess move  │
   │   on the board and   │      │   (you don't know if │
   │   peek inside it     │      │   it'll succeed)     │
   └──────────────────────┘      └──────────────────────┘
```

You do **not** get told when your opponent moves (only if they captured
something of yours, and where). There is **no check**, **no checkmate** —
**you win by capturing the enemy king.**

### The board you actually "see"

Regular chess (full information):

```
  a b c d e f g h
8 r n b q k b n r
7 p p p p p p p p
6 . . . . . . . .
5 . . . . . . . .
4 . . . . . . . .
3 . . . . . . . .
2 P P P P P P P P
1 R N B Q K B N R
```

RBC, from White's point of view (only your pieces + last sensed window):

```
  a b c d e f g h
8 ? ? ? ? ? ? ? ?    ← unknown
7 ? ? ? ? ? ? ? ?
6 ? ? ? ? ? ? ? ?    ┌────────┐
5 ? ? ? ? . p . ?    │ sensed │  ← 3×3 window we peeked at
4 ? ? ? ? . . . ?    │ window │
3 ? ? ? ? . . . ?    └────────┘
2 P P P P P P P P
1 R N B Q K B N R
```

That `?` is the whole game. RBC is chess with **partial observation**.

---

## 2. Why this is interesting (and still relevant)

Most "famous" board-game AI you've heard of — Deep Blue, AlphaZero,
Stockfish — solved **perfect-information** games. The agent always knows
the full state of the world. That is a very clean problem.

The real world is **not** like that. Self-driving cars, medical
diagnosis, poker, military planning, robotics — none of these agents
ever see the full state. They have to act **under uncertainty**.

RBC is a clean, well-defined sandbox for that harder problem:

| Property                | Regular Chess        | Recon Chess (RBC)            |
|-------------------------|----------------------|------------------------------|
| Observable              | Fully observable     | **Partially** observable     |
| Outcome of own move     | Deterministic        | **Stochastic** (can fail)    |
| Opponent move feedback  | You see it           | **Hidden** (mostly)          |
| State the agent reasons over | One board       | **Many possible boards**     |
| Skills required         | Search + evaluation  | Search + **belief tracking** + sensing |

So although chess engines are "solved," RBC is **not**. It forces you to
build the kind of agent the field actually still cares about: one that
reasons over **what it doesn't know**.

---

## 3. The core idea: a *belief* over boards

Because we cannot see the opponent, we keep a **set of board states we
think are possible** — call it the **belief state**.

```
                ┌─────────────────────┐
                │    Belief state     │
                │   { B1, B2, ..., Bk }│   ← all boards still consistent
                └──────────┬──────────┘     with what we've observed
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   our move fires    opponent moves       we sense a 3x3
   (push on every    (expand each Bi      window → throw away
    Bi, drop ones    by all of their      every Bi that doesn't
    that became      pseudo-legal         match what we saw
    impossible)      replies)
```

Each step in the loop is one of the small Python files in this folder —
which is what we'll look at next.

---

## 4. What this project builds

Each file is one **building block** for an RBC agent. Together they
implement the loop above.

| File                          | Role in the agent loop                              | Input → Output                          |
|-------------------------------|-----------------------------------------------------|------------------------------------------|
| `rbc_state_representation.py` | Pretty-print a board from a FEN string              | FEN → ASCII board                        |
| `next_move_pred.py`           | All pseudo-legal moves from a state (+ null move)   | FEN → list of UCI moves                  |
| `next_state_pred.py`          | All board states reachable in one move              | FEN → list of FEN                        |
| `next_state_cap_pred.py`      | States reachable that capture on a given square     | FEN + square → list of FEN               |
| `next_state_pred_sense.py`    | Filter a belief set by a sensed 3×3 window          | list of FEN + window → filtered FEN list |
| `rbc_move_exec.py`            | Apply a UCI move to a FEN, return new FEN           | FEN + move → FEN                         |
| `move_generation.py`          | Pick a move on one board (king-grab, else Stockfish)| FEN → UCI move                           |
| `mult_move_gen.py`            | Pick the *most-voted* move across a belief set      | list of FEN → UCI move                   |
| `random_bot.py`               | A baseline RBC player (random sense + random move)  | —                                        |
| `trout_bot.py`                | A stronger reference bot from the RBC framework     | —                                        |

### How the blocks compose

```
       ┌─────────────────────────────────────────────────────┐
       │                  Our turn starts                    │
       └──────────────────────────┬──────────────────────────┘
                                  │
       ┌──────────────────────────▼──────────────────────────┐
       │  Expand belief by opponent's possible last move     │
       │  (next_state_pred.py / next_state_cap_pred.py)      │
       └──────────────────────────┬──────────────────────────┘
                                  │
       ┌──────────────────────────▼──────────────────────────┐
       │  Pick a 3×3 sense square, observe the window        │
       │  Filter belief: next_state_pred_sense.py            │
       └──────────────────────────┬──────────────────────────┘
                                  │
       ┌──────────────────────────▼──────────────────────────┐
       │  For each board in belief, ask Stockfish for a move │
       │  (move_generation.py), then majority-vote across    │
       │  the belief set (mult_move_gen.py)                  │
       └──────────────────────────┬──────────────────────────┘
                                  │
       ┌──────────────────────────▼──────────────────────────┐
       │  Execute move (rbc_move_exec.py), update belief     │
       └─────────────────────────────────────────────────────┘
```

This is a classic **think-in-many-worlds** approach: instead of trying
to guess the one true board, we keep all plausible boards and act
robustly across them.

---

## 5. Where this sits in the AI course

You can think of the techniques in RBC as a sampler of much of an AI
syllabus, all glued onto one task:

| Course topic                  | How RBC uses it                                     |
|-------------------------------|------------------------------------------------------|
| Search                        | Stockfish does the move search on each candidate board |
| State-space representation    | FEN strings as compact world states                  |
| Reasoning under uncertainty   | The belief set itself                                |
| Probabilistic reasoning       | Weighting / filtering boards by what we observed     |
| Decision making               | Choosing a sense square = an *information-gathering* action |
| Multi-agent / adversarial     | Opponent is hostile *and* hidden                     |

It is also a reminder that "AI" is broader than today's headline tech:
even in a world dominated by large-scale generative models, an enormous
amount of practical AI is still about **structured agents acting under
uncertainty** — exactly what RBC is.

---

## 6. Sense and move: a worked example

Suppose it's our turn and we're White. We have two boards in our belief
set, `B1` and `B2`, that differ only in **where the black knight is**:

```
   B1: knight on f6              B2: knight on d7
   . . . . . n . .               . . . n . . . .
   p p p p p p p p               p p p p . p p p
   . . . . . . . .               . . . . . . . .
   ...                           ...
```

If we sense the 3×3 window centred at `e7`, we will see:

```
   B1's window:  . . .            B2's window:  n . .
                 . . .                          p . p
                 . . n                          . . .
```

The two are different, so **the sense will tell us which world we're
in** — that's the whole point of choosing the sense well.
`next_state_pred_sense.py` does exactly this filtering: throw away
every board in the belief set that disagrees with what we saw.

Then `mult_move_gen.py` runs Stockfish on whichever boards remain and
picks the move that was suggested most often — a simple but effective
way to act robustly when more than one world is still possible.

---

## 7. Setup

1. Install dependencies:
   ```
   pip install python-chess reconchess
   ```
2. Download the **Stockfish** executable (follow Steve's instructions in
   the course handout) and place it in this folder as `./stockfish`.
   The move-generation files (`move_generation.py`, `mult_move_gen.py`)
   call this binary directly.
3. Run any module standalone — each one reads from `stdin` and writes
   to `stdout`. For example:
   ```
   echo "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" \
     | python next_move_pred.py
   ```

---

## 8. TL;DR

- **RBC = chess, but you can't see the opponent.**
- We keep a **belief set** of boards that are still possible.
- Each file in this folder is one operator on that belief set:
  expand it, filter it, or pick a move from it.
- This is small and self-contained, but the *shape* of the problem —
  acting well under partial observation — is what almost every serious
  real-world AI system has to solve. That's why a 64-square game is
  still a worthwhile place to learn it.
