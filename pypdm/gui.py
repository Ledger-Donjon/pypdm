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


"""
Small control window for ALPhANOV's PDM and LFIPico laser sources, inspired by
ALPhANOV's LFIPico software. Only documented features are provided.

Requires PyQt6: ``pip install pypdm[gui]``, then run ``pypdm-gui``.
"""

import sys
from typing import Callable, List, Optional

from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

from .lfipico import Alarm, LFIPico
from .pdm import (
    PDM,
    ControlMode,
    CurrentSource,
    DelayLineType,
    InterlockStatus,
    Mode,
    SyncSource,
)


# Item data role holding the serial number of a port in the port list.
SERIAL_NUMBER_ROLE = Qt.ItemDataRole.UserRole + 1

# Polling period of the device state, in ms.
POLL_PERIOD = 1000

STYLE = """
QGroupBox { font-weight: bold; border: 1px solid #0b5c7a; border-radius: 3px;
    margin-top: 1.4em; padding: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 4px;
    color: #0b5c7a; }
QPushButton:checked { background-color: #0b5c7a; color: white;
    border: 1px solid #0b5c7a; border-radius: 3px; padding: 4px; }
"""

# Alarm labels, as named in the LFIPico Hexa Programming Manual.
ALARM_LABELS = {
    Alarm.MAIN_POWER_SUPPLY: "Main Power Supply",
    Alarm.HOUSEKEEPING_POWER_SUPPLY: "Housekeeping Power Supply",
    Alarm.RED_GUIDE: "Red Guide",
    Alarm.SMD1_TEMPERATURE: "T° SMD1",
    Alarm.SMD2_TEMPERATURE: "T° SMD2",
    Alarm.SMD2_AVERAGE_CURRENT: "SMD2 Average Current",
    Alarm.CASE_TEMPERATURE: "T° Case",
    Alarm.BAD_START_SEQUENCE: "Bad Start Sequence",
    Alarm.CASE_OPEN: "Case Open",
    Alarm.EXTERNAL_POWER_CUT: "External Power Cut",
    Alarm.PD_IN_LOW: "PD_IN Low",
    Alarm.PD_OUT_LOW: "PD_OUT Low",
    Alarm.PD_CRI_LOW: "PD_CRI Low",
    Alarm.LASER_RETURN: "Laser Return",
    Alarm.DRIVER_ALARM: "Driver Alarm",
    Alarm.MMD1_ALARM: "MMD1 Alarm",
    Alarm.MMD2_ALARM: "MMD2 Alarm",
    Alarm.MMD3_ALARM: "MMD3 Alarm",
    Alarm.WATCHDOG_PD_PULSE: "Watchdog PD_PULSE",
}


class Led(QLabel):
    """Round indicator light."""

    COLORS = {None: "#9a9a9a", False: "#2ea043", True: "#d62828"}

    def __init__(self):
        super().__init__()
        self.setFixedSize(14, 14)
        self.set_state(None)

    def set_state(self, alarm: Optional[bool]):
        """
        :param alarm: None for unknown, False for OK (green), True for alarm
            (red).
        """
        self.setStyleSheet(
            f"background-color: {self.COLORS[alarm]}; border-radius: 7px;"
        )


class Toggle:
    """Exclusive checkable buttons, like the original ALPhANOV software."""

    def __init__(self, parent: QWidget, labels: List[str]):
        self.group = QButtonGroup(parent)
        self.buttons = []
        for i, text in enumerate(labels):
            button = QPushButton(text)
            button.setCheckable(True)
            self.group.addButton(button, i)
            self.buttons.append(button)
        self.buttons[0].setChecked(True)

    def add_to(self, grid: QGridLayout, row: int, col: int):
        for i, button in enumerate(self.buttons):
            grid.addWidget(button, row, col + i)

    def index(self) -> int:
        return self.group.checkedId()

    def set_index(self, index: int):
        self.buttons[index].setChecked(True)

    def set_enabled(self, enabled: bool):
        for button in self.buttons:
            button.setEnabled(enabled)

    def on_click(self, callback: Callable[[int], None]):
        self.group.idClicked.connect(callback)


