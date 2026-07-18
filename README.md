# XPeel Driver

A small Python driver for the Azenta / Brooks **XPeel** automated microplate seal
remover, which speaks an ASCII command/response protocol over RS-232 (`9600,8,N,1`).

- `peel(param_set=4, adhere_time=1)` — run a peel cycle; blocks until the plate is peeled.
- `tape_left()` — remaining tape as `(supply, take_up)` counts in deseals.

## Setup & Run

Prerequisites: **Python 3.9+** and `git`. (Verified from scratch on Python 3.9.6.)

```bash
git clone <your-repo-url> && cd <cloned-dir>
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # installs pyserial (runtime) + pytest (dev)
pytest -q                          # 43 tests, ~1s
```

Usage:

```python
from xpeel import XPeel

dev = XPeel(port="/dev/ttyUSB0")   # opens 9600,8,N,1 and drains startup messages
dev.peel()                         # default *xpeel:41; blocks until *ready
supply, take_up = dev.tape_left()  # e.g. (110, 130); (None, None) if unknown
dev.close()
```

## Assumptions

- Target **Python 3.9+**; deps are `pyserial` (runtime) and `pytest` (dev).
- Usually attaching to an already-initialized device; init drains any pending
  unsolicited startup messages before the first command.
- `peel()` raises on a nonzero device error code (a failed peel should surface,
  not pass silently). `adhere_time` uses the manual's `B` enum (`1-4`).
- Tests use an injected fake serial port.

## Design decisions & tradeoffs

- **`peel()` blocks until `*ready`, never on `*ack`.** `*ack` only means "command
  received", so we want to ensure we don't send more commands while the device is
  running.
- **Errors raise; the driver never retries or logs.** I chose not to retry the peel
  command ever, because it seems too dangerous for the driver to decide this; this
  seems more like a scheduler software-side call. I also decided to let a higher 
  level piece of code handle the logging so it can be more customizable for users, 
  and the driver can just raise different kinds of errors.
- **Timeouts** (all injectable): 60 s peel (adhere ≤10 s + motion), 5 s query
  (no motion), 0.2 s per-read; startup drain stops after 0.5 s idle, capped at 5 s.
  The driver enforces deadlines with a monotonic loop because pyserial read
  timeouts return empty rather than raising.

## Edge cases

Handled:
- **Broken read:** a line may be split due to a timeout mid-read. this was 
  addressed by reassembling into one cohesive message instead of 2.
- **Steady-state unsolicited messages (C1):** a front-panel button press emits
  `*manual`/`*xpeel`/`*setup`/`*ready` on its own; these are skipped mid-command
  and their terminal `*ready` is not mistaken for ours (so a device busy with a
  manual op correctly times out rather than reporting false success).
- Unsolicited **startup broadcast** are drained on init, but I decided to keep
  them stored in `startup_messages`, in case that could be useful for debugging
  later.
- Malformed responses and `*ack`-without-`*ready` each raise a distinct error.

## With more time, I would:

- Inspect the stored `startup_messages` for embedded error codes (e.g. a startup
  `*ready` reporting cover-open) and decide how to surface/handle them.
- Look into more situations where some manual interference may affect the
  instrument
- In my experience with XPeel, I have seen seals that are not fully peeled and
  require manual inspection. I would consider ways in which the Driver could
  help enable this manual inspection step.
