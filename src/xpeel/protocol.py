"""Wire-level constants and helpers for the XPeel serial protocol.

Messages are ASCII, begin with ``*`` and end with ``<CR><LF>``. A motion command
is answered with ``*ack`` (received) and later ``*ready`` (completed).
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from xpeel.exceptions import XPeelProtocolError

ENCODING = "ascii"

MESSAGE_PREFIX = "*"
COMMAND_TERMINATOR = "\r\n"

# Lines end in CRLF, so reading up to LF yields one complete line.
READ_TERMINATOR = b"\n"

# Parameters for the ``*xpeel:AB`` command.
# A: parameter set (begin-peel location + speed), 1-9.
PARAM_SETS = range(1, 10)
# B: adhere time, encoded 1-4 and mapping to seconds.
ADHERE_TIMES = {1: 2.5, 2: 5.0, 3: 7.5, 4: 10.0}


def build_command(body: str) -> bytes:
    """Frame a command body into wire bytes, e.g. ``"xpeel:41" -> b"*xpeel:41\\r\\n"``."""
    return f"{MESSAGE_PREFIX}{body}{COMMAND_TERMINATOR}".encode(ENCODING)


def normalize(line: str) -> str:
    """Strip surrounding whitespace from a received line."""
    return line.strip()


def is_ack(line: str) -> bool:
    """True for an acknowledgement (``*ack`` or ``*ack:``)."""
    return normalize(line).startswith("*ack")


def is_ready(line: str) -> bool:
    """True for a terminal ready response (``*ready:...``)."""
    return normalize(line).startswith("*ready")


def is_tape(line: str) -> bool:
    """True for a tape-remaining response (``*tape:SS,TT``)."""
    return normalize(line).startswith("*tape:")


# ``*tape:SS,TT`` -- SS/TT are counts; 99 is the "unknown" sentinel.
_TAPE_RE = re.compile(r"^\*tape:(\d+),(\d+)$")
TAPE_UNKNOWN = 99
TAPE_MULTIPLIER = 10


def parse_tape(line: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse ``*tape:SS,TT`` into (supply, take-up) counts in *deseals*.

    The manual documents ``99,99`` as the "unknown" reading reported on power-up
    until the first peel completes; that case returns ``(None, None)``. Any other
    reading multiplies each field by 10 to give the number of peel operations.
    """
    match = _TAPE_RE.match(normalize(line))
    if match is None:
        raise XPeelProtocolError(f"Malformed tape response: {line!r}")
    supply_raw, takeup_raw = int(match.group(1)), int(match.group(2))
    if supply_raw == TAPE_UNKNOWN and takeup_raw == TAPE_UNKNOWN:
        return None, None
    return supply_raw * TAPE_MULTIPLIER, takeup_raw * TAPE_MULTIPLIER


# ``*ready:XX,XX,XX`` -- up to three error codes from the previous motion.
_READY_RE = re.compile(r"^\*ready:(\d{2}),(\d{2}),(\d{2})$")

# Error-code table (manual p.56). ``00`` means "no error".
ERROR_CODES = {
    0: "No error",
    1: "Conveyor motor stalled",
    2: "Elevator motor stalled",
    3: "Take-up spool stalled",
    4: "Seal not removed",
    5: "Illegal command",
    6: "No plate found (plate check enabled)",
    7: "Out of tape, or tape broke",
    8: "Parameters not saved",
    9: "Stop button pressed while running",
    10: "Seal sensor unplugged or broken",
    20: "Less than 30 seals left on the supply roll",
    21: "Room for less than 30 seals on the take-up spool",
    51: "Emergency stop: power relay not settable (cover open or hardware fault)",
    52: "Circuitry fault detected: remove power",
}


def parse_ready(line: str) -> Tuple[int, int, int]:
    """Parse ``*ready:XX,XX,XX`` into its three integer error codes."""
    match = _READY_RE.match(normalize(line))
    if match is None:
        raise XPeelProtocolError(f"Malformed ready response: {line!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def describe_error_code(code: int) -> str:
    """Human-readable description for an error code, tolerant of unknown codes."""
    return ERROR_CODES.get(code, f"Unknown error code {code:02d}")


# Messages the device emits on its own, unprompted (manual p.51-52): the
# power-up/restart broadcast and front-panel ("manual") operation notices.
_UNSOLICITED_PREFIXES = ("*manual", "*setup", "*poweron", "*homing")
# These begin an unsolicited sequence that ends in its *own* ``*ready``.
_UNSOLICITED_READY_STARTS = ("*manual", "*poweron", "*homing")


def is_unsolicited(line: str) -> bool:
    """True for a message the device sends on its own, not as a command reply.

    Covers the front-panel notices (``*manual``/``*setup`` and the bare
    ``*xpeel`` that follows a manual button press -- note: no ``:AB``) and the
    power-up/restart broadcast (``*poweron``/``*homing``).
    """
    text = normalize(line)
    if text == "*xpeel":  # bare, no ":AB" -> a manual-op notice, not our command
        return True
    return text.startswith(_UNSOLICITED_PREFIXES)


def starts_unsolicited_ready(line: str) -> bool:
    """True if this line begins an unsolicited sequence terminated by ``*ready``.

    A front-panel action and the power-up/restart broadcast each end with their
    own ``*ready``; seeing one of these means the *next* ``*ready`` belongs to
    that sequence, not to a command we issued.
    """
    return normalize(line).startswith(_UNSOLICITED_READY_STARTS)
