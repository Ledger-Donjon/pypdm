# These tests never activate the laser emission.

import pytest

from pypdm import Alarm, CardType, LFIPico

pytestmark = pytest.mark.real_lfipico


@pytest.fixture
def pico(lfipico_device_path: str) -> LFIPico:
    pico = LFIPico(lfipico_device_path)
    pico.activation = False
    pico.full_activation = False
    pico.apply()
    return pico


def test_identification_real(pico: LFIPico) -> None:
    assert pico.version.count(".") == 1
    assert pico.instruction_version.count(".") == 1
    assert pico.firmware_version.count(".") == 2
    assert pico.hardware_version.count(".") == 2
    assert isinstance(pico.card_type, CardType)
    assert pico.serial_number >= 0


def test_read_error_code_real(pico: LFIPico) -> None:
    module_id, error_id = pico.read_error_code()
    assert 0 <= module_id <= 255
    assert 0 <= error_id <= 255


def test_laser_off_real(pico: LFIPico) -> None:
    assert pico.activation is False
    assert pico.full_activation is False


def test_alarms_real(pico: LFIPico) -> None:
    assert isinstance(pico.alarms, Alarm)
    assert pico.interlock_alarms == Alarm(0)


def test_current_limits_real(pico: LFIPico) -> None:
    assert 0 < pico.smd1_current_max <= 1.5
    assert 0 < pico.smd2_peak_current_max <= LFIPico.MAX_SMD2_CURRENT


def test_smd2_current_real(pico: LFIPico) -> None:
    initial = pico.smd2_current
    try:
        pico.smd2_current = 0.01
        pico.apply()
        assert pico.smd2_current == pytest.approx(0.01)
        with pytest.raises(ValueError):
            pico.smd2_current = pico.smd2_peak_current_max + 0.01
    finally:
        pico.smd2_current = initial
        pico.apply()
    assert pico.activation is False


def test_smd1_current_percentage_real(pico: LFIPico) -> None:
    initial = pico.smd1_current_percentage
    try:
        pico.smd1_current_percentage = 1.0
        pico.apply()
        assert pico.smd1_current_percentage == pytest.approx(1.0)
    finally:
        pico.smd1_current_percentage = initial
        pico.apply()
    assert pico.full_activation is False
