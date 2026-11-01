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
# Copyright 2026 Ledger SAS
#
# Written from ALPhANOV's "LFIPico Hexa Programming Manual" v1.1 (DQ234.b).


from enum import Enum, IntFlag
import struct
import time
from typing import Callable, List, Optional, Tuple, Union

from .pdm import Command, Link, PDM, ProtocolError


class LFIPicoInstruction(Enum):
    """Instruction IDs of the LFIPico."""

    INSTRUCTION_VERSION = 0
    HARDWARE_CARD_TYPE = 1
    HARDWARE_VERSION = 2
    SERIAL_NUMBER = 3
    FIRMWARE_VERSION = 5
    LASER_ACTIVATION = 10
    SMD1_CURRENT_MAX = 46
    SMD1_CURRENT = 47
    SMD2_CURRENT = 53
    SMD2_PEAK_CURRENT_MAX = 56
    FULL_LASER_ACTIVATION = 60


class LFIPicoMeasure(Enum):
    """Measure IDs of the LFIPico."""

    ALARMS = 14
    INTERLOCK_ALARMS = 15


class CardType(Enum):
    """Hardware card types, as returned by :attr:`LFIPico.card_type`."""

    NONE = 0
    PDM = 1
    CCM = 2
    CRISTAL = 3
    CENTRAL = 4
    PULSEPICKER = 5
    SHAPER = 6
    PDMV5 = 7
    EXO = 8
    BIO = 9


class Alarm(IntFlag):
    """LFIPico alarm bits, as returned by :attr:`LFIPico.alarms`."""

    MAIN_POWER_SUPPLY = 1 << 0
    HOUSEKEEPING_POWER_SUPPLY = 1 << 1
    RED_GUIDE = 1 << 2
    SMD1_TEMPERATURE = 1 << 3
    SMD2_TEMPERATURE = 1 << 4
    SMD2_AVERAGE_CURRENT = 1 << 5
    CASE_TEMPERATURE = 1 << 6
    BAD_START_SEQUENCE = 1 << 7
    CASE_OPEN = 1 << 8
    EXTERNAL_POWER_CUT = 1 << 9
    PD_IN_LOW = 1 << 10
    PD_OUT_LOW = 1 << 11
    PD_CRI_LOW = 1 << 12
    LASER_RETURN = 1 << 13
    DRIVER_ALARM = 1 << 14
    MMD1_ALARM = 1 << 15
    MMD2_ALARM = 1 << 16
    MMD3_ALARM = 1 << 17
    WATCHDOG_PD_PULSE = 1 << 18


