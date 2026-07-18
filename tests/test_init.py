"""Initialization and startup-drain behavior."""

import pytest

from xpeel import XPeel


def test_requires_port_or_connection():
    with pytest.raises(ValueError):
        XPeel()


def test_startup_burst_is_drained(make_driver):
    dev, conn = make_driver(
        startup=["*poweron", "*homing", "*ready:00,00,00"],
        responses=["*ack:", "*ready:00,00,00"],
    )
    # The power-up broadcast is consumed (and retained) during construction...
    assert dev.startup_messages == ["*poweron", "*homing", "*ready:00,00,00"]
    # ...and does not corrupt the first real command.
    assert dev.peel() == "*ready:00,00,00"
    assert conn.written == [b"*xpeel:41\r\n"]


def test_idle_device_has_no_startup_messages(make_driver):
    dev, _ = make_driver(responses=["*ack:", "*ready:00,00,00"])
    assert dev.startup_messages == []


def test_drain_stops_early_on_ready(make_driver):
    # A trailing line after *ready must survive the drain (drain exits at *ready).
    dev, conn = make_driver(
        startup=["*poweron", "*ready:00,00,00"],
        responses=["*ack:", "*ready:00,00,00"],
    )
    assert dev.startup_messages == ["*poweron", "*ready:00,00,00"]
    assert dev.peel() == "*ready:00,00,00"
