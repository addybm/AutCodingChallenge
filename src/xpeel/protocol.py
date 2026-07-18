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