class LFIPico:
    """
    Class to command ALPhANOV's LFIPico picosecond laser.

    The LFIPico has a seed diode, which is not driven by this class, and two
    amplifying diodes:

    - SMD2, which modulates the output in low power mode (:attr:`smd2_current`),
    - SMD1, which modulates the output in high power mode, SMD2 being at its
      maximum current (:attr:`smd1_current_percentage`).

    Like for :class:`PDM`, written settings are effective only after calling
    :meth:`apply`. Activating the laser resets the SMD1 and SMD2 currents to 0,
    so currents must be set and applied after activation.

    The diode currents must be raised and lowered progressively, by steps of
    :attr:`RAMP_STEP` percent of their full scale every :attr:`RAMP_PERIOD`
    seconds. :meth:`set_low_power`, :meth:`set_high_power` and
    :meth:`switch_off` take care of this. They block during the ramp: for a
    non-blocking operation, run the steps given by :meth:`low_power_steps`,
    :meth:`high_power_steps` and :meth:`switch_off_steps` with a timer.
    """

    # Default board address, according to documentation.
    DEFAULT_ADDRESS = 51
    # Maximum SMD2 current, in A, according to documentation.
    MAX_SMD2_CURRENT = 4.0
    # Diode currents ramp step, in percent of their full scale.
    RAMP_STEP = 20.0
    # Delay between two ramp steps, in seconds.
    RAMP_PERIOD = 1.0

    def __init__(
        self, link: Union[str, Link, PDM, "LFIPico"], address: int = DEFAULT_ADDRESS
    ):
        """
        :param link: Specify a string for the serial to be used
            ('/dev/ttyUSBx' or 'COMx'), or a :class:`Link`, :class:`PDM` or
            :class:`LFIPico` instance to share an existing serial link.
        :param address: Board address. 51 by default.
        """
        self.address = address
        if type(link) is str:
            self.link = Link(link)
        elif isinstance(link, Link):
            self.link = link
        elif isinstance(link, (PDM, LFIPico)):
            self.link = link.link
        else:
            raise ValueError("Invalid link parameter.")
        # Verify we can communicate with the device.
        self.version = self.read_protocol_version()
        self.__smd2_peak_current_max_cache: Optional[float] = None

    def __del__(self):
        """
        For safety, disable laser when the object is deleted.
        """
        if hasattr(self, "version"):
            # Disabling activation powers off both diodes, but full activation
            # remains set and would power on SMD1 at next activation.
            self.activation = False
            self.full_activation = False
            self.apply()

    def __command(self, command: Command, data: bytes = bytes()) -> bytes:
        return self.link.command(self.address, command, data)

    def __write_instruction(self, instruction: LFIPicoInstruction, value: bytes):
        """
        Write an instruction in volatile memory.
        :param instruction: An LFIPicoInstruction enum instance.
        :param value: Value data bytes.
        """
        self.__command(
            Command.WRITE_INSTRUCTION, instruction.value.to_bytes(2, "big") + value
        )

    def __read_instruction(
        self, instruction: LFIPicoInstruction, length: int
    ) -> bytes:
        """
        Read an instruction value.
        :param instruction: An LFIPicoInstruction enum instance.
        :param length: Expected value length.
        :return: Instruction value data bytes.
        """
        res = self.__command(
            Command.READ_INSTRUCTION, instruction.value.to_bytes(2, "big")
        )
        if len(res) - 1 != length:
            raise ProtocolError()
        return res[1:]

    def __read_measure(self, measure: LFIPicoMeasure, length: int) -> bytes:
        """
        Read a measure value.
        :param measure: An LFIPicoMeasure enum instance.
        :param length: Expected value length.
        :return: Measure value data bytes.
        """
        res = self.__command(Command.READ_MEASURE, measure.value.to_bytes(2, "big"))
        if len(res) - 1 != length:
            raise ProtocolError()
        return res[1:]

    def __read_float(self, instruction: LFIPicoInstruction) -> float:
        return struct.unpack(">f", self.__read_instruction(instruction, 4))[0]

    def __read_version(self, instruction: LFIPicoInstruction, length: int) -> str:
        return ".".join(str(x) for x in self.__read_instruction(instruction, length))

    def read_protocol_version(self) -> str:
        """
        :return: Protocol version string, for instance '3.4'.
        """
        res = self.__command(Command.READ_PROTOCOL_VERSION)
        if len(res) != 3:
            raise ProtocolError()
        return f"{res[1]}.{res[2]}"

    def read_error_code(self) -> Tuple[int, int]:
        """
        Read the last error, which details a :class:`StatusError` with the
        query error status.

        :return: (module ID, error ID) tuple.
        """
        res = self.__command(Command.READ_ERROR_CODE)
        if len(res) != 3:
            raise ProtocolError()
        return res[1], res[2]

    def apply(self):
        """
        Apply all the instructions which are in volatile memory. This makes all
        settings changes effective.
        """
        self.__command(Command.APPLY_ALL_INSTRUCTIONS)

    @property
    def instruction_version(self) -> str:
        """Instruction set version string, for instance '0.2'."""
        return self.__read_version(LFIPicoInstruction.INSTRUCTION_VERSION, 2)

    @property
    def card_type(self) -> CardType:
        """Hardware card type, :class:`CardType` instance."""
        val = self.__read_instruction(LFIPicoInstruction.HARDWARE_CARD_TYPE, 4)
        return CardType(int.from_bytes(val, "big"))

    @property
    def hardware_version(self) -> str:
        """Hardware version string, for instance '1.2.3'."""
        return self.__read_version(LFIPicoInstruction.HARDWARE_VERSION, 3)

    @property
    def serial_number(self) -> int:
        """Serial number."""
        val = self.__read_instruction(LFIPicoInstruction.SERIAL_NUMBER, 4)
        return int.from_bytes(val, "big")

    @property
    def firmware_version(self) -> str:
        """Firmware version string, for instance '1.6.1'."""
        return self.__read_version(LFIPicoInstruction.FIRMWARE_VERSION, 3)

    @property
    def activation(self) -> bool:
        """
        Laser activation. Enabling powers on SMD2; disabling powers off both
        SMD1 and SMD2. Call :meth:`apply` to make any change effective.
        """
        val = self.__read_instruction(LFIPicoInstruction.LASER_ACTIVATION, 1)[0]
        if val not in range(2):
            raise ProtocolError()
        return bool(val)

    @activation.setter
    def activation(self, value: bool):
        self.__write_instruction(
            LFIPicoInstruction.LASER_ACTIVATION, bytes([int(bool(value))])
        )

    @property
    def full_activation(self) -> bool:
        """
        Full laser activation. Enabling powers on SMD1 (high power mode),
        disabling powers it off (low power mode). Call :meth:`apply` to make
        any change effective.
        """
        val = self.__read_instruction(LFIPicoInstruction.FULL_LASER_ACTIVATION, 1)[0]
        if val not in range(2):
            raise ProtocolError()
        return bool(val)

    @full_activation.setter
    def full_activation(self, value: bool):
        self.__write_instruction(
            LFIPicoInstruction.FULL_LASER_ACTIVATION, bytes([int(bool(value))])
        )

    @property
    def smd1_current_max(self) -> float:
        """SMD1 maximum pumping current, in A."""
        return self.__read_float(LFIPicoInstruction.SMD1_CURRENT_MAX)

    @property
    def smd1_current_percentage(self) -> float:
        """
        SMD1 pumping current, in percentage of :attr:`smd1_current_max`. Call
        :meth:`apply` to make any change effective.
        """
        return self.__read_float(LFIPicoInstruction.SMD1_CURRENT)

    @smd1_current_percentage.setter
    def smd1_current_percentage(self, value: float):
        if (value < 0) or (value > 100):
            raise ValueError(f"SMD1 current {value}% out of bounds (0-100%)")
        self.__write_instruction(
            LFIPicoInstruction.SMD1_CURRENT, struct.pack(">f", value)
        )

    @property
    def smd2_peak_current_max(self) -> float:
        """
        SMD2 maximum peak current, in A.
        The getter of this property queries the device once then cache the
        value for next accesses.
        """
        if self.__smd2_peak_current_max_cache is None:
            self.__smd2_peak_current_max_cache = self.__read_float(
                LFIPicoInstruction.SMD2_PEAK_CURRENT_MAX
            )
        return self.__smd2_peak_current_max_cache

    @property
    def smd2_current(self) -> float:
        """
        SMD2 current, in A. Cannot exceed :attr:`smd2_peak_current_max`. Call
        :meth:`apply` to make any change effective.
        """
        return self.__read_float(LFIPicoInstruction.SMD2_CURRENT)

    @smd2_current.setter
    def smd2_current(self, value: float):
        maximum = self.smd2_current_full_scale
        if (value < 0) or (value > maximum):
            raise ValueError(f"SMD2 current {value}A out of bounds ({maximum}A max)")
        self.__write_instruction(
            LFIPicoInstruction.SMD2_CURRENT, struct.pack(">f", value)
        )

    @property
    def alarms(self) -> Alarm:
        """Alarms currently triggered, :class:`Alarm` flags."""
        val = self.__read_measure(LFIPicoMeasure.ALARMS, 4)
        return Alarm(int.from_bytes(val, "big"))

    @property
    def interlock_alarms(self) -> Alarm:
        """
        Alarms that triggered an interlock, necessitating a power cycle,
        :class:`Alarm` flags.
        """
        val = self.__read_measure(LFIPicoMeasure.INTERLOCK_ALARMS, 4)
        return Alarm(int.from_bytes(val, "big"))

    @property
    def smd2_current_full_scale(self) -> float:
        """SMD2 current maximum allowed value, in A."""
        return min(self.MAX_SMD2_CURRENT, self.smd2_peak_current_max)

    def __ramp(
        self, start: float, stop: float, full_scale: float, write: Callable[[float], None]
    ) -> List[Callable[[], None]]:
        """
        :return: Steps writing and applying the values from start (excluded)
            to stop (included), by :attr:`RAMP_STEP` percent of full scale.
        """
        step = full_scale * self.RAMP_STEP / 100
        values = []
        value = start
        # Tolerance avoids a tiny last step due to rounding errors.
        while abs(stop - value) > step * 1.001:
            value += step if stop > value else -step
            values.append(value)
        if abs(stop - start) > 1e-9:
            values.append(stop)

        def make_step(v: float) -> Callable[[], None]:
            def step_function():
                write(v)
                self.apply()

            return step_function

        return [make_step(v) for v in values]

    def __set_smd1(self, value: float):
        self.smd1_current_percentage = value

    def __set_smd2(self, value: float):
        self.smd2_current = value

    def __smd1_off_steps(self) -> List[Callable[[], None]]:
        """Steps lowering SMD1 current to 0 then powering SMD1 off, if on."""
        if not (self.activation and self.full_activation):
            return []

        def full_off():
            self.full_activation = False
            self.apply()

        return self.__ramp(
            self.smd1_current_percentage, 0, 100, self.__set_smd1
        ) + [full_off]

    def __activation_steps(self) -> Tuple[List[Callable[[], None]], float]:
        """
        :return: Steps activating the laser if it is off, and the SMD2 current
            once activated.
        """
        if self.activation:
            return [], self.smd2_current

        def activate():
            self.full_activation = False
            self.activation = True
            self.apply()

        # Activation resets the currents to 0.
        return [activate], 0.0

    def low_power_steps(self, smd2_current: float) -> List[Callable[[], None]]:
        """
        Steps to operate in low power mode: SMD1 is off and the output is
        modulated by the SMD2 current. The laser is activated if it is off,
        and the currents are changed progressively. The steps must be called
        in order, :attr:`RAMP_PERIOD` seconds apart.

        :param smd2_current: SMD2 current, in A.
        """
        # Validate before activating the laser.
        maximum = self.smd2_current_full_scale
        if (smd2_current < 0) or (smd2_current > maximum):
            raise ValueError(
                f"SMD2 current {smd2_current}A out of bounds ({maximum}A max)"
            )
        steps = self.__smd1_off_steps()
        activation, current = self.__activation_steps()
        return (
            steps
            + activation
            + self.__ramp(current, smd2_current, maximum, self.__set_smd2)
        )

    def high_power_steps(
        self, smd1_current_percentage: float
    ) -> List[Callable[[], None]]:
        """
        Steps to operate in high power mode: SMD2 is at its maximum current
        and the output is modulated by the SMD1 current. The laser is
        activated if it is off, and the currents are changed progressively.
        The steps must be called in order, :attr:`RAMP_PERIOD` seconds apart.

        :param smd1_current_percentage: SMD1 current, in percentage of
            :attr:`smd1_current_max`.
        """
        # Validate before activating the laser.
        if (smd1_current_percentage < 0) or (smd1_current_percentage > 100):
            raise ValueError(
                f"SMD1 current {smd1_current_percentage}% out of bounds (0-100%)"
            )
        maximum = self.smd2_current_full_scale
        steps, current = self.__activation_steps()
        steps += self.__ramp(current, maximum, maximum, self.__set_smd2)
        if self.activation and self.full_activation:
            current = self.smd1_current_percentage
        else:
            current = 0.0

            def full_on():
                self.smd1_current_percentage = 0.0
                self.full_activation = True
                self.apply()

            steps.append(full_on)
        return steps + self.__ramp(
            current, smd1_current_percentage, 100, self.__set_smd1
        )

    def switch_off_steps(self) -> List[Callable[[], None]]:
        """
        Steps to switch the laser off, lowering the currents progressively.
        The steps must be called in order, :attr:`RAMP_PERIOD` seconds apart.
        """
        if not self.activation:
            return []
        steps = self.__smd1_off_steps()
        steps += self.__ramp(
            self.smd2_current, 0, self.smd2_current_full_scale, self.__set_smd2
        )

        def deactivate():
            self.activation = False
            self.full_activation = False
            self.apply()

        return steps + [deactivate]

    def run_steps(self, steps: List[Callable[[], None]]):
        """
        Call the given steps, :attr:`RAMP_PERIOD` seconds apart.
        """
        for i, step in enumerate(steps):
            if i:
                time.sleep(self.RAMP_PERIOD)
            step()

    def set_low_power(self, smd2_current: float):
        """
        Operate in low power mode: SMD1 is off and the output is modulated by
        the SMD2 current. The laser is activated if it is off. Currents are
        changed progressively, so this blocks for up to 10 seconds.

        :param smd2_current: SMD2 current, in A.
        """
        self.run_steps(self.low_power_steps(smd2_current))

    def set_high_power(self, smd1_current_percentage: float):
        """
        Operate in high power mode: SMD2 is at its maximum current and the
        output is modulated by the SMD1 current. The laser is activated if it
        is off. Currents are changed progressively, so this blocks for up to
        10 seconds.

        :param smd1_current_percentage: SMD1 current, in percentage of
            :attr:`smd1_current_max`.
        """
        self.run_steps(self.high_power_steps(smd1_current_percentage))

    def switch_off(self):
        """
        Switch the laser off. Currents are lowered progressively, so this
        blocks for up to 10 seconds.
        """
        self.run_steps(self.switch_off_steps())
