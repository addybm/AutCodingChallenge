"""peel() happy-path, parameters, and delayed-but-successful cycles."""

import time

import pytest

from conftest import Delay


def test_normal_peel_writes_command_and_returns(make_driver):
    dev, conn = make_driver(responses=["*ack:", "*ready:00,00,00"])
    ready = dev.peel()
    assert ready == "*ready:00,00,00"
    # Default parameters map to the documented example command.
    assert conn.written == [b"*xpeel:41\r\n"]


def test_peel_uses_custom_parameters(make_driver):
    dev, conn = make_driver(responses=["*ack:", "*ready:00,00,00"])
    dev.peel(param_set=3, adhere_time=2)
    assert conn.written == [b"*xpeel:32\r\n"]


def test_ack_is_not_treated_as_completion(make_driver):
    # The overlap trap: *ack must not end the call; only *ready does. With a
    # real motion delay between them, peel() must block through the delay.
    dev, _ = make_driver(
        responses=["*ack:", Delay(0.15), "*ready:00,00,00"],
        peel_timeout=1.0,
    )
    start = time.monotonic()
    assert dev.peel() == "*ready:00,00,00"
    assert time.monotonic() - start >= 0.12  # actually waited for the peel


def test_delayed_peel_completes_before_deadline(make_driver):
    dev, _ = make_driver(
        responses=["*ack:", Delay(0.1), "*ready:00,00,00"],
        peel_timeout=0.5,
    )
    assert dev.peel() == "*ready:00,00,00"


@pytest.mark.parametrize("bad_param_set", [0, 10, -1])
def test_invalid_param_set_raises(make_driver, bad_param_set):
    dev, _ = make_driver(responses=["*ack:", "*ready:00,00,00"])
    with pytest.raises(ValueError):
        dev.peel(param_set=bad_param_set)


@pytest.mark.parametrize("bad_adhere", [0, 5])
def test_invalid_adhere_time_raises(make_driver, bad_adhere):
    dev, _ = make_driver(responses=["*ack:", "*ready:00,00,00"])
    with pytest.raises(ValueError):
        dev.peel(adhere_time=bad_adhere)
