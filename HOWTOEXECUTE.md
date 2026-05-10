# how to run this

hi team, quick guide for running and testing the bot. follow this once, then you're set.

## what's in the folder

- `oracle_bot.py` is the baseline RBC bot I wrote, this is the Part 4.1 deliverable (20% of the marks)
- `Ooracle.py` is the same code as `oracle_bot.py` but with comments on every method, read this one first if you want to understand what each callback does
- `replay.py` is a small script I wrote to step through a saved game in the terminal, more on this below
- `TODO.md` is the running list of what's left to do, please tick stuff off as you finish it
- `RBC_NOTES.md` is a doc with AI-generated notes explaining the game, I asked Claude to write it because I was struggling to wrap my head around the rules and the belief set, read Part A if you're new to RBC, Part B if you want the POMDP framing
- the 8 original modules from the brief (`rbc_state_representation.py`, `next_move_pred.py` etc) are mostly done, see `TODO.md` for the small bugs that are still open

## prerequisites

things you need installed before anything works:

- python 3.10 or newer
- pip
- stockfish (the chess engine the bot calls)
- the `reconchess` python library (the framework that runs the bots)
- the `python-chess` library (boards, FENs, moves)

install commands, run them in order:

- install the python libraries
  ```
  pip install python-chess reconchess setuptools
  ```
- install stockfish via apt
  ```
  sudo apt update
  sudo apt install -y stockfish
  ```
- check stockfish works
  ```
  stockfish --help | head -3
  ```
- set the env var so the bot can find stockfish (the bot reads `STOCKFISH_EXECUTABLE` from the environment)
  ```
  echo 'export STOCKFISH_EXECUTABLE=$(which stockfish)' >> ~/.bashrc
  source ~/.bashrc
  ```
- drop a symlink in the project folder, a couple of the older module files look for `./stockfish` locally
  ```
  ln -s "$(which stockfish)" ./stockfish
  ```
- sanity check the bot imports
  ```
  python3 -c "from oracle_bot import OracleBot; print('ok')"
  ```
  if you see `ok` you're done

## running a game

we only have two opponents to test against right now, both ship with the `reconchess` package:

- `reconchess.bots.random_bot` is the random baseline
- `reconchess.bots.trout_bot` is the stronger reference bot

the `rc-bot-match` command takes two args, first one plays white, second plays black:

- oracle as white vs random as black
  ```
  rc-bot-match oracle_bot.OracleBot reconchess.bots.random_bot
  ```
- oracle as white vs trout as black
  ```
  rc-bot-match oracle_bot.OracleBot reconchess.bots.trout_bot
  ```
- flip colors by swapping the order
  ```
  rc-bot-match reconchess.bots.random_bot oracle_bot.OracleBot
  ```

things to know:

- a single game takes about 1 to 3 minutes
- when it finishes a `.json` file appears in the folder, e.g. `OracleBot-RandomBot-white-2026_05_10-15_23_44.json`, that's the game history
- the winner gets printed in the terminal at the end

## stepping through a saved game

`rc-replay` (the one that ships with `reconchess`) was broken on my setup so I wrote `replay.py` as a backup.

- after `rc-bot-match` finishes, take the `.json` filename it created and run
  ```
  python3 replay.py OracleBot-RandomBot-white-2026_05_10-15_23_44.json
  ```
- it prints the board before each turn, the sense square, the requested move and the actual move that went through
- press enter to step to the next turn, ctrl+c to quit

if `rc-replay` happens to work for you, that one has a nicer web UI:
```
rc-replay OracleBot-RandomBot-white-2026_05_10-15_23_44.json
```

## running many games to count win rate

save this as `bench.sh` in the project folder, then `chmod +x bench.sh`:

```bash
#!/bin/bash
N=${1:-10}
WINS=0
for i in $(seq 1 $N); do
    rc-bot-match oracle_bot.OracleBot reconchess.bots.random_bot 2>&1 \
      | grep -qi "OracleBot won" && WINS=$((WINS+1))
    echo "game $i done, oracle wins so far: $WINS / $i"
done
echo "FINAL: $WINS / $N"
```

run `./bench.sh 20` to play 20 games and print a final score.

## a few team notes

- check `TODO.md` before starting work so we don't double up on anything
- if you change `oracle_bot.py` please run at least one game vs random before pushing, just to make sure nothing crashes
- the `stockfish` binary is gitignored, you have to install your own
- the `.json` game files pile up fast, feel free to delete them or gitignore them once you've replayed
- if `RBC_NOTES.md` says something wrong or unclear, just fix it, it's only notes
- the verbose `Ooracle.py` and the terse `oracle_bot.py` are kept in sync by hand, if you change one please change the other
