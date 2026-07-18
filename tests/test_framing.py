"""Frame reassembly: a message split across reads must be stitched together."""

from conftest import Raw


def test_fragmented_ready_is_reassembled(make_driver):
    # The *ready line arrives in three partial reads (no terminator until the
    # last). The driver must reassemble it into one line, not misparse fragments.
    dev, _ = make_driver(
        responses=["*ack:", Raw(b"*re"), Raw(b"ady:00,"), Raw(b"00,00\r\n")],
        peel_timeout=0.5,
    )
    assert dev.peel() == "*ready:00,00,00"


def test_fragmented_tape_is_reassembled(make_driver):
    dev, _ = make_driver(
        responses=[Raw(b"*tape:11"), Raw(b",13\r\n"), "*ready:00,00,00"],
        query_timeout=0.5,
    )
    assert dev.tape_left() == (110, 130)
