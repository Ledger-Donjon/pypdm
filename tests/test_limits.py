import pytest
from pypdm.pdm import PDM, Link, Status
from typing import Callable, cast
import types
from conftest import FakeSerial


def version_resp(make_response: Callable[[int, bytes], bytes], major: int = 3, minor: int = 4) -> bytes:
    return make_response(Status.OK.value, bytes([major, minor]))


def test_pulse_width_and_delay_limits(fake_serial_factory: types.SimpleNamespace) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    fs.queue_response(version_resp(fake_serial_factory.make_response))
    pdm = PDM(1, link)

    # pulse_width must raise beyond MAX_PULSE_WIDTH
    with pytest.raises(ValueError):
        pdm.pulse_width = pdm.MAX_PULSE_WIDTH + 1

    # delay must raise beyond MAX_DELAY
    with pytest.raises(ValueError):
        pdm.delay = pdm.MAX_DELAY + 1

    # __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)


def test_current_percentage_and_offset_current_setters(fake_serial_factory: types.SimpleNamespace) -> None:
    link = Link("/dev/ttyFAKE")
    fs = cast(FakeSerial, link.serial)
    fs.queue_response(version_resp(fake_serial_factory.make_response))

    pdm = PDM(1, link)

    with pytest.raises(ValueError):
        pdm.current_percentage = -0.1
    with pytest.raises(ValueError):
        pdm.current_percentage = 100.1
    with pytest.raises(ValueError):
        pdm.offset_current = -1.0
    with pytest.raises(ValueError):
        pdm.offset_current = 151.0

    # __del__ will disable the laser -> provide a two last OK responses
    fs.queue_response(fake_serial_factory.OK_RESP)
    fs.queue_response(fake_serial_factory.OK_RESP)
