[![Documentation Status](https://readthedocs.org/projects/pypdm/badge/?version=latest)](https://pypdm.readthedocs.io/en/latest/?badge=latest)

# PyPDM

Python3 library for controlling Alphanov's PDM laser sources. Currently supported PDM protocol version is 3.4. Daisy-chain configuration for multiple devices is supported, so it is possible to use many PDMs with only one serial link.

## Installation

Clone the repository then use pip3 to install the package.

    pip3 install pypdm

## Documentation

A quick documentation is available on [Read the Docs](https://pypdm.readthedocs.io). A simple usage example is also provided below.

## Requirements

This library requires the following packages:
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
print('Interlock status:', pdm.interlock_status)
print('Laser activation:', pdm.laser_activation)
```

### Use of two sources in daisy-chain configuration

```python
import pypdm

pdm1 = pypdm.PDM(1, 'COM0')
pdm2 = pypdm.PDM(2, pdm1)
```