def spin(
    suffix: str, decimals: int, maximum: float, minimum: float = 0
) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setSuffix(suffix)
    box.setDecimals(decimals)
    box.setRange(minimum, maximum)
    box.setKeyboardTracking(False)
    return box


class DevicePanel:
    """
    Device specific part of the window: settings and status widgets, and laser
    activation.
    """

    name = ""
    default_address = 0

    def __init__(self, window: "Window"):
        self.window = window
        self.settings = QGroupBox(f"{self.name} Settings")
        self.status = QGroupBox("Status")

    def open(self, port: str, address: int) -> str:
        """
        Open the device, and load its settings in the widgets.

        :return: Device information text.
        """
        raise NotImplementedError()

    def close(self):
        """Release the device. Deleting the device switches the laser off."""
        raise NotImplementedError()

    def laser_on(self):
        raise NotImplementedError()

    def laser_off(self):
        raise NotImplementedError()

    def poll(self) -> bool:
        """
        Refresh status widgets.

        :return: Laser activation state.
        """
        raise NotImplementedError()

    def set_active(self, active: bool):
        """Called when the laser is switched on or off."""
        pass

    def clear_status(self):
        pass

    def write(self, action: Callable[[], None]):
        """Run a settings change, then apply, reporting errors."""
        if not self.window.connected:
            return
        try:
            action()
            self.device.apply()
        except Exception as e:
            self.window.error(e)
            self.load()

    def load(self):
        """Load the device settings in the widgets."""
        pass


