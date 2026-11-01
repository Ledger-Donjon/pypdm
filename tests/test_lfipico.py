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


class SimPico(LFIPico):
    """LFIPico simulating the device state, logging the applied states."""

    def __init__(self) -> None:
        self.state = {"on": False, "full": False, "smd1": 0.0, "smd2": 0.0}
        self.pending = dict(self.state)
        self.log: list[tuple[bool, bool, float, float]] = []
        self.sleeps = 0

    def apply(self) -> None:
        if self.pending["on"] and not self.state["on"]:
            # Activation resets the currents.
            self.pending["smd1"] = self.pending["smd2"] = 0.0
        if not self.pending["on"]:
            self.pending["full"] = False
        self.state = dict(self.pending)
        s = self.state
        self.log.append((s["on"], s["full"], round(s["smd2"], 6), round(s["smd1"], 6)))

    smd2_peak_current_max = 0.5  # type: ignore[assignment]
    activation = property(  # type: ignore[assignment]
        lambda self: self.state["on"],
        lambda self, v: self.pending.__setitem__("on", v),
    )
    full_activation = property(  # type: ignore[assignment]
        lambda self: self.state["full"],
        lambda self, v: self.pending.__setitem__("full", v),
    )
    smd1_current_percentage = property(  # type: ignore[assignment]
        lambda self: self.state["smd1"],
        lambda self, v: self.pending.__setitem__("smd1", v),
    )
    smd2_current = property(  # type: ignore[assignment]
        lambda self: self.state["smd2"],
        lambda self, v: self.pending.__setitem__("smd2", v),
    )


@pytest.fixture
def sim(monkeypatch: pytest.MonkeyPatch) -> SimPico:
    pico = SimPico()
    monkeypatch.setattr(
        "pypdm.lfipico.time.sleep",
        lambda d: setattr(pico, "sleeps", pico.sleeps + 1),
    )
    return pico


def test_set_low_power_ramps_up(sim: SimPico) -> None:
    sim.set_low_power(0.25)
    # Steps of 20% of 0.5 A, one second apart
    assert sim.log == [
        (True, False, 0.0, 0.0),
        (True, False, 0.1, 0.0),
        (True, False, 0.2, 0.0),
        (True, False, 0.25, 0.0),
    ]
    assert sim.sleeps == 3
    # Out of bounds current is rejected before activating the laser
    with pytest.raises(ValueError):
        sim.set_low_power(0.6)
    assert len(sim.log) == 4


def test_set_high_power_ramps_up(sim: SimPico) -> None:
    with pytest.raises(ValueError):
        sim.set_high_power(101)
    assert sim.log == []
    sim.set_high_power(30.0)
    assert sim.log == [
        (True, False, 0.0, 0.0),
        (True, False, 0.1, 0.0),
        (True, False, 0.2, 0.0),
        (True, False, 0.3, 0.0),
        (True, False, 0.4, 0.0),
        (True, False, 0.5, 0.0),
        (True, True, 0.5, 0.0),
        (True, True, 0.5, 20.0),
        (True, True, 0.5, 30.0),
    ]
    assert sim.sleeps == len(sim.log) - 1


def test_switch_off_ramps_down(sim: SimPico) -> None:
    sim.set_high_power(30.0)
    sim.log.clear()
    sim.switch_off()
    assert sim.log == [
        (True, True, 0.5, 10.0),
        (True, True, 0.5, 0.0),
        (True, False, 0.5, 0.0),
        (True, False, 0.4, 0.0),
        (True, False, 0.3, 0.0),
        (True, False, 0.2, 0.0),
        (True, False, 0.1, 0.0),
        (True, False, 0.0, 0.0),
        (False, False, 0.0, 0.0),
    ]
    # Already off: nothing to do
    sim.log.clear()
    sim.switch_off()
    assert sim.log == []


def test_mode_change_while_on(sim: SimPico) -> None:
    sim.set_high_power(10.0)
    sim.log.clear()
    sim.set_low_power(0.3)
    assert sim.log == [
        (True, True, 0.5, 0.0),
        (True, False, 0.5, 0.0),
        (True, False, 0.4, 0.0),
        (True, False, 0.3, 0.0),
    ]
    sim.log.clear()
    sim.set_high_power(10.0)
    assert sim.log == [
        (True, False, 0.4, 0.0),
        (True, False, 0.5, 0.0),
        (True, True, 0.5, 0.0),
        (True, True, 0.5, 10.0),
    ]
