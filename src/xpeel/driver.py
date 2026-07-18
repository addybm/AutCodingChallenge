"""High-level driver for the Azenta / Brooks XPeel plate seal remover."""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

import serial

from xpeel import protocol
from xpeel.exceptions import (
    XPeelAckTimeoutError,
    XPeelConnectionError,
    XPeelDeviceError,
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

# Init drain: stop once the line has been quiet this long, bounded by an overall
# cap so a chatty/misbehaving device cannot block construction indefinitely.
DRAIN_IDLE_TIMEOUT = 0.5
DRAIN_MAX_TIME = 5.0


class XPeel:
    """Driver for a single XPeel instrument over RS-232.

    Args:
        port: Serial device name (e.g. ``"/dev/ttyUSB0"``). Opened at 9600,8,N,1.
        connection: A pre-built serial-like object to use instead of opening a
            port; enables testing without hardware.
        baudrate: Serial baud rate (defaults to 9600).
        read_timeout: Per-read serial timeout in seconds.
        peel_timeout: Deadline for a full peel cycle to reach ``*ready``.
        query_timeout: Deadline for a quick query (e.g. tape remaining).
        drain_idle_timeout: Startup drain stops after the line is quiet this long.
        drain_max_time: Absolute cap on the startup drain.

    The timeout arguments default to the module-level constants and exist mainly
    so callers (and tests) can tune or shorten them.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        *,
        connection: Optional[object] = None,
        baudrate: int = DEFAULT_BAUDRATE,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        peel_timeout: float = PEEL_TIMEOUT,
        query_timeout: float = QUERY_TIMEOUT,
        drain_idle_timeout: float = DRAIN_IDLE_TIMEOUT,
        drain_max_time: float = DRAIN_MAX_TIME,
    ) -> None:
        if connection is None and port is None:
            raise ValueError("Provide either a 'port' to open or a 'connection'.")
        self._read_timeout = read_timeout
        self._peel_timeout = peel_timeout
        self._query_timeout = query_timeout
        self._drain_idle_timeout = drain_idle_timeout
        self._drain_max_time = drain_max_time
        # Holds an incomplete (not yet newline-terminated) frame between reads, so
        # a message split across read timeouts is reassembled rather than parsed
        # as two broken lines.
        self._rx_buffer = b""
        # Unsolicited startup messages consumed during construction, kept for
        # inspection/debugging.
        self.startup_messages: List[str] = []
        if connection is not None:
            self._conn = connection
        else:
            self._conn = self._open(port, baudrate, read_timeout)
        self._drain_unsolicited()

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
        """Read one complete framed line, stripped.

        A single read may time out mid-message and return a partial fragment
        (bytes not ending in the terminator). Such fragments are retained in a
        buffer and completed on later calls, so a line split across reads is
        reassembled instead of being parsed as two broken lines. Returns ``""``
        when no complete line is available yet.
        """
        self._rx_buffer += self._conn.read_until(protocol.READ_TERMINATOR)
        if not self._rx_buffer.endswith(protocol.READ_TERMINATOR):
            return ""  # still mid-frame; keep the partial for the next read
        line = self._rx_buffer
        self._rx_buffer = b""
        return line.decode(protocol.ENCODING, errors="replace").strip()

    def _drain_unsolicited(self) -> None:
        """Consume any unsolicited messages already on the line before commands.

        On power-up the device broadcasts ``*poweron``/``*homing``/``*ready``;
        a device that has been idle sends nothing. We consume whatever is
        present (retaining a copy in ``startup_messages``) until either a
        terminal ``*ready`` is seen or the line has been quiet for
        ``drain_idle_timeout``, bounded by ``drain_max_time``.
        """
        hard_deadline = time.monotonic() + self._drain_max_time
        last_activity = time.monotonic()
        while time.monotonic() < hard_deadline:
            line = self._read_message()
            if line:
                self.startup_messages.append(line)
                last_activity = time.monotonic()
                # The startup broadcast ends with *ready -> line is now idle.
                if protocol.is_ready(line):
                    return
                continue
            if time.monotonic() - last_activity >= self._drain_idle_timeout:
                return

    def _run_command(
        self, body: str, ready_timeout: float
    ) -> Tuple[List[str], str]:
        """Send a command and block until the terminal ``*ready`` response.

        Returns ``(data_lines, ready_line)`` where ``data_lines`` are any
        intermediate payload lines (e.g. ``*tape:...``) received before ready;
        ``*ack`` is treated as a receipt only.

        Raises :class:`XPeelAckTimeoutError` if an ``*ack`` was seen but no
        ``*ready`` followed in time, and :class:`XPeelTimeoutError` if nothing
        usable arrived at all.

        Unsolicited messages that appear mid-session (a human pressing the
        front-panel button, or a power-up/restart broadcast) are skipped, and the
        ``*ready`` that terminates such a sequence is not mistaken for ours.
        """
        self._conn.write(protocol.build_command(body))
        deadline = time.monotonic() + ready_timeout
        data_lines: List[str] = []
        saw_ack = False
        pending_unsolicited_ready = False
        while time.monotonic() < deadline:
            line = self._read_message()
            if not line:
                continue
            if protocol.is_ready(line):
                if pending_unsolicited_ready:
                    # Terminal *ready of an unsolicited op, not our command's.
                    pending_unsolicited_ready = False
                    continue
                return data_lines, line
            if protocol.is_ack(line):
                saw_ack = True
                continue
            if protocol.is_unsolicited(line):
                if protocol.starts_unsolicited_ready(line):
                    pending_unsolicited_ready = True
                continue
            data_lines.append(line)
        if saw_ack:
            raise XPeelAckTimeoutError(
                f"Received *ack but no *ready for command '*{body}' "
                f"within {ready_timeout}s."
            )
        raise XPeelTimeoutError(
            f"No response for command '*{body}' within {ready_timeout}s."
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
        parameters and :class:`XPeelDeviceError` if the device reports a nonzero
        error code (e.g. seal not removed, out of tape).
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
            f"xpeel:{param_set}{adhere_time}", ready_timeout=self._peel_timeout
        )
        self._raise_for_error_codes(ready)
        return ready

    @staticmethod
    def _raise_for_error_codes(ready_line: str) -> None:
        """Raise :class:`XPeelDeviceError` if a motion ``*ready`` reports errors.

        Only meaningful for motion commands: for query commands the ``*ready``
        error fields carry codes from the *previous* motion, so callers of those
        commands must not use this.
        """
        codes = protocol.parse_ready(ready_line)
        failed = [code for code in codes if code != 0]
        if failed:
            raise XPeelDeviceError(
                failed, [protocol.describe_error_code(code) for code in failed]
            )

    def tape_left(self) -> Tuple[Optional[int], Optional[int]]:
        """Report remaining tape as (supply, take-up) counts in *deseals*.

        ``supply`` is the peel operations left on the supply spool; ``take-up``
        is the room left on the collection spool. Returns ``(None, None)`` when
        the device reports the unknown state (``99,99``, before the first peel).

        The trailing ``*ready`` error fields are intentionally ignored: for query
        commands they carry codes from the *previous* motion, not this query.
        """
        data_lines, _ = self._run_command(
            "tapeleft", ready_timeout=self._query_timeout
        )
        for line in data_lines:
            if protocol.is_tape(line):
                return protocol.parse_tape(line)
        raise XPeelProtocolError(
            f"No *tape response received; got {data_lines!r}."
        )
