"""Shared test doubles and fixtures for the XPeel driver suite.

The star here is :class:`FakeSerial`, a timing-aware stand-in for
``serial.Serial``. It replays a scripted sequence of lines and *delays* so tests
can model a real peel cycle -- the device acknowledges immediately, stays silent
for a while (motion), then reports ``*ready`` -- and exercise the driver's real
monotonic-deadline timeout logic without any hardware.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Union

import pytest

from xpeel import XPeel


@dataclass
class Delay:
    """A scripted pause: the device emits nothing for ``seconds``."""

    seconds: float


@dataclass
class Raw:
    """Raw bytes returned by a single ``read_until`` call, verbatim.

    Used to model a fragmented read: a partial line (no terminator) that a real
    serial timeout would hand back before the rest of the message arrives.
    """

    data: bytes


ScriptItem = Union[str, Delay, Raw]


# Short, injected timeouts so the suite runs fast while still driving the real
# deadline logic. Failure cases use a peel_timeout smaller than the scripted
# delay; success cases use one larger than the delay.
FAST_TIMEOUTS = dict(
    peel_timeout=0.2,
    query_timeout=0.2,
    drain_idle_timeout=0.02,
    drain_max_time=0.2,
)


class FakeSerial:
    """A scripted, timing-aware serial stand-in.

    Two scripts are consumed in order:

    * ``startup`` -- lines already on the line at construction, delivered
      immediately. The driver drains these during ``__init__``.
    * ``responses`` -- the reply to a command; delivered only *after* the first
      ``write`` (mirroring the device, which stays silent until commanded).

    Either script may contain :class:`Delay` items to model motion time.

    ``read_until`` mimics pyserial: it blocks at most ``timeout`` seconds and
    returns whatever is available -- ``b""`` on timeout, never raising.
    """

    def __init__(
        self,
        startup: Optional[List[ScriptItem]] = None,
        responses: Optional[List[ScriptItem]] = None,
        timeout: float = 0.02,
    ) -> None:
        self.timeout = timeout
        self._startup: List[ScriptItem] = list(startup or [])
        self._responses: List[ScriptItem] = list(responses or [])
        self._armed = False
        self._pending_delay = 0.0
        self.written: List[bytes] = []
        self.closed = False

    def _current_queue(self) -> Optional[List[ScriptItem]]:
        if self._startup:
            return self._startup
        if self._armed:
            return self._responses
        return None

    def read_until(self, expected: bytes = b"\n", size=None) -> bytes:
        budget = self.timeout if self.timeout is not None else 0.0
        start = time.monotonic()
        while True:
            if self._pending_delay > 0:
                remaining_budget = budget - (time.monotonic() - start)
                if remaining_budget <= 0:
                    return b""
                nap = min(self._pending_delay, remaining_budget)
                time.sleep(nap)
                self._pending_delay -= nap
                if self._pending_delay > 1e-9:
                    return b""  # read budget spent mid-delay
                self._pending_delay = 0.0
                continue

            queue = self._current_queue()
            if not queue:
                # Line is quiet: wait out the remaining budget like a real port.
                remaining = budget - (time.monotonic() - start)
                if remaining > 0:
                    time.sleep(remaining)
                return b""

            item = queue.pop(0)
            if isinstance(item, Delay):
                self._pending_delay = item.seconds
                continue
            if isinstance(item, Raw):
                return item.data
            line = item if item.endswith("\r\n") else item + "\r\n"
            return line.encode("ascii")

    def write(self, data: bytes) -> int:
        self.written.append(data)
        self._armed = True
        return len(data)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def make_driver():
    """Factory building an :class:`XPeel` over a :class:`FakeSerial`.

    Usage::

        dev, conn = make_driver(responses=["*ack:", "*ready:00,00,00"])

    ``startup`` scripts the init-drain burst; ``responses`` scripts the command
    reply. Fast timeouts are applied by default and may be overridden via kwargs.
    """
    created: List[XPeel] = []

    def _make(responses=None, startup=None, timeout=0.02, **kwargs):
        conn = FakeSerial(startup=startup, responses=responses, timeout=timeout)
        options = {**FAST_TIMEOUTS, **kwargs}
        dev = XPeel(connection=conn, **options)
        created.append(dev)
        return dev, conn

    yield _make

    for dev in created:
        dev.close()
