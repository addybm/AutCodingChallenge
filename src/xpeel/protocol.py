"""Wire-level constants and helpers for the XPeel serial protocol.

Messages are ASCII, begin with ``*`` and end with ``<CR><LF>``. A motion command
is answered with ``*ack`` (received) and later ``*ready`` (completed).
"""

from __future__ import annotations

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
