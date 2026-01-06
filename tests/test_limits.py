import pytest
from pypdm.pdm import PDM, Link


def version_resp(make_response, major=3, minor=4):
    return make_response(0x00, bytes([major, minor]))


def test_pulse_width_and_delay_limits(fake_serial_factory):
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    fs.queue_response(version_resp(fake_serial_factory.make_response))
    link = Link("/dev/ttyFAKE")
    pdm = PDM(1, link)

    # pulse_width doit lever au-delà de MAX_PULSE_WIDTH
    with pytest.raises(ValueError):
        pdm.pulse_width = pdm.MAX_PULSE_WIDTH + 1

    # delay doit lever au-delà de MAX_DELAY
    with pytest.raises(ValueError):
        pdm.delay = pdm.MAX_DELAY + 1


def test_current_percentage_and_offset_current_setters(fake_serial_factory):
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    fs.queue_response(version_resp(fake_serial_factory.make_response))
    link = Link("/dev/ttyFAKE")
    pdm = PDM(1, link)

    with pytest.raises(ValueError):
        pdm.current_percentage = -0.1
    with pytest.raises(ValueError):
        pdm.current_percentage = 100.1
    with pytest.raises(ValueError):
        pdm.offset_current = -1.0
    with pytest.raises(ValueError):
        pdm.offset_current = 151.0


