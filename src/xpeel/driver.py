"""High-level driver for the Azenta / Brooks XPeel plate seal remover."""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

import serial

from xpeel import protocol
from xpeel.exceptions import (
    XPeelConnectionError,
    XPeelProtocolError,
    XPeelTimeoutError,
)

DEFAULT_BAUDRATE = 9600

# Small per-read serial timeout; the real command deadline is enforced by a
# monotonic loop, since pyserial read timeouts return empty rather than raising.
DEFAULT_READ_TIMEOUT = 0.2

# Generous headroom for a full cycle (up to 10s adhere plus mechanism motion).
PEEL_TIMEOUT = 60.0

# Quick queries that involve no mechanism motion (e.g. tape remaining).
QUERY_TIMEOUT = 5.0


class XPeel:
    """Driver for a single XPeel instrument over RS-232.

    Args:
        port: Serial device name (e.g. ``"/dev/ttyUSB0"``). Opened at 9600,8,N,1.
        connection: A pre-built serial-like object to use instead of opening a
            port; enables testing without hardware.
        baudrate: Serial baud rate (defaults to 9600).
        read_timeout: Per-read serial timeout in seconds.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        *,
        connection: Optional[object] = None,
        baudrate: int = DEFAULT_BAUDRATE,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
    ) -> None:
        if connection is None and port is None:
            raise ValueError("Provide either a 'port' to open or a 'connection'.")
        self._read_timeout = read_timeout
        if connection is not None:
            self._conn = connection
        else:
            self._conn = self._open(port, baudrate, read_timeout)

    @staticmethod
    def _open(port: str, baudrate: int, read_timeout: float):
        try:
            return serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=read_timeout,
            )
        except serial.SerialException as exc:
            raise XPeelConnectionError(
                f"Could not open serial port {port!r}: {exc}"
            ) from exc

    def close(self) -> None:
        """Close the underlying serial connection."""
        if self._conn is not None:
            self._conn.close()

    # -- low-level I/O -----------------------------------------------------

    def _read_message(self) -> str:
        """Read one framed line, stripped; "" if nothing arrived before timeout."""
        raw = self._conn.read_until(protocol.READ_TERMINATOR)
        if not raw:
            return ""
        return raw.decode(protocol.ENCODING, errors="replace").strip()

    def _run_command(
        self, body: str, ready_timeout: float
    ) -> Tuple[List[str], str]:
        """Send a command and block until the terminal ``*ready`` response.

        Returns ``(data_lines, ready_line)`` where ``data_lines`` are any
        intermediate payload lines (e.g. ``*tape:...``) received before ready;
        ``*ack`` is treated as a receipt only. Raises
        :class:`XPeelTimeoutError` if no ``*ready`` arrives in time.
        """
        self._conn.write(protocol.build_command(body))
        deadline = time.monotonic() + ready_timeout
        data_lines: List[str] = []
        while time.monotonic() < deadline:
            line = self._read_message()
            if not line:
                continue
            if protocol.is_ready(line):
                return data_lines, line
            if protocol.is_ack(line):
                continue
            data_lines.append(line)
        raise XPeelTimeoutError(
            f"No *ready response for command '*{body}' within {ready_timeout}s."
        )

    # -- public commands ---------------------------------------------------

    def peel(self, param_set: int = 4, adhere_time: int = 1) -> str:
        """Trigger a peel cycle and block until the plate has been peeled.

        Args:
            param_set: ``A`` in ``*xpeel:AB`` -- the parameter set (1-9)
                selecting begin-peel location and speed.
            adhere_time: ``B`` in ``*xpeel:AB`` -- the adhere-time code
                (1=2.5s, 2=5s, 3=7.5s, 4=10s).

        Defaults produce ``*xpeel:41``. Raises ``ValueError`` for out-of-range
        parameters.
        """
        if param_set not in protocol.PARAM_SETS:
            raise ValueError(
                f"param_set must be in {protocol.PARAM_SETS.start}-"
                f"{protocol.PARAM_SETS.stop - 1}, got {param_set!r}."
            )
        if adhere_time not in protocol.ADHERE_TIMES:
            raise ValueError(
                f"adhere_time must be one of {sorted(protocol.ADHERE_TIMES)}, "
                f"got {adhere_time!r}."
            )
        _, ready = self._run_command(
            f"xpeel:{param_set}{adhere_time}", ready_timeout=PEEL_TIMEOUT
        )
        return ready

    def tape_left(self) -> Tuple[Optional[int], Optional[int]]:
        """Report remaining tape as (supply, take-up) counts in *deseals*.

        ``supply`` is the peel operations left on the supply spool; ``take-up``
        is the room left on the collection spool. Returns ``(None, None)`` when
        the device reports the unknown state (``99,99``, before the first peel).
        """
        data_lines, _ = self._run_command("tapeleft", ready_timeout=QUERY_TIMEOUT)
        for line in data_lines:
            if protocol.is_tape(line):
                return protocol.parse_tape(line)
        raise XPeelProtocolError(
            f"No *tape response received; got {data_lines!r}."
        )
