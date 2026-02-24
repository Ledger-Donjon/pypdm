import struct
import pytest

from pypdm.pdm import PDM, Link, Command, Mode, Status
from conftest import FakeSerial
from typing import Callable, cast
import types


def version_resp(
    v_major: int, v_minor: int, make_response: Callable[[int, bytes], bytes]
) -> bytes:
    # DATA: U08_X, U08_Y
    return make_response(Status.OK.value, bytes([v_major, v_minor]))


def test_read_protocol_version(fake_serial_factory: types.SimpleNamespace) -> None:
    # 1) __init__ will read the version -> provide a first response
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    fs.queue_response(version_resp(3, 4, fake_serial_factory.make_response))
    pdm = PDM(1, link)
    # 2) explicit read -> provide a second response
    fs.queue_response(version_resp(3, 4, fake_serial_factory.make_response))
    version = pdm.read_protocol_version()
    assert version == "3.4"
    # 3) __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)


def test_read_address_uses_address_zero(
    fake_serial_factory: types.SimpleNamespace,
) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # __init__ version handshake
    fs.queue_response(version_resp(3, 4, fake_serial_factory.make_response))
    pdm = PDM(7, link)
    # Response for READ_ADDRESS: DATA0=U08_ADD
    fs.queue_response(fake_serial_factory.make_response(Status.OK.value, bytes([5])))  # type: ignore
    addr = pdm.read_address()
    assert addr == 5
    # Verify that the sent frame used ADD=0
    # The last write corresponds to READ_ADDRESS
    frame = fs.writes[-1]
    assert frame[1] == 0  # ADD
    assert frame[2] == Command.READ_ADDRESS.value
    # __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)


def test_mode_from_read_cw_pulse(fake_serial_factory: types.SimpleNamespace) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # __init__ handshake
    fs.queue_response(version_resp(3, 4, fake_serial_factory.make_response))
    pdm = PDM(1, link)
    # Response for READ_CW_PULSE: DATA0=STATE (0=pulsed, 1=continuous)
    fs.queue_response(fake_serial_factory.make_response(0x00, bytes([1])))
    assert pdm.mode == Mode.CONTINUOUS
    fs.queue_response(fake_serial_factory.make_response(0x00, bytes([0])))
    assert pdm.mode == Mode.PULSED
    # __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)


def test_offset_current_read_and_write(
    fake_serial_factory: types.SimpleNamespace,
) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # __init__ handshake
    fs.queue_response(version_resp(3, 4, fake_serial_factory.make_response))
    pdm = PDM(1, link)

    # Read: return big-endian F32 12.5
    fs.queue_response(fake_serial_factory.make_response(0x00, struct.pack(">f", 12.5)))
    assert pytest.approx(pdm.offset_current, rel=1e-6) == 12.5  # type: ignore

    # Write: verify WRITE_INSTRUCTION (0x10) with U16 id + F32
    fs.queue_response(fake_serial_factory.make_response(Status.OK.value))
    pdm.offset_current = 10.0
    frame = fs.writes[-1]
    assert frame[2] == Command.WRITE_INSTRUCTION.value
    # DATA = U16 instruction id (15) + F32
    data = frame[3:-1]  # without checksum
    assert data[:2] == (15).to_bytes(2, "big")
    assert data[2:] == struct.pack(">f", 10.0)
    # __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)
