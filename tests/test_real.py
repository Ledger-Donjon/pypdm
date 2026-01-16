from pypdm.pdm import PDM, Mode, ControlMode
import pytest


@pytest.mark.real
def test_read_protocol_version_real(device_path: str) -> None:
    pdm = PDM(1, device_path)
    assert pdm.version == "3.7" or pdm.version == "3.4"


@pytest.mark.real
def test_read_address_real(device_path: str) -> None:
    pdm = PDM(1, device_path)
    assert pdm.read_address() == 1


@pytest.mark.real
def test_software_control_mode_real(device_path: str) -> None:
    pdm = PDM(1, device_path)

    if pdm.version != "3.7":
        pytest.skip(
            "Software control mode is not supported for protocol version 3.4"
        )

    mode = pdm.software_control_mode
    assert mode == Mode.PULSED or mode == Mode.CONTINUOUS

    pdm.software_control_mode = Mode.PULSED
    assert pdm.software_control_mode == Mode.PULSED
    pdm.software_control_mode = Mode.CONTINUOUS
    assert pdm.software_control_mode == Mode.CONTINUOUS

    pdm.software_control_mode = mode
    assert pdm.software_control_mode == mode


@pytest.mark.real
def test_control_mode_selection_real(device_path: str) -> None:
    pdm = PDM(1, device_path)

    if pdm.version != "3.7":
        pytest.skip(
            "Control mode selection is not supported for protocol version 3.4"
        )

    selection = pdm.control_mode_selection
    assert selection == ControlMode.HARDWARE or selection == ControlMode.SOFTWARE

    pdm.control_mode_selection = ControlMode.HARDWARE
    assert pdm.control_mode_selection == ControlMode.HARDWARE
    pdm.control_mode_selection = ControlMode.SOFTWARE
    assert pdm.control_mode_selection == ControlMode.SOFTWARE

    pdm.control_mode_selection = selection
    assert pdm.control_mode_selection == selection
