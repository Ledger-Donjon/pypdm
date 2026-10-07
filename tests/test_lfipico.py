import struct
import types
from typing import cast

import pytest

from pypdm.pdm import Command, Link, Status
from pypdm.lfipico import Alarm, CardType, LFIPico
from conftest import FakeSerial


def make_pico(fsf: types.SimpleNamespace) -> tuple[LFIPico, FakeSerial]:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    # __init__ reads the protocol version
    fs.queue_response(fsf.make_response(Status.OK.value, bytes([1, 0])))
    return LFIPico(link), fs


def release(pico: LFIPico, fs: FakeSerial, fsf: types.SimpleNamespace) -> None:
    # __del__ disables the laser and applies
    fs.queue_response(fsf.OK_RESP)
    fs.queue_response(fsf.OK_RESP)
    fs.queue_response(fsf.OK_RESP)
    del pico


def written(fs: FakeSerial, index: int = -1) -> tuple[int, int, bytes]:
    """Return (command, instruction id, value) of a written frame."""
    frame = fs.writes[index]
    return frame[2], int.from_bytes(frame[3:5], "big"), bytes(frame[5:-1])


def test_default_address_and_version(fake_serial_factory: types.SimpleNamespace) -> None:
    pico, fs = make_pico(fake_serial_factory)
    assert pico.address == 51
    assert pico.version == "1.0"
    assert fs.writes[0][1] == 51
    release(pico, fs, fake_serial_factory)


def test_del_disables_laser(fake_serial_factory: types.SimpleNamespace) -> None:
    pico, fs = make_pico(fake_serial_factory)
    for _ in range(3):
        fs.queue_response(fake_serial_factory.OK_RESP)
    del pico
    assert written(fs, -3) == (Command.WRITE_INSTRUCTION.value, 10, b"\x00")
    assert written(fs, -2) == (Command.WRITE_INSTRUCTION.value, 60, b"\x00")
    assert fs.writes[-1][2] == Command.APPLY_ALL_INSTRUCTIONS.value


def test_identification(fake_serial_factory: types.SimpleNamespace) -> None:
    fsf = fake_serial_factory
    pico, fs = make_pico(fsf)
    fs.queue_response(fsf.make_response(0, (7).to_bytes(4, "big")))
    assert pico.card_type == CardType.PDMV5
    fs.queue_response(fsf.make_response(0, bytes([1, 6, 1])))
    assert pico.firmware_version == "1.6.1"
    assert written(fs)[:2] == (Command.READ_INSTRUCTION.value, 5)
    fs.queue_response(fsf.make_response(0, bytes([0, 2])))
    assert pico.instruction_version == "0.2"
    fs.queue_response(fsf.make_response(0, (98).to_bytes(4, "big")))
    assert pico.serial_number == 98
    release(pico, fs, fsf)


def test_smd2_current(fake_serial_factory: types.SimpleNamespace) -> None:
    fsf = fake_serial_factory
    pico, fs = make_pico(fsf)
    # Setter queries the maximum (instruction 56) once, then writes
    fs.queue_response(fsf.make_response(0, struct.pack(">f", 3.5)))
    fs.queue_response(fsf.OK_RESP)
    pico.smd2_current = 2.0
    assert written(fs, -2)[:2] == (Command.READ_INSTRUCTION.value, 56)
    assert written(fs) == (Command.WRITE_INSTRUCTION.value, 53, struct.pack(">f", 2.0))
    # Maximum is cached
    with pytest.raises(ValueError):
        pico.smd2_current = 3.6
    with pytest.raises(ValueError):
        pico.smd2_current = -0.1
    release(pico, fs, fsf)


