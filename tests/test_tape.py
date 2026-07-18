"""tape_left() parsing, the unknown sentinel, and stale-code handling."""

import pytest

from xpeel import XPeelProtocolError


def test_tape_left_returns_deseals(make_driver):
    dev, conn = make_driver(responses=["*tape:11,13", "*ready:00,00,00"])
    assert dev.tape_left() == (110, 130)
    assert conn.written == [b"*tapeleft\r\n"]


def test_tape_left_unknown_sentinel_returns_none(make_driver):
    dev, _ = make_driver(responses=["*tape:99,99", "*ready:00,00,00"])
    assert dev.tape_left() == (None, None)


def test_tape_left_ignores_stale_ready_error_codes(make_driver):
    # The query's *ready carries a prior motion's error (07); must not raise.
    dev, _ = make_driver(responses=["*tape:11,13", "*ready:07,00,00"])
    assert dev.tape_left() == (110, 130)


def test_tape_left_missing_tape_line_raises(make_driver):
    dev, _ = make_driver(responses=["*ready:00,00,00"])
    with pytest.raises(XPeelProtocolError):
        dev.tape_left()


def test_tape_left_malformed_tape_raises(make_driver):
    dev, _ = make_driver(responses=["*tape:bogus", "*ready:00,00,00"])
    with pytest.raises(XPeelProtocolError):
        dev.tape_left()