class PDMPanel(DevicePanel):
    name = "PDM"
    default_address = 1

    SYNC_SOURCES = [
        SyncSource.INTERNAL,
        SyncSource.EXTERNAL_TTL_LVTTL,
        SyncSource.EXTERNAL_LVDS,
    ]

    def __init__(self, window: "Window"):
        super().__init__(window)
        self.device: Optional[PDM] = None
        grid = QGridLayout(self.settings)
        grid.setVerticalSpacing(4)

        self.sync = Toggle(self.settings, ["Int", "TTL/LVTTL", "LVDS"])
        self.sync.add_to(grid, 1, 0)
        grid.addWidget(QLabel("Sync Source"), 0, 0, 1, 3)
        self.sync.on_click(
            lambda i: self.write(
                lambda: setattr(self.device, "sync_source", self.SYNC_SOURCES[i])
            )
        )
        self.delay_line = Toggle(self.settings, ["None", "Internal"])
        self.delay_line.add_to(grid, 1, 3)
        grid.addWidget(QLabel("Delay Line"), 0, 3, 1, 2)
        self.delay_line.on_click(
            lambda i: self.write(
                lambda: setattr(self.device, "delay_line_type", DelayLineType(i))
            )
        )

        self.frequency = QSpinBox()
        self.frequency.setSuffix(" Hz")
        self.frequency.setRange(1, PDM.MAX_FREQUENCY)
        self.frequency.setKeyboardTracking(False)
        self.frequency.setGroupSeparatorShown(True)
        self.frequency.editingFinished.connect(
            lambda: self.write(
                lambda: setattr(self.device, "frequency", self.frequency.value())
            )
        )
        grid.addWidget(self.frequency, 3, 0, 1, 3)
        grid.addWidget(QLabel("Frequency (internal sync)"), 2, 0, 1, 3)
        self.pulse_width = spin(" ns", 3, PDM.MAX_PULSE_WIDTH / 1000)
        self.pulse_width.editingFinished.connect(
            lambda: self.write(
                lambda: setattr(
                    self.device, "pulse_width", round(self.pulse_width.value() * 1000)
                )
            )
        )
        grid.addWidget(self.pulse_width, 3, 3, 1, 2)
        grid.addWidget(QLabel("Pulse Width"), 2, 3, 1, 2)
        self.delay = spin(" ns", 3, PDM.MAX_DELAY / 1000)
        self.delay.editingFinished.connect(
            lambda: self.write(
                lambda: setattr(self.device, "delay", round(self.delay.value() * 1000))
            )
        )
        grid.addWidget(self.delay, 5, 0, 1, 3)
        grid.addWidget(QLabel("Delay"), 4, 0, 1, 3)
        self.offset = spin(" mA", 1, 150)
        self.offset.editingFinished.connect(
            lambda: self.write(
                lambda: setattr(self.device, "offset_current", self.offset.value())
            )
        )
        grid.addWidget(self.offset, 5, 3, 1, 2)
        grid.addWidget(QLabel("Offset Current"), 4, 3, 1, 2)

        self.source = Toggle(self.settings, ["Analog", "Numeric"])
        self.source.add_to(grid, 7, 0)
        grid.addWidget(QLabel("Current Source"), 6, 0, 1, 3)
        self.source.on_click(
            lambda i: self.write(
                lambda: setattr(self.device, "current_source", CurrentSource(i))
            )
        )
        self.current = spin(" mA", 1, 0)
        self.current.editingFinished.connect(
            lambda: self.write(
                lambda: setattr(self.device, "current", self.current.value())
            )
        )
        grid.addWidget(self.current, 7, 3, 1, 2)
        grid.addWidget(QLabel("Current (numeric source)"), 6, 3, 1, 2)

        # Protocol 3.7 only.
        self.control = Toggle(self.settings, ["Hardware", "Software"])
        self.control.add_to(grid, 9, 0)
        self.control_label = QLabel("Control Mode Selection (protocol 3.7)")
        grid.addWidget(self.control_label, 8, 0, 1, 3)
        self.control.on_click(
            lambda i: self.write(
                lambda: setattr(self.device, "control_mode_selection", ControlMode(i))
            )
        )
        self.software_mode = Toggle(self.settings, ["Pulsed", "CW"])
        self.software_mode.add_to(grid, 9, 3)
        self.software_mode_label = QLabel("Software Control Mode")
        grid.addWidget(self.software_mode_label, 8, 3, 1, 2)
        self.software_mode.on_click(
            lambda i: self.write(
                lambda: setattr(self.device, "software_control_mode", Mode(i))
            )
        )

        grid = QGridLayout(self.status)
        grid.setHorizontalSpacing(12)
        self.interlock_led = Led()
        grid.addWidget(self.interlock_led, 0, 0)
        grid.addWidget(QLabel("Interlock"), 0, 1)
        self.mode_label = QLabel("")
        grid.addWidget(self.mode_label, 0, 2)
        self.temperature = QLabel("")
        grid.addWidget(self.temperature, 0, 3)

    def open(self, port: str, address: int) -> str:
        self.device = PDM(address, port)
        pdm = self.device
        self.current.setMaximum(pdm.maximum_current)
        self.load()
        return (
            f"PDM protocol {pdm.version} — max current {pdm.maximum_current:.0f} mA"
            f" — max mean current {pdm.maximum_mean_current:.0f} mA"
        )

    def close(self):
        self.device = None

    def load(self):
        pdm = self.device
        self.sync.set_index(self.SYNC_SOURCES.index(pdm.sync_source))
        self.delay_line.set_index(pdm.delay_line_type.value)
        self.frequency.setValue(pdm.frequency)
        self.pulse_width.setValue(pdm.pulse_width / 1000)
        self.delay.setValue(pdm.delay / 1000)
        self.offset.setValue(pdm.offset_current)
        self.source.set_index(pdm.current_source.value)
        self.current.setValue(pdm.current)
        v37 = pdm.version == "3.7"
        for widget in [self.control_label, self.software_mode_label]:
            widget.setEnabled(v37)
        self.control.set_enabled(v37)
        self.software_mode.set_enabled(v37)
        if v37:
            self.control.set_index(pdm.control_mode_selection.value)
            self.software_mode.set_index(pdm.software_control_mode.value)

    def laser_on(self):
        if self.device.interlock_status != InterlockStatus.CLOSED:
            QMessageBox.information(
                self.window,
                self.window.windowTitle(),
                "Interlock is open: the laser cannot pulse.",
            )
        self.device.activation = True
        self.device.apply()

    def laser_off(self):
        self.device.activation = False
        self.device.apply()

    def poll(self) -> bool:
        pdm = self.device
        active = pdm.activation
        interlock = pdm.interlock_status
        mode = pdm.mode
        temperature = pdm.temperature
        self.interlock_led.set_state(interlock != InterlockStatus.CLOSED)
        self.interlock_led.setToolTip(interlock.name)
        self.mode_label.setText(
            f"Mode: {'CW' if mode == Mode.CONTINUOUS else 'Pulsed'}"
        )
        self.temperature.setText(f"Temperature: {temperature:.1f} °C")
        return active

    def clear_status(self):
        self.interlock_led.set_state(None)
        self.mode_label.setText("")
        self.temperature.setText("")


