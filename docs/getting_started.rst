Getting started!
================

PyPDM is a small and simple Python3 library for controlling Alphanov's PDM laser sources. Currently supported PDM protocol version is from 3.4 to 3.7. Daisy-chain configuration for multiple devices is supported, so it is possible to use many PDMs with only one serial link.


Connecting to PDM devices
-------------------------

The following example shows how to connect to a PDM device using the :class:`pypdm.PDM` class. The first argument is the PDM device address, which may be different depending on your PDM configuration. The second argument is the serial device path (may be '/dev/ttyUSB0' on linux).

When connecting, the library will query the device version and raise a :class:`pypdm.ProtocolVersionNotSupported` exception if not correct.

.. code-block:: python

    import pypdm

    pdm = pypdm.PDM(1, 'COM0')

If you use multiple laser sources in daisy-chain configuration, you can instantiate one :class:`pypdm.PDM` object for each device like in the following example:

.. code-block:: python

    import pypdm

    pdm1 = pypdm.PDM(1, 'COM0')
    pdm2 = pypdm.PDM(2, pdm1) # Use same serial as pdm1
    pdm3 = pypdm.PDM(3, pdm1) # Use same serial as pdm1

Daisy-chain configuration must be used for PDM2+ or PDM4+ devices.

Alternatively, you can use the following equivalent code for daisy-chain configuration:

.. code-block:: python

    import pypdm
    
    link = pypdm.Link('COM0')
    pdm1 = pypdm.PDM(1, link)
    pdm2 = pypdm.PDM(2, link)
    pdm3 = pypdm.PDM(3, link)


Laser in continuous operation
-----------------------------

The following example turns on a laser source in continuous mode.
Current is set to 30 mA.

.. code-block:: python

    import pypdm

    pdm = pypdm

    pdm = pypdm.PDM(1, 'COM0')
    pdm.offset_current = 30
    pdm.activation = True
    # Apply new settings to the device
    pdm.apply()


Configuring the laser source
----------------------------

All configuration parameters of PDM devices can be modified using :class:`pypdm.PDM` member properties. When a setting is changed, call :meth:`pypdm.PDM.apply` to make it effective. Here is the list of properties which can be read or changed (see reference API for more details):

- :attr:`pypdm.PDM.sync_source`
- :attr:`pypdm.PDM.delay_line_type`
- :attr:`pypdm.PDM.frequency`
- :attr:`pypdm.PDM.pulse_width`
- :attr:`pypdm.PDM.delay`
- :attr:`pypdm.PDM.offset_current`
- :attr:`pypdm.PDM.current_percentage`
- :attr:`pypdm.PDM.current`
- :attr:`pypdm.PDM.temperature`
- :attr:`pypdm.PDM.maximum_current`
- :attr:`pypdm.PDM.current_source`
- :attr:`pypdm.PDM.interlock_status`
- :attr:`pypdm.PDM.activation`
- :attr:`pypdm.PDM.mode`
- :attr:`pypdm.PDM.software_control_mode`
- :attr:`pypdm.PDM.control_mode_selection`

Laser in pulsed operation
-------------------------

The following example turns on a laser source for pulsed operation. Pulse power can be specified using the current_percentage or current properties.

.. code-block:: python

    import pypdm

    pdm = pypdm

    pdm = pypdm.PDM(1, 'COM0')
    pdm.offset_current = 0
    pdm.current_source = pypdm.CurrentSource.NUMERIC
    pdm.current_percentage = 20
    pdm.activation = True
    # Apply new settings to the device
    pdm.apply()


Safety
------

When a PDM object is deleted, the library may try to switch off the laser source for safety. However, you shall not rely on this behavior and always beware of dangers when using laser equipments! Please always wear laser safety glasses or use any appropriate safety equipment to prevent any harmful accident.

