import types
from typing import cast, Callable
import pytest

from pypdm.pdm import PDM, Link, Command, Mode, ControlMode, Status, ProtocolVersionNotSupported
from conftest import FakeSerial


def version_resp(
    v_major: int, v_minor: int, make_response: Callable[[int, bytes], bytes]
) -> bytes:
    return make_response(Status.OK.value, bytes([v_major, v_minor]))


def test_software_control_mode_read_and_write_protocol_3_7(
    fake_serial_factory: types.SimpleNamespace,
) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # __init__ handshake for protocol 3.7
    fs.queue_response(version_resp(3, 7, fake_serial_factory.make_response))
    pdm = PDM(1, link)

    # Getter: READ_INSTRUCTION SOFTWARE_CONTROL_MODE -> returns U08 mode
    fs.queue_response(fake_serial_factory.make_response(Status.OK.value, bytes([Mode.PULSED.value])))
    assert pdm.software_control_mode == Mode.PULSED

    # Setter: WRITE_INSTRUCTION SOFTWARE_CONTROL_MODE + U08 mode
    fs.queue_response(fake_serial_factory.OK_RESP)
    pdm.software_control_mode = Mode.CONTINUOUS
    frame = fs.writes[-1]
    assert frame[2] == Command.WRITE_INSTRUCTION.value
    data = frame[3:-1]  # without checksum
    # U16 instruction id (31) + U08 mode value
    assert data[:2] == (31).to_bytes(2, "big")
    assert data[2:] == bytes([Mode.CONTINUOUS.value])

    # __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)


def test_control_mode_selection_read_and_write_protocol_3_7(
    fake_serial_factory: types.SimpleNamespace,
) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # __init__ handshake for protocol 3.7
    fs.queue_response(version_resp(3, 7, fake_serial_factory.make_response))
    pdm = PDM(1, link)

    # Getter: READ_INSTRUCTION CONTROL_MODE_SELECTION -> returns U08 selection
    fs.queue_response(fake_serial_factory.make_response(Status.OK.value, bytes([ControlMode.SOFTWARE.value])))
    assert pdm.control_mode_selection == ControlMode.SOFTWARE

    # Setter: WRITE_INSTRUCTION CONTROL_MODE_SELECTION + U08 selection
    fs.queue_response(fake_serial_factory.OK_RESP)
    pdm.control_mode_selection = ControlMode.HARDWARE
    frame = fs.writes[-1]
    assert frame[2] == Command.WRITE_INSTRUCTION.value
    data = frame[3:-1]  # without checksum
    # U16 instruction id (32) + U08 selection value
    assert data[:2] == (32).to_bytes(2, "big")
    assert data[2:] == bytes([ControlMode.HARDWARE.value])

    # __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)


def test_software_control_mode_unsupported_version_raises(
    fake_serial_factory: types.SimpleNamespace,
) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # __init__ handshake for protocol 3.6
    fs.queue_response(version_resp(3, 6, fake_serial_factory.make_response))
    pdm = PDM(1, link)
    with pytest.raises(ProtocolVersionNotSupported):
        _ = pdm.software_control_mode
    # __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)


def test_control_mode_selection_unsupported_version_raises(
    fake_serial_factory: types.SimpleNamespace,
) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # __init__ handshake for protocol 3.6
    fs.queue_response(version_resp(3, 6, fake_serial_factory.make_response))
    pdm = PDM(1, link)
    with pytest.raises(ProtocolVersionNotSupported):
        _ = pdm.control_mode_selection
    # __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)

