"""Error handling: timeouts, ack-without-ready, malformed, device error codes."""

import pytest

from xpeel import (
    XPeelAckTimeoutError,
    XPeelDeviceError,
    XPeelProtocolError,
    XPeelTimeoutError,
)

from conftest import Delay


def test_no_response_raises_timeout(make_driver):
    # Device never answers the command at all.
    dev, _ = make_driver(responses=[], peel_timeout=0.1)
    with pytest.raises(XPeelTimeoutError) as info:
        dev.peel()
    assert not isinstance(info.value, XPeelAckTimeoutError)


def test_busy_past_deadline_after_ack_raises_ack_timeout(make_driver):
    # Acknowledged, then stays busy longer than the deadline: distinct subclass.
    dev, _ = make_driver(responses=["*ack:", Delay(1.0)], peel_timeout=0.1)
    with pytest.raises(XPeelAckTimeoutError):
        dev.peel()


def test_device_error_code_raises_device_error(make_driver):
    dev, _ = make_driver(responses=["*ack:", "*ready:04,00,00"])
    with pytest.raises(XPeelDeviceError) as info:
        dev.peel()
    assert info.value.codes == [4]
    assert "Seal not removed" in info.value.descriptions[0]


def test_multiple_error_codes_are_reported(make_driver):
    dev, _ = make_driver(responses=["*ack:", "*ready:01,07,00"])
    with pytest.raises(XPeelDeviceError) as info:
        dev.peel()
    assert info.value.codes == [1, 7]


def test_malformed_ready_raises_protocol_error(make_driver):
    dev, _ = make_driver(responses=["*ack:", "*ready:0,0,0"])
    with pytest.raises(XPeelProtocolError):
        dev.peel()
