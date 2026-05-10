# Reconnaissance Blind Chess — Notes from Scratch

A re-cap of everything we covered, in two halves:

- **Part A — Apples & bananas:** the game, the bot, the belief set, sensing, Stockfish. No jargon.
- **Part B — Framework:** RBC as a POMDP, why the problem is still open, and the deeper question of how to *sense well* (this is where the real research lives).

---

# Part A — Apples & Bananas

## A1. What the game is

Chess, but **blindfolded for the opponent's pieces**.

You see your own pieces. You don't see theirs. You only learn things when:

- You **sense** a 3×3 patch of the board (one peek per turn) and it tells you what's in those 9 squares.
- Your own piece gets **captured** (you're told the square).
- Your move **goes through or fails** (you find out which).

You win by **capturing the enemy king** — there's no check, no checkmate, no stalemate.

## A2. What a FEN string is

A short text snapshot of a chess position. Splits on `/` into 8 rows (rank 8 → rank 1), letters are pieces (UPPER = white, lower = black), digits = empty squares.

```
rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
└─────── board ────────┘ │  └──┘ │ │ │
                       turn castling │ │ └ full move number
                                en-passant│
                                          half-move clock
```

The bit before the first space is the actual board. The rest is metadata you can mostly ignore.

## A3. What "an agent" looks like in code

The `reconchess` library hands you a class to fill in. It's a state machine with **six callbacks**:

| Callback | When it's called | What you do |
|---|---|---|
| `handle_game_start` | once | initialise your belief set |
| `handle_opponent_move_result` | start of your turn | expand belief by every move opponent could have made |
| `choose_sense` | every turn | pick a 3×3 centre square |
| `handle_sense_result` | after sensing | filter belief set to only worlds matching the window |
| `choose_move` | every turn | majority-vote a move across remaining beliefs |
| `handle_move_result` | after moving | apply your move to every belief, drop impossible ones |

That's the whole agent. Six methods.

## A4. The belief set

Because you can't see the enemy, you keep **a list of full chess boards** that *could* be the real one. That list is the **belief set**:

```python
self.beliefs: list[str]   # list of FEN strings (full 8×8 boards)
```

Each entry is a complete board. The 3×3 sense window is *not* a belief — it's the **filter** you put across them.

### How the list size moves

```
   game start            after enemy moves           after you sense
  ┌───────────┐         ┌──────────────────┐        ┌──────────────┐
  │ 1 board   │  ───►   │ ~20 boards       │ ───►   │ ~5 boards    │
  └───────────┘         └──────────────────┘        └──────────────┘
   you know it all       uncertainty added           uncertainty cut
```

- **Grows** when the opponent makes a hidden move (every pseudo-legal reply they could've made → one new belief each).
- **Shrinks** when you sense (drop every board whose 9-square window disagrees with what you saw) and when you move (drop every board where your *taken* move would have been illegal).

## A5. Pseudo-legal vs legal

- **Legal** = follows piece rules **and** doesn't leave your king in check.
- **Pseudo-legal** = follows piece rules only (ignores check).

RBC has no concept of check, so we use **pseudo-legal**. Walking your king into "check" is fine in RBC — it just means the opponent *might* capture it next turn, if they happen to know it's exposed.

## A6. Stockfish

Stockfish is a separate, free, world-class **normal-chess** engine. It is a black box:

```
   one FEN  ──────►  STOCKFISH  ──────►  one move (UCI: "e2e4")
```

You don't write it, don't peek inside, don't modify it. You just hand it boards and collect moves.

It only understands normal chess (one fully-known board), so you **cannot** hand it a belief set. You call it once per board in your belief set, then **majority-vote** across the answers.

## A7. The decision loop, end-to-end

```
                ┌───────────────────────────────┐
                │ start of turn                 │
                │ belief = [B1, B2, …, Bk]      │
                └────────────────┬──────────────┘
                                 │
            opponent move?       │
            (we infer hidden)    ▼
                  ┌──────────────────────────────┐
                  │ for each belief:             │
                  │   add every board reachable  │
                  │   by any opponent move       │
                  │ → belief grows                │
                  └────────────────┬─────────────┘
                                   │
            sense                  ▼
                  ┌──────────────────────────────┐
                  │ pick 3×3 centre              │
                  │ filter belief: drop boards   │
                  │ whose window ≠ what we saw   │
                  │ → belief shrinks             │
                  └────────────────┬─────────────┘
                                   │
            choose move            ▼
                  ┌──────────────────────────────┐
                  │ for each belief:             │
                  │   move = stockfish(belief)   │
                  │ play the most-common move    │
                  │ (random tiebreak)            │
                  └────────────────┬─────────────┘
                                   │
            apply our move         ▼
                  ┌──────────────────────────────┐
                  │ for each belief:             │
                  │   push the *taken* move      │
                  │   drop if illegal there      │
                  │ → belief stays consistent    │
                  └──────────────────────────────┘
```

## A8. Tiny worked example — why sensing matters

Belief set = 2 boards differing only in **enemy queen position**.

| World | Stockfish says | Why |
|---|---|---|
| queen on **f6** | retreat `Bf1` | bishop hanging |
| queen on **c3** | attack `Nxc3` | free queen |

Random sense at `a1` → learns nothing → vote splits 1–1 → coin flip → likely loses material.

Smart sense at `e6` → window distinguishes the two worlds → belief collapses to 1 → unambiguous play → keeps the bishop, maybe wins the queen later.

**Sensing turns guesses into facts. Facts let Stockfish play correctly. Correct play wins games.**

---

# Part B — The Framework: RBC as a POMDP

You picked up on something important: this isn't really a chess problem, it's a **decision-under-partial-observation** problem that happens to use chess as its surface.

## B1. POMDP, formally

A POMDP — *Partially Observable Markov Decision Process* — is the standard formal model for an agent acting under uncertainty. It is a 7-tuple `(S, A, T, R, Ω, O, γ)`:

| Symbol | Meaning | In RBC |
|---|---|---|
| `S` | set of states | every legal chess position (FEN), plus whose turn it is |
| `A` | actions | every (sense_square, move) pair available this turn |
| `T(s' \| s, a)` | transition function | mostly deterministic for *your* move on a given board, **but** you don't know which `s` you're in |
| `R(s, a)` | reward | +1 for capturing the enemy king, −1 for losing yours, 0 otherwise |
| `Ω` | observation set | every possible 3×3 sense window, plus capture/move-result feedback |
| `O(o \| s', a)` | observation function | what the engine reports back given the true new state |
| `γ` | discount | small enough to encourage finishing the game |

Because you don't know `s` directly, you maintain a **belief** `b(s)` — a probability distribution over `S`. Your "list of FENs" *is* a (uniform) belief; a fancier agent would also track *probabilities*.

### The POMDP shape, drawn

```
     ┌────────────┐         ┌────────────┐         ┌────────────┐
     │ true state │ ──T──►  │ true state │ ──T──►  │ true state │   ← hidden world
     │     s_t    │         │   s_{t+1}  │         │   s_{t+2}  │
     └─────┬──────┘         └─────┬──────┘         └─────┬──────┘
           │ O                    │ O                    │ O
           ▼                      ▼                      ▼
     ┌────────────┐         ┌────────────┐         ┌────────────┐
     │ obs o_t    │         │ obs o_{t+1}│         │ obs o_{t+2}│   ← what we see
     │ (3×3 etc.) │         │            │         │            │
     └─────┬──────┘         └─────┬──────┘         └─────┬──────┘
           │                      │                      │
           ▼                      ▼                      ▼
     ┌────────────┐         ┌────────────┐         ┌────────────┐
     │ belief b_t │ ──upd►  │  b_{t+1}   │ ──upd►  │  b_{t+2}   │   ← in our head
     │ over S     │         │            │         │            │
     └────────────┘         └────────────┘         └────────────┘
```

The **key move**: instead of acting on `s` (which you can't see), you act on `b` (which you maintain). This is a fundamental trick of POMDP solving — *if you treat the belief itself as the state, the partially-observed problem becomes a fully-observed one again, just in a bigger space*.

## B2. Why POMDPs are still hard (and still researched)

Three reasons:

1. **The belief space is enormous.** For tiny POMDPs (a few states) you can compute optimal policies. For RBC the state space is the size of legal-chess-positions (≈ 10⁴⁴), and the belief space is *distributions over that*. Exact methods (`POMDP value iteration`, `point-based VI`) collapse instantly.
2. **Long horizon × adversary.** The opponent is also a POMDP agent, also reasoning about *your* belief about their belief… (recursive belief modelling — the open frontier). This pushes the problem from POMDP into **POSG** (partially-observable stochastic *game*).
3. **Information has to be *valued*.** Sensing doesn't move pieces or capture anything — its only payoff is *future* clarity. That's a hard credit-assignment problem: how much is "I'd know more if I peeked here" worth in king-capture currency?

POMDPs underpin: robotics (LIDAR-based navigation), medical decision-making (test ordering), dialogue systems (intent tracking), poker bots, autonomous vehicles. RBC is a **clean, deterministic-physics, adversarial POMDP** — the perfect lab problem for the family.

## B3. Why this problem is still worth solving

You might think: chess is solved, computers crush humans, what's left? RBC reframes it.

- **Deep Blue / Stockfish / AlphaZero solved perfect-information games.** You hand them the state, they hand you the move.
- **The real world isn't perfect-information.** Surgeons act without full diagnostic info. Drones fly without seeing every obstacle. Soldiers plan without enemy positions. Negotiators trade without seeing the other side's BATNA.
- **RBC makes that exact gap small enough to study.** 64 squares, deterministic mechanics, perfectly defined observation model. If you can build a great RBC bot, the *techniques* (belief tracking, information-valued sensing, Monte-Carlo over belief, opponent modelling) transfer directly.
- **It's also unsolved.** No one has a "Stockfish-level" RBC bot. The annual JHU APL tournament still has wide skill gaps. There's room to contribute, even at undergrad level.

## B4. Sensing — the lever you noticed

You're right to fixate on sensing. The deepest insight in this assignment is:

> **In RBC, the only action you fully control is your sense. Your moves are stochastic, your opponent is hidden, but *where you look* is yours alone.**

Sensing is the only **information-gathering action**. Moving doesn't reduce uncertainty (it changes the world but doesn't tell you which world you were in). Sensing is purely epistemic — it doesn't change the board, it changes *you*.

### Why random sensing is wasteful (the baseline's flaw)

The rubric's baseline says "sense uniformly at random." That's deliberately bad — it's a benchmark, not a strategy. Random sensing wastes your one peek per turn on:

- squares full of your own pieces (you already know what's there),
- squares far from likely enemy activity (no boards in your belief set disagree there),
- areas the opponent hasn't moved to in 30 turns.

A **good** sense at the right moment can collapse 200 belief-boards down to 3. A **bad** sense leaves all 200.

### Is it really a coin flip? No — it's quantifiable.

Here's the part you intuited: *"surely there's a good way to sense."* There is. It's called **information gain** (or **expected entropy reduction**), and it's a *defined* framework, not a vibe.

The intuition:

```
   For each candidate sense centre c (one of the inner 6×6 squares):
     1. Look at every belief board in your set.
     2. For each one, compute the 3×3 window it would show at centre c.
     3. Group the belief boards by what window they'd show.
     4. The "expected residual belief size" after sensing at c is then:
            sum over groups g of:  P(group g) * |group g|
        (you'll land in some group, then your belief shrinks to that group)

   Pick the c that minimises this expected residual size.
   Equivalently — pick the c with the highest *expected information gain*:
            H(belief) - E_o[H(belief | observation o)]
```

Plain English: *"Pick the square where the 3×3 windows across my belief set disagree the most."* That's the square most likely to split the belief set into small chunks.

### A picture

```
   Belief set = 8 boards. Sense candidates (just two for illustration):
   
   Sense at c₁ = a1 (corner of your own pieces):
     all 8 boards show the SAME 3×3 → no boards eliminated → belief still 8
     waste.
   
   Sense at c₂ = e6 (where boards diverge on enemy knight position):
     ┌──────────────┬───────┐
     │ window seen  │ count │
     ├──────────────┼───────┤
     │ . . . / . . . / . . . │   3 boards
     │ . . . / . n . / . . . │   2 boards
     │ . . . / . . . / . p . │   2 boards
     │ . . . / . p . / . . . │   1 board
     └──────────────┴───────┘
     after sensing, you land in ONE of those groups.
     expected residual = (3/8)*3 + (2/8)*2 + (2/8)*2 + (1/8)*1 = 2.25 boards
     → belief drops from 8 → ~2 in one peek.
```

This is the core idea behind smart sensing in RBC. Variants:

- **Plain information gain** (above) — the "Oracle bot, but smart" approach.
- **Adversarial-aware sensing** — also weight by *which* uncertainty hurts you most. Not knowing where the enemy *king* is matters more than not knowing where their *pawn on h7* is.
- **Move-conditioned sensing** — sense at the square your candidate move ends on, so you find out before-the-fact whether the move will work.

The Perrotta et al. (2022) paper the assignment cites is exactly this conversation, formalised. **You're already thinking like the paper.**

### Where to take it for Part 4.3

Three concrete improvements you can implement, in increasing difficulty:

1. **Sense where you plan to move** — if your planned move is `Nxe5`, sense around `e5` first. Cheap and obviously useful.
2. **Sense the highest-disagreement square** — implement the information-gain heuristic above. Bigger lift but tractable.
3. **Sense to localise the enemy king** — track per-square posterior probability of the enemy king and sense the highest-entropy region of *that* distribution. Most paper-worthy.

You don't need all three. One of them, well done and discussed in the report, is plenty.

## B5. The opponent — what you can and can't assume

You asked whether you can tell if your opponent is adversarial. **You cannot, in general.** The opponent could be:

- **Random** — pure baseline.
- **Trout** — assumes one true board, ignores belief.
- **Oracle** — your own architecture, possibly stronger.
- **A neural-network bot** trained on millions of games.

The standard assumption in this family of problems is "**worst-case opponent up to the rules**" — they will play to maximise their win probability against your strategy. In an introductory project the opponents are all known and weaker, so you can specialise. In a real tournament you'd add **opponent modelling**: track which moves the opponent made and infer what their belief / strategy might be. That's beyond the scope here, but worth knowing exists — it's the next layer of the onion.

## B6. The 30-second pitch

> RBC is a clean, adversarial POMDP. Your bot's intelligence isn't in the chess (Stockfish handles that) — it's in **how it manages uncertainty**. Belief tracking is your memory. Sensing is your only knob for reducing it. The baseline senses randomly, which is provably wasteful; the research direction is **information-gain-based sensing** — provably better and cleanly formalisable. You're not just building a chess bot, you're building a small, contained instance of the kind of agent every serious real-world system has to be.

---

# Quick glossary

| Term | One-line definition |
|---|---|
| FEN | Text snapshot of a chess board. |
| UCI move | `<from><to>[<promo>]` string, e.g. `e2e4`, `e7e8q`. `0000` = null move. |
| Pseudo-legal | Move that follows piece rules, ignores king-safety. RBC uses these. |
| Belief set | Your list of full FENs that *could* be the real board. |
| Sense | One-per-turn 3×3 peek. Filters belief, doesn't change the board. |
| Stockfish | External engine. Black-box: FEN in → move out. |
| Majority vote | Run Stockfish on every belief, play most-common answer (random tiebreak). |
| POMDP | Formal model: agent acts on hidden state, sees only observations. |
| Information gain | Expected drop in belief-set entropy from an observation. The math behind smart sensing. |
| POSG | POMDP + adversary (you're playing one of these, technically). |
