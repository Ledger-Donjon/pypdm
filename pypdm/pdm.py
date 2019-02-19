# This file is part of PyPDM
#
# PyPDM is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#
# Copyright 2018-2019 Olivier Hériveaux, Ledger SAS
#
# Thanks for ALPhANOV for providing documentation to write this library.


from enum import Enum
import struct
import serial


class ChecksumError(Exception):
    """ Thrown if a communication checksum error is detected. """
    pass


class ProtocolError(Exception):
    """ Thrown if an unexpected response from the device is received. """
    pass


class ConnectionFailure(Exception):
    pass


class ProtocolVersionNotSupported(Exception):
    """
    Thrown when a PDM protocol version is not (yet) supported by the library.
    """
    def __init__(self, version):
        """
        :param version: Version string.
        """
        super().__init__()
        self.version = version

    def __str__(self):
        return self.version


class StatusError(Exception):
    """
    Thrown when a PDM device did not respond with 'OK' status to the last
    command.
    """
    def __init__(self, status):
        """
        :param status: Status code. int.
        """
        super().__init__()
        self.status = status

    def __str__(self):
        return str(Status(self.status))


class Status(Enum):
    """ Possible response status from the laser source. """
    OK = 0x00
    TIMEOUT = 0x01
    UNKNOWN_COMMAND = 0x02
    QUERY_ERROR = 0x04
    BAD_LENGTH = 0x08
    CHECKSUM_ERROR = 0x10


class Command(Enum):
    """ Possible command IDs. """
    READ_ADDRESS = 0x01  # This command is not documented
    READ_PROTOCOL_VERSION = 0x02
    READ_ERROR_CODE = 0x03
    WRITE_INSTRUCTION = 0x10
    READ_INSTRUCTION = 0x11
    APPLY_ALL_INSTRUCTIONS = 0x12
    SAVE_ALL_INSTRUCTIONS = 0x13
    READ_MEASURE = 0x14
    READ_CW_PULSE = 0x20


class Instruction(Enum):
    """ Possible instruction IDs. """
    SYNC_SOURCE = 10
    DELAY_LINE_TYPE = 11
    FREQUENCY = 12
    PULSE_WIDTH = 13
    DELAY = 14
    OFFSET_CURRENT = 15
    CURRENT = 16
    TEMPERATURE = 17
    MAXIMUM_CURRENT = 20
    CURRENT_SOURCE = 21
    INTERLOCK_STATUS = 26
    LASER_ACTIVATION = 27


class SyncSource(Enum):
    """ Possible PDM synchronization source. """
    EXTERNAL_TTL_LVTTL = 0
    EXTERNAL_LVDS = 1
    INTERNAL = 2


class DelayLineType(Enum):
    """ Possible delay line types. """
    NONE = 0
    INTERNAL = 1


class CurrentSource(Enum):
    """ Possible current sources. """
    ANALOG = 0
    NUMERIC = 1


class Mode(Enum):
    """ Possible PDM mode. """
    PULSED = 0
    CONTINUOUS = 1


class Link:
    """
    Base PDM communication implementation. An instance of :class:`Link` uses a
    serial port and can be shared by multiple :class:`PDM` instances if the
    devices are daisy-chained.
    """
    def __init__(self, dev):
        """
        Open serial device.

        :param dev: Serial device path. For instance '/dev/ttyUSB0' on linux,
            'COM0' on Windows.
        """
        try:
            self.serial = serial.Serial(dev, 125000)
        except serial.serialutil.SerialException as e:
            raise ConnectionFailure() from e

    def __checksum(self, data):
        """
        Calculate the checksum of some data.
        :param data: Input data bytes.
        :return: Checksum byte value.
        """
        val = 0
        for byte in data:
            val ^= byte
        return (val - 1) % 256

    def __receive(self):
        """
        Receive a response. Verify the status and checksum.
        :return: Received data, without header and checksum.
        """
        # Get length byte.
        data = self.serial.read(1)
        # Length byte must be at least 3 for responses (length byte, status
        # byte and checksum byte).
        if data[0] < 3:
            raise ProtocolError()
        # Fetch all the bytes of the command
        data += self.serial.read(data[0]-1)
        # Verify the checksum
        if self.__checksum(data[:-1]) != data[-1]:
            raise ChecksumError()
        # Verify the status
        if data[1] != Status.OK.value:
            raise StatusError(data[1])
        return data[1:-1]

    def __send(self, address, command, data):
        """
        Transmit a command to the laser source. This method automatically add
        the length and checksum bytes.
        :param address: Device address.
        :param command: An instance of Command enumeration.
        :param data: Data bytes.
        :param address: Device address override.
        """
        length = 4 + len(data)
        if length > 0xff:
            raise ValueError('data too long.')
        frame = bytearray([length, address, command.value]) + data
        frame.append(self.__checksum(frame))
        self.serial.write(frame)

    def command(self, address, command, data=bytes()):
        """
        Transmit a command to a laser source, and retrieve the response to
        that command.

        :param address: Device address.
        :param command: An instance of Command enumeration.
        :param data: Data bytes.
        :param address: Device address override.
        :return: Received data, without header and checksum.
        """
        self.__send(address, command, data)
        return self.__receive()


