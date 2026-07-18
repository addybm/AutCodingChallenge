"""Steady-state unsolicited messages (front-panel button, broadcasts).

A human pressing the front-panel button makes the device emit, on its own,
``*manual`` -> ``*xpeel``/``*setup`` -> ``*ready`` (manual p.51-52). None of that
is a reply to a command we sent, and its terminal ``*ready`` must not be mistaken
for our command's completion.
"""

import pytest

from xpeel import XPeelTimeoutError


def test_manual_op_ready_is_not_mistaken_for_ours(make_driver):
    # Device is busy with a front-panel peel, so our command is ignored (no ack).
    # We must NOT treat the manual op's *ready as success -> we time out instead.
    dev, _ = make_driver(
        responses=["*manual", "*xpeel", "*ready:00,00,00"],
        peel_timeout=0.15,
    )
    with pytest.raises(XPeelTimeoutError):
        dev.peel()


def test_manual_op_then_our_response_returns_ours(make_driver):
    # A front-panel op completes first, then our command's real ack + ready.
    dev, _ = make_driver(
        responses=[
            "*manual",
            "*xpeel",
            "*ready:00,00,00",   # the manual op's ready (must be skipped)
            "*ack:",
            "*ready:00,00,00",   # our command's ready
        ],
    )
    assert dev.peel() == "*ready:00,00,00"


def test_setup_button_sequence_is_skipped(make_driver):
    dev, _ = make_driver(
        responses=["*manual", "*setup", "*ready:00,00,00", "*ack:", "*ready:00,00,00"],
    )
    assert dev.peel() == "*ready:00,00,00"


def test_query_skips_unsolicited_before_tape(make_driver):
    dev, _ = make_driver(
        responses=[
            "*manual",
            "*xpeel",
            "*ready:00,00,00",   # manual op's ready (skipped)
            "*tape:11,13",
            "*ready:00,00,00",
        ],
    )
    assert dev.tape_left() == (110, 130)
