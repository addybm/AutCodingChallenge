"""Exception hierarchy for the XPeel driver.

All driver errors derive from :class:`XPeelError` so callers can catch a single
base class when the specific failure mode does not matter.
"""

from __future__ import annotations

from typing import List, Optional, Sequence


class XPeelError(Exception):
    """Base class for all XPeel driver errors."""


class XPeelConnectionError(XPeelError):
    """The serial port could not be opened (wraps ``serial.SerialException``)."""


class XPeelTimeoutError(XPeelError):
    """The device did not respond within the expected time window."""


class XPeelAckTimeoutError(XPeelTimeoutError):
    """The device acknowledged the command (``*ack``) but never sent ``*ready``.

    A subclass of :class:`XPeelTimeoutError` so callers may catch either the
    general timeout or this more specific "started but never finished" case.
    """


class XPeelProtocolError(XPeelError):
    """A received message was malformed or unexpected."""


class XPeelDeviceError(XPeelError):
    """The device reported one or more nonzero error codes in a ``*ready`` line.

    Attributes:
        codes: The nonzero error codes returned by the device.
        descriptions: Human-readable descriptions aligned with ``codes``.
    """

    def __init__(
        self,
        codes: Sequence[int],
        descriptions: Optional[Sequence[str]] = None,
        message: Optional[str] = None,
    ) -> None:
        self.codes: List[int] = list(codes)
        self.descriptions: List[str] = (
            list(descriptions) if descriptions is not None else []
        )
        if message is None:
            if self.descriptions:
                detail = ", ".join(
                    f"{code:02d} ({desc})"
                    for code, desc in zip(self.codes, self.descriptions)
                )
            else:
                detail = ", ".join(f"{code:02d}" for code in self.codes)
            message = f"Device reported error code(s): {detail}"
        super().__init__(message)
