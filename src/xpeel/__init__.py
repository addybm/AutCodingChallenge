"""Python driver for the Azenta / Brooks XPeel automated plate seal remover."""

from xpeel.driver import XPeel
from xpeel.exceptions import (
    XPeelConnectionError,
    XPeelError,
    XPeelProtocolError,
    XPeelTimeoutError,
)

__all__ = [
    "XPeel",
    "XPeelError",
    "XPeelConnectionError",
    "XPeelTimeoutError",
    "XPeelProtocolError",
]

__version__ = "0.1.0"