class LFIPicoPanel(DevicePanel):
    name = "LFIPico"
    default_address = LFIPico.DEFAULT_ADDRESS

    def __init__(self, window: "Window"):
        super().__init__(window)
        self.device: Optional[LFIPico] = None
        grid = QGridLayout(self.settings)
        grid.setVerticalSpacing(4)

        self.power_mode = Toggle(self.settings, ["Low", "High"])
        self.power_mode.add_to(grid, 1, 0)
        grid.addWidget(QLabel("Power Mode (chosen before activation)"), 0, 0, 1, 2)
        self.power_mode.on_click(lambda i: self.update_mode())
        self.low_adj = spin(" A", 3, 0)
        self.low_adj.setSingleStep(0.01)
        self.low_adj.editingFinished.connect(self.adjust_low)
        grid.addWidget(self.low_adj, 3, 0)
        self.low_label = QLabel("Low Power Adj. (SMD2)")
        grid.addWidget(self.low_label, 2, 0)
        self.high_adj = spin(" %", 1, 100)
        self.high_adj.editingFinished.connect(self.adjust_high)
        grid.addWidget(self.high_adj, 3, 1)
        self.high_label = QLabel("High Power Adj. (SMD1)")
        grid.addWidget(self.high_label, 2, 1)
        self.readback = QLabel("")
        self.readback.setStyleSheet("color: gray;")
        grid.addWidget(self.readback, 4, 0, 1, 2)
        self.update_mode()

        grid = QGridLayout(self.status)
        grid.setHorizontalSpacing(12)
        self.interlock_led = Led()
        grid.addWidget(self.interlock_led, 0, 0)
        grid.addWidget(QLabel("Interlock (latched alarms)"), 0, 1, 1, 3)
        self.alarm_leds = {}
        for i, alarm in enumerate(Alarm):
            led = Led()
            self.alarm_leds[alarm] = led
            r, c = divmod(i, 2)
            grid.addWidget(led, r + 1, c * 2)
            grid.addWidget(QLabel(ALARM_LABELS[alarm]), r + 1, c * 2 + 1)

    def open(self, port: str, address: int) -> str:
        self.device = LFIPico(port, address)
        pico = self.device
        self.low_adj.setMaximum(
            min(LFIPico.MAX_SMD2_CURRENT, pico.smd2_peak_current_max)
        )
        high = pico.activation and pico.full_activation
        self.power_mode.set_index(int(high))
        self.load()
        self.update_mode()
        return (
            f"LFIPico S/N {pico.serial_number} — firmware {pico.firmware_version}"
            f" — protocol {pico.version} — SMD1 max {pico.smd1_current_max:.2f} A"
            f" — SMD2 max {pico.smd2_peak_current_max:.2f} A"
        )

    def close(self):
        self.device = None

    def load(self):
        if self.device.activation:
            self.low_adj.setValue(self.device.smd2_current)
            self.high_adj.setValue(self.device.smd1_current_percentage)

    def high(self) -> bool:
        return self.power_mode.index() == 1

    def update_mode(self):
        """Enable the adjustment of the selected power mode."""
        high = self.high()
        for widget in [self.low_adj, self.low_label]:
            widget.setEnabled(not high)
        for widget in [self.high_adj, self.high_label]:
            widget.setEnabled(high)

    def set_active(self, active: bool):
        self.power_mode.set_enabled(not active)

    def laser_on(self):
        if self.high():
            self.device.set_high_power(self.high_adj.value())
        else:
            self.device.set_low_power(self.low_adj.value())

    def laser_off(self):
        self.device.activation = False
        self.device.full_activation = False
        self.device.apply()

    def adjust_low(self):
        if self.window.is_on() and not self.high():
            self.write(
                lambda: setattr(self.device, "smd2_current", self.low_adj.value())
            )

    def adjust_high(self):
        if self.window.is_on() and self.high():
            self.write(
                lambda: setattr(
                    self.device, "smd1_current_percentage", self.high_adj.value()
                )
            )

    def poll(self) -> bool:
        pico = self.device
        active = pico.activation
        alarms = pico.alarms
        interlock = pico.interlock_alarms
        self.readback.setText(
            f"Readback: SMD2 {pico.smd2_current:.3f} A — "
            f"SMD1 {pico.smd1_current_percentage:.1f} % "
            f"({'on' if pico.full_activation else 'off'})"
        )
        self.interlock_led.set_state(bool(interlock))
        self.interlock_led.setToolTip(str(interlock))
        for alarm, led in self.alarm_leds.items():
            led.set_state(alarm in alarms)
        return active

    def clear_status(self):
        self.readback.setText("")
        for led in [self.interlock_led, *self.alarm_leds.values()]:
            led.set_state(None)


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.connected = False
        self.active = False
        self.setWindowTitle("PyPDM")
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)

        # Connection
        box = QGroupBox("Connection")
        row = QHBoxLayout(box)
        self.device_type = QComboBox()
        row.addWidget(self.device_type)
        self.port = QComboBox()
        self.port.setMinimumWidth(240)
        self.refresh_ports()
        row.addWidget(self.port, 1)
        refresh = QPushButton("↻")
        refresh.setToolTip("Refresh serial ports")
        refresh.setFixedWidth(30)
        refresh.clicked.connect(self.refresh_ports)
        row.addWidget(refresh)
        row.addWidget(QLabel("Address"))
        self.address = QSpinBox()
        self.address.setRange(0, 255)
        row.addWidget(self.address)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        row.addWidget(self.connect_button)
        layout.addWidget(box)
        self.info = QLabel("")
        self.info.setStyleSheet("color: gray;")
        layout.addWidget(self.info)

        # Laser control
        box = QGroupBox("Laser Control")
        grid = QGridLayout(box)
        self.activation = Toggle(box, ["Off", "On"])
        self.activation.add_to(grid, 1, 0)
        grid.addWidget(QLabel("Laser Activation"), 0, 0, 1, 2)
        self.activation.on_click(self.activation_clicked)
        self.control = box
        layout.addWidget(box)

        self.panels: List[DevicePanel] = [PDMPanel(self), LFIPicoPanel(self)]
        for panel in self.panels:
            self.device_type.addItem(panel.name)
            layout.addWidget(panel.settings)
            layout.addWidget(panel.status)
        self.device_type.currentIndexChanged.connect(self.select_device)
        self.select_device()
        self.load_selection()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.set_connected(False)

    @property
    def panel(self) -> DevicePanel:
        return self.panels[self.device_type.currentIndex()]

    def select_device(self):
        for panel in self.panels:
            visible = panel is self.panel
            panel.settings.setVisible(visible)
            panel.status.setVisible(visible)
        self.address.setValue(self.panel.default_address)
        self.adjustSize()

    def refresh_ports(self):
        self.port.clear()
        ports = sorted(list_ports.comports(), key=lambda p: p.device)
        # Hide legacy ports without USB adapter, unless there is no other.
        ports = [p for p in ports if p.vid is not None] or ports
        for p in ports:
            label = p.device
            if p.serial_number:
                label += f"  (SN {p.serial_number})"
            self.port.addItem(label, p.device)
            self.port.setItemData(
                self.port.count() - 1, p.serial_number, SERIAL_NUMBER_ROLE
            )

    def load_selection(self):
        """Restore the device type, port and address selected last time."""
        settings = QSettings("Ledger", "pypdm")
        index = self.device_type.findText(settings.value("device_type", "", str))
        if index >= 0:
            self.device_type.setCurrentIndex(index)
        # Serial number first, as device paths may change between sessions.
        serial_number = settings.value("port_serial_number", "", str)
        index = -1
        if serial_number:
            index = self.port.findData(serial_number, SERIAL_NUMBER_ROLE)
        if index < 0:
            index = self.port.findData(settings.value("port", "", str))
        if index >= 0:
            self.port.setCurrentIndex(index)
        address = settings.value("address", None)
        if address is not None:
            self.address.setValue(int(address))

    def save_selection(self):
        """Save the device type, port and address for the next session."""
        settings = QSettings("Ledger", "pypdm")
        settings.setValue("device_type", self.device_type.currentText())
        settings.setValue("port", self.port.currentData() or "")
        settings.setValue(
            "port_serial_number", self.port.currentData(SERIAL_NUMBER_ROLE) or ""
        )
        settings.setValue("address", self.address.value())

    def error(self, e: Exception):
        QMessageBox.critical(self, self.windowTitle(), f"{type(e).__name__}: {e}")

    def set_connected(self, connected: bool):
        self.connected = connected
        self.control.setEnabled(connected)
        for panel in self.panels:
            panel.settings.setEnabled(connected)
        for widget in [self.device_type, self.port, self.address]:
            widget.setEnabled(not connected)
        self.connect_button.setText("Disconnect" if connected else "Connect")
        if not connected:
            self.timer.stop()
            self.set_active(False)
            self.panel.clear_status()
            self.info.setText("Not connected")

    def toggle_connection(self):
        if self.connected:
            self.disconnect()
            return
        try:
            info = self.panel.open(self.port.currentData(), self.address.value())
            self.info.setText(info)
        except Exception as e:
            self.panel.close()
            self.error(e)
            return
        self.set_connected(True)
        self.poll()
        self.timer.start(POLL_PERIOD)

    def disconnect(self):
        try:
            self.laser_off()
        finally:
            self.panel.close()
            self.set_connected(False)

    def is_on(self) -> bool:
        return self.active

    def activation_clicked(self, index: int):
        if index and not self.active:
            self.laser_on()
        elif not index and self.active:
            self.laser_off()

    def set_active(self, active: bool):
        self.active = active
        self.activation.set_index(int(active))
        self.panel.set_active(active)

    def laser_on(self):
        answer = QMessageBox.warning(
            self,
            self.windowTitle(),
            "Class 4 laser. Enable laser emission?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.set_active(False)
            return
        try:
            self.panel.laser_on()
            self.set_active(True)
        except Exception as e:
            self.error(e)
            self.laser_off()
        self.poll()

    def laser_off(self):
        self.set_active(False)
        if self.connected:
            try:
                self.panel.laser_off()
            except Exception as e:
                self.error(e)

    def poll(self):
        """Refresh the device status."""
        if not self.connected:
            return
        try:
            active = self.panel.poll()
        except Exception as e:
            # Communication lost: do not try to switch the laser off.
            self.panel.close()
            self.set_connected(False)
            self.error(e)
            return
        if active != self.is_on():
            # For instance, switched off by the interlock.
            self.set_active(active)

    def closeEvent(self, event):
        self.save_selection()
        if self.connected:
            self.disconnect()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
