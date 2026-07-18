"""High-level driver for the Azenta / Brooks XPeel plate seal remover."""

from __future__ import annotations

import time
from typing import Optional

import serial

from xpeel import protocol
from xpeel.exceptions import XPeelConnectionError, XPeelTimeoutError

DEFAULT_BAUDRATE = 9600

# Small per-read serial timeout; the real command deadline is enforced by a
# monotonic loop, since pyserial read timeouts return empty rather than raising.
DEFAULT_READ_TIMEOUT = 0.2

# Generous headroom for a full cycle (up to 10s adhere plus mechanism motion).
PEEL_TIMEOUT = 60.0


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

    def _run_command(self, body: str, ready_timeout: float) -> str:
        """Send a command and block until the terminal ``*ready`` response.

        Intermediate lines (notably ``*ack``) are skipped; only ``*ready`` ends
        the wait. Raises :class:`XPeelTimeoutError` on no ``*ready`` in time.
        """
        self._conn.write(protocol.build_command(body))
        deadline = time.monotonic() + ready_timeout
        while time.monotonic() < deadline:
            line = self._read_message()
            if not line:
                continue
            if protocol.is_ready(line):
                return line
        raise XPeelTimeoutError(
            f"No *ready response for command '*{body}' within {ready_timeout}s."
        )

    # -- public commands ---------------------------------------------------

    def peel(self) -> str:
        """Trigger a peel cycle and block until the plate has been peeled."""
        return self._run_command("xpeel:41", ready_timeout=PEEL_TIMEOUT)