def test_smd1_current_percentage(fake_serial_factory: types.SimpleNamespace) -> None:
    fsf = fake_serial_factory
    pico, fs = make_pico(fsf)
    fs.queue_response(fsf.OK_RESP)
    pico.smd1_current_percentage = 40.0
    assert written(fs) == (Command.WRITE_INSTRUCTION.value, 47, struct.pack(">f", 40.0))
    with pytest.raises(ValueError):
        pico.smd1_current_percentage = 101
    fs.queue_response(fsf.make_response(0, struct.pack(">f", 1.5)))
    assert pico.smd1_current_max == pytest.approx(1.5)
    release(pico, fs, fsf)


def test_alarms(fake_serial_factory: types.SimpleNamespace) -> None:
    fsf = fake_serial_factory
    pico, fs = make_pico(fsf)
    fs.queue_response(fsf.make_response(0, ((1 << 8) | (1 << 3)).to_bytes(4, "big")))
    assert pico.alarms == Alarm.CASE_OPEN | Alarm.SMD1_TEMPERATURE
    assert written(fs)[:2] == (Command.READ_MEASURE.value, 14)
    fs.queue_response(fsf.make_response(0, bytes(4)))
    assert pico.interlock_alarms == Alarm(0)
    assert written(fs)[:2] == (Command.READ_MEASURE.value, 15)
    release(pico, fs, fsf)


def test_read_error_code(fake_serial_factory: types.SimpleNamespace) -> None:
    fsf = fake_serial_factory
    pico, fs = make_pico(fsf)
    fs.queue_response(fsf.make_response(0, bytes([2, 9])))
    assert pico.read_error_code() == (2, 9)
    release(pico, fs, fsf)


def apply_frame(fs: FakeSerial, index: int) -> bool:
    return fs.writes[index][2] == Command.APPLY_ALL_INSTRUCTIONS.value


def test_set_low_power(fake_serial_factory: types.SimpleNamespace) -> None:
    fsf = fake_serial_factory
    pico, fs = make_pico(fsf)
    fs.queue_response(fsf.make_response(0, struct.pack(">f", 0.48)))
    for _ in range(5):
        fs.queue_response(fsf.OK_RESP)
    pico.set_low_power(0.05)
    # Current is set after activation, which resets it to 0
    assert written(fs, -5) == (Command.WRITE_INSTRUCTION.value, 60, b"\x00")
    assert written(fs, -4) == (Command.WRITE_INSTRUCTION.value, 10, b"\x01")
    assert apply_frame(fs, -3)
    assert written(fs, -2) == (Command.WRITE_INSTRUCTION.value, 53, struct.pack(">f", 0.05))
    assert apply_frame(fs, -1)
    # Out of bounds current is rejected before activating the laser
    count = len(fs.writes)
    with pytest.raises(ValueError):
        pico.set_low_power(0.5)
    assert len(fs.writes) == count
    release(pico, fs, fsf)


def test_set_high_power(fake_serial_factory: types.SimpleNamespace) -> None:
    fsf = fake_serial_factory
    pico, fs = make_pico(fsf)
    with pytest.raises(ValueError):
        pico.set_high_power(101)
    assert len(fs.writes) == 1
    fs.queue_response(fsf.OK_RESP)
    fs.queue_response(fsf.OK_RESP)
    fs.queue_response(fsf.make_response(0, struct.pack(">f", 0.48)))
    for _ in range(6):
        fs.queue_response(fsf.OK_RESP)
    pico.set_high_power(60.0)
    assert written(fs, -9) == (Command.WRITE_INSTRUCTION.value, 10, b"\x01")
    assert apply_frame(fs, -8)
    assert written(fs, -7)[:2] == (Command.READ_INSTRUCTION.value, 56)
    assert written(fs, -6) == (Command.WRITE_INSTRUCTION.value, 53, struct.pack(">f", 0.48))
    assert apply_frame(fs, -5)
    assert written(fs, -4) == (Command.WRITE_INSTRUCTION.value, 60, b"\x01")
    assert apply_frame(fs, -3)
    assert written(fs, -2) == (Command.WRITE_INSTRUCTION.value, 47, struct.pack(">f", 60.0))
    assert apply_frame(fs, -1)
    release(pico, fs, fsf)
