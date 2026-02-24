
import pytest

from pypdm.pdm import Link, Command, StatusError, ChecksumError, ProtocolError, Status
import types
from typing import cast
from conftest import FakeSerial


def test_send_frame_and_checksum(fake_serial_factory: types.SimpleNamespace) -> None:
    # Prepare a minimal OK response (LEN=3, STS=0x00)
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    fs.queue_response(fake_serial_factory.OK_RESP)
    link.command(1, Command.READ_PROTOCOL_VERSION, b"")

    assert len(fs.writes) == 1
    frame = fs.writes[0]
    # LEN, ADD, CMD, CHK
    assert len(frame) == 4
    assert frame[0] == 4
    assert frame[1] == 1
    assert frame[2] == Command.READ_PROTOCOL_VERSION.value
    # Verify XOR-1 checksum
    chk = fake_serial_factory.calc_chk(frame[:-1])
    assert frame[-1] == chk


def test_status_error_timeout(fake_serial_factory: types.SimpleNamespace) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # TIMEOUT status response (0x01), LEN=3
    fs.queue_response(fake_serial_factory.make_response(Status.TIMEOUT.value))
    with pytest.raises(StatusError) as ei:
        link.command(1, Command.READ_PROTOCOL_VERSION, b"")
    assert int(ei.value.status) == 0x01


def test_checksum_error_detected(fake_serial_factory: types.SimpleNamespace) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # Build a response with a wrong checksum
    body = bytearray([3, Status.OK.value])  # LEN=3, STS=0x00, no data
    bad_chk = (fake_serial_factory.calc_chk(bytes(body)) + 1) % 256  # make it wrong
    body.append(bad_chk)
    fs.queue_response(bytes(body))
    with pytest.raises(ChecksumError):
        link.command(1, Command.READ_PROTOCOL_VERSION, b"")


def test_protocol_error_on_short_length(fake_serial_factory: types.SimpleNamespace) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # LEN=2 (less than 3) -> ProtocolError
    # The code first reads 1 byte (LEN), then validates.
    fs.queue_response(bytes([2]))
    with pytest.raises(ProtocolError):
        link.command(1, Command.READ_PROTOCOL_VERSION, b"")


