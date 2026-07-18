"""Exception hierarchy for the XPeel driver.

All driver errors derive from :class:`XPeelError` so callers can catch a single
base class when the specific failure mode does not matter.
"""

from __future__ import annotations


class XPeelError(Exception):
    """Base class for all XPeel driver errors."""


class XPeelConnectionError(XPeelError):
    """The serial port could not be opened (wraps ``serial.SerialException``)."""


class XPeelTimeoutError(XPeelError):
    """The device did not respond within the expected time window."""


class XPeelProtocolError(XPeelError):
    """A received message was malformed or unexpected."""
