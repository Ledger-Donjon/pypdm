# PyPDM

[![Documentation Status](https://readthedocs.org/projects/pypdm/badge/?version=latest)](https://pypdm.readthedocs.io/en/latest/?badge=latest)

> Python3 library for controlling Alphanov's PDM laser sources. Currently supported PDM protocol version is from 3.4 to 3.7. Daisy-chain configuration for multiple devices is supported, so it is possible to use many PDMs with only one serial link.

## What's new in 2.0

- Explicit support for protocol 3.7: `software_control_mode` and `control_mode_selection`.
- Minimum required Python raised to 3.10.

## Installation

The library can be installed using pip3:

```sh
pip3 install pypdm
```

## Documentation

A quick documentation is available on [Read the Docs](https://pypdm.readthedocs.io). A simple usage example is also provided below.

## Requirements

This library requires:

- Python >= 3.10
- pyserial

## Safety

When a PDM object is deleted, the library may try to switch off the laser source for safety. However, you shall not rely on this behavior and always beware of dangers when using laser equipments! Please always wear laser safety goggles or use any appropriate safety equipment to prevent any harmful accident.

## Usage example

### Basic laser activation in continuous mode

```python
import pypdm

pdm = pypdm.PDM(1, 'COM0')
# Set offset current in mA.
pdm.offset_current = 30
pdm.activation = True
# Apply new settings to the device.
pdm.apply()
```

### Basic laser configuration for pulsed operation

```python
import pypdm

pdm = pypdm.PDM(1, 'COM0')
# Set pulse power to 50%
pdm.current_source = pypdm.CurrentSource.NUMERIC
pdm.current_percentage = 50
pdm.activation = True
# Apply new settings to the device.
pdm.apply()
```

### List of available properties

```python
import pypdm

pdm = pypdm.PDM(1, 'COM0')
print('Mode:', pdm.mode)
print('Synchronization source:', pdm.sync_source)
print('Delay line type:', pdm.delay_line_type)
print('Frequency (Hz):', pdm.frequency)
print('Pulse width (ps):', pdm.pulse_width)
print('Delay (ps):', pdm.delay)
print('Offset current (mA):', pdm.offset_current)
print('Current (%):', pdm.current_percentage)
print('Current (mA):', pdm.current)
print('Temperature (C°):', pdm.temperature)
print('Maximum current (mA):', pdm.maximum_current)
print('Maximum mean current (mA):', pdm.maximum_mean_current)
print('Current source:', pdm.current_source)
print('Interlock status:', pdm.interlock_status)
print('Activation:', pdm.activation)
# Protocol 3.7 only:
print('Software control mode:', pdm.software_control_mode)      # requires protocol 3.7
print('Control mode selection:', pdm.control_mode_selection)    # requires protocol 3.7
```

### Use of two sources in daisy-chain configuration

```python
import pypdm

pdm1 = pypdm.PDM(1, 'COM0')
pdm2 = pypdm.PDM(2, pdm1)
```

## Testing

To test the package with a real device, you can use `pytest` and enable the "real" tests using the `real` marker.  
Make sure your device is connected (for example, `/dev/ttyUSB0` on Linux or `COM3` on Windows) and that you have installed the required test dependencies (`pytest`).

To run all standard tests (not requiring hardware), use:

```bash
pytest
```

To run tests involving a real device, use:

```bash
pytest -m real --device /dev/ttyUSB0
```

Replace `/dev/ttyUSB0` with the appropriate serial port for your platform.

The `--device` parameter specifies the serial port of the device to be used during "real" tests.  
Tests marked with `@pytest.mark.real` will actually access the physical device.