class PDM:
    """
    Class to command one Alphanov's PDM laser sources.
    """
    # Maximum delay in ps, according to documentation.
    MAX_DELAY = 15000
    # Maximum pulse width, in ps, according to documentation.
    MAX_PULSE_WIDTH = 1275000

    def __init__(self, address, link):
        """
        :param address: PDM device address.
        :param link: Specify a string for the serial to be used
            ('/dev/ttyUSBx' or 'COMx'), a :class:`Link` or :class:`PDM` instance
            for daisy-chained configurations.
        """
        self.address = address
        if type(link) is str:
            self.link = Link(link)
        elif isinstance(link, Link):
            self.link = link
        elif isinstance(link, PDM):
            self.link = link.link
        else:
            raise ValueError('Invalid link parameter.')
        # Verify we can communicate with the PDM and the protocol version is
        # supported.
        ver = self.read_protocol_version()
        if ver != '3.4':
            raise ProtocolVersionNotSupported(ver)
        # If the maximum current is queried, cache the result in the following
        # float variable.
        self.__maximum_current_cache = None

    def __del__(self):
        """
        For safety, disable laser when the object is deleted.
        """
        self.activation = False
        self.apply()

    def __command(self, command, data=bytes(), address=None):
        """
        Call link.command method with current device address.
        :param command: An instance of Command enumeration.
        :param data: Data bytes.
        :param address: Device address override.
        :return: Received data, without header and checksum.
        """
        return self.link.command(self.address, command, data)

    def read_protocol_version(self):
        """
        :return: Protocol version string, for instance '3.4'.
        """
        res = self.__command(Command.READ_PROTOCOL_VERSION)
        major = res[1]
        minor = res[2]
        return '{0}.{1}'.format(major, minor)

    def read_address(self):
        """
        Query laser source address.
        """
        res = self.__command(Command.READ_ADDRESS, address=0)
        return res[1]

    def __write_instruction(self, instruction, value):
        """
        Write an instruction in volatile memory.
        :param instruction: An Instruction enum instance.
        :param value: Value data bytes. bytes.
        """
        self.__command(
            Command.WRITE_INSTRUCTION,
            instruction.value.to_bytes(2, 'big', signed=False) + value)

    def __read_instruction(self, instruction, length):
        """
        Read an instruction value.
        :param instruction: An Instruction enum instance.
        :param length: Expected response length.
        :return: Instruction value data bytes.
        """
        res = self.__command(
            Command.READ_INSTRUCTION,
            instruction.value.to_bytes(2, 'big', signed=False))
        if len(res) - 1 != length:
            raise ProtocolError()
        return res[1:]

    @property
    def sync_source(self):
        """ Synchronization source, :class:`SyncSource` instance. """
        val = self.__read_instruction(Instruction.SYNC_SOURCE, 1)[0]
        return SyncSource(val)

    @sync_source.setter
    def sync_source(self, value):
        if not isinstance(value, SyncSource):
            raise ValueError('Param is not a SyncSource')
        self.__write_instruction(Instruction.SYNC_SOURCE,
            value.value.to_bytes(1, 'big', signed=False))

    @property
    def delay_line_type(self):
        """ Delay line type, :class:`DelayLineType` instance. """
        val = self.__read_instruction(Instruction.DELAY_LINE_TYPE, 1)[0]
        return DelayLineType(val)

    @delay_line_type.setter
    def delay_line_type(self, value):
        if not isinstance(value, DelayLineType):
            raise ValueError('Param is not a DelayLineType')
        self.__write_instruction(Instruction.DELAY_LINE_TYPE,
            value.value.to_bytes(1, 'big', signed=False))

    @property
    def frequency(self):
        """ Frequency, in Hz. int. Read-only. """
        val = self.__read_instruction(Instruction.FREQUENCY, 4)
        return int.from_bytes(val, 'big', signed=False)

    @property
    def pulse_width(self):
        """
        Pulse width, in ps. int. Maximum value is defined in MAX_PULSE_WIDTH.
        """
        val = self.__read_instruction(Instruction.PULSE_WIDTH, 4)
        return int.from_bytes(val, 'big', signed=False)

    @pulse_width.setter
    def pulse_width(self, value):
        if value not in range(self.MAX_PULSE_WIDTH+1):
            raise ValueError('Pulse width out of bounds')
        self.__write_instruction(Instruction.PULSE_WIDTH,
            value.to_bytes(4, 'big', signed=False))

    @property
    def delay(self):
        """ Delay, in ps. int. Maximum value is defined in MAX_DELAY. """
        val = self.__read_instruction(Instruction.DELAY, 4)
        return int.from_bytes(val, 'big', signed=False)

    @delay.setter
    def delay(self, value):
        if value not in range(self.MAX_DELAY+1):
            raise ValueError('Delay out of bounds')
        self.__write_instruction(Instruction.DELAY,
            value.to_bytes(4, 'big', signed=False))

    @property
    def offset_current(self):
        """ Offset current, in mA. float. """
        val = self.__read_instruction(Instruction.OFFSET_CURRENT, 4)
        current = struct.unpack('>f', val)[0]
        if current < 0:
            raise ProtocolError()
        return current

    @offset_current.setter
    def offset_current(self, value):
        if (value < 0) or (value > 150):
            raise ValueError('Invalid offset current value.')
        val = struct.pack('>f', value)
        self.__write_instruction(Instruction.OFFSET_CURRENT, val)

    @property
    def current_percentage(self):
        """
        Current, in percentage of maximum. This is an alternative way of
        changing the :attr:`current` property. Call :meth:`apply` to make any
        change effective.
        """
        val = self.__read_instruction(Instruction.CURRENT, 4)
        current = struct.unpack('>f', val)[0]
        if (current < 0) or (current > 100):
            raise ProtocolError()
        return current

    @current_percentage.setter
    def current_percentage(self, value):
        if (value < 0) or (value > 100):
            raise ValueError('Invalid current value.')
        val = struct.pack('>f', value)
        self.__write_instruction(Instruction.CURRENT, val)

    @property
    def current(self):
        """
        Current, in mA.
        Please note this property is in milli-amperes and is not a percentage
        of the maximum current, as the official PDM documentation may state.
        For the percentage, see current_percentage property. Call :meth:`apply`
        to make any change effective.

        :getter: Return diode current configuration.
        :setter: Set the new current. Raise a ValueError if current is out of
            bounds.
        """
        percentage = self.current_percentage
        return percentage * self.maximum_current / 100

    @current.setter
    def current(self, value):
        if (value < 0):
            raise ValueError('Current cannot be negative.')
        if (value > self.maximum_current):
            raise ValueError('Current above maximum possible diode current.')
        self.current_percentage = (value / self.maximum_current) * 100

    @property
    def temperature(self):
        """ Temperature, in degrees. """
        val = self.__read_instruction(Instruction.TEMPERATURE, 4)
        return struct.unpack('>f', val)[0]

    @property
    def maximum_current(self):
        """
        Maximum current, in mA.
        The getter of this property queries the PDM device once then cache the
        value for next accesses.
        """
        if self.__maximum_current_cache is None:
            val = self.__read_instruction(Instruction.MAXIMUM_CURRENT, 4)
            max_current = struct.unpack('>f', val)[0]
            if max_current < 0:
                raise ProtocolError()
            self.__maximum_current_cache = max_current
        return self.__maximum_current_cache

    @property
    def current_source(self):
        """
        Current source. Set to :attr:`CurrentSource.NUMERIC` to control the
        laser diode pulse current from software through the :attr:`current` or
        :attr:`current_percentage` attributes.

        :type: :class:`CurrentSource`
        """
        val = self.__read_instruction(Instruction.CURRENT_SOURCE, 1)[0]
        return CurrentSource(val)

    @current_source.setter
    def current_source(self, value):
        if not isinstance(value, CurrentSource):
            raise ValueError('Param is not a CurrentSource')
        self.__write_instruction(Instruction.CURRENT_SOURCE,
            value.value.to_bytes(1, 'big'))

    @property
    def interlock_status(self):
        """ True if interlock is detected, False otherwise. """
        val = self.__read_instruction(Instruction.INTERLOCK_STATUS, 1)[0]
        if val not in range(2):
            raise ProtocolError()
        return bool(val)

    @property
    def activation(self):
        """
        True when laser is enabled, False when laser is off. Call :meth:`apply`
        to make any change effective.
        """
        val = self.__read_instruction(Instruction.LASER_ACTIVATION, 1)[0]
        if val not in range(2):
            raise ProtocolError()
        return bool(val)

    @activation.setter
    def activation(self, value):
        val = bytes([int(bool(value))])
        self.__write_instruction(Instruction.LASER_ACTIVATION, val)

    @property
    def mode(self):
        """ PDM mode, :class:`Mode` instance. """
        res = self.__command(Command.READ_CW_PULSE)
        if len(res) != 2:
            raise ProtocolError()
        return Mode(res[1])

    def apply(self):
        """
        Apply all the instructions which are in volatile memory. This makes all
        settings changes effectives.
        """
        self.__command(Command.APPLY_ALL_INSTRUCTIONS)
