"""Unit tests for the pure protocol helpers (no I/O)."""

import pytest

from xpeel import protocol
from xpeel.exceptions import XPeelProtocolError


def test_build_command_frames_body():
    assert protocol.build_command("xpeel:41") == b"*xpeel:41\r\n"


@pytest.mark.parametrize(
    "line, expected",
    [("*ack", True), ("*ack:", True), ("*ready:00,00,00", False), ("*tape:1,2", False)],
)
def test_is_ack(line, expected):
    assert protocol.is_ack(line) is expected


def test_parse_ready_extracts_codes():
    assert protocol.parse_ready("*ready:01,07,00") == (1, 7, 0)


@pytest.mark.parametrize("bad", ["*ready:1,2,3", "*ready:00,00", "ready:00,00,00", ""])
def test_parse_ready_rejects_malformed(bad):
    with pytest.raises(XPeelProtocolError):
        protocol.parse_ready(bad)


def test_parse_tape_scales_by_ten():
    assert protocol.parse_tape("*tape:11,13") == (110, 130)


def test_parse_tape_unknown_sentinel():
    assert protocol.parse_tape("*tape:99,99") == (None, None)


def test_parse_tape_lone_99_is_literal():
    # Only 99,99 means "unknown"; a lone 99 is treated as a real reading (x10).
    assert protocol.parse_tape("*tape:99,13") == (990, 130)


def test_describe_error_code_known_and_unknown():
    assert protocol.describe_error_code(4) == "Seal not removed"
    assert "Unknown error code" in protocol.describe_error_code(77)
