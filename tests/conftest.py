import types
import os
import pytest
from typing import Optional, Iterable, List
from serial.serialutil import SerialException
from serial import Serial
import pypdm.pdm as pdm_mod


def calc_chk(bytes_iterable: Iterable[int]) -> int:
    val = 0
    for b in bytes_iterable:
        val ^= b
    return (val - 1) % 256


def make_response(status: int, data: bytes = bytes()) -> bytes:
    length = 3 + len(data)
    body = bytearray([length, status]) + bytearray(data)
    body.append(calc_chk(body))
    return bytes(body)


OK_RESP = make_response(0)


class FakeSerial:
    def __init__(
        self,
        dev: str,
        baudrate: int,
        timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
    ):
        self.is_fake = "FAKE" in dev
        self.dev = dev
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._rx_buffer = bytearray()
        self.writes: List[bytes] = []
        if not self.is_fake:
            try:
                self.serial = Serial(
                    dev, baudrate, timeout=timeout, write_timeout=write_timeout
                )
            except SerialException as e:
                raise pdm_mod.ConnectionFailure() from e

    def queue_response(self, frame: bytes):
        self._rx_buffer.extend(frame)

    def read(self, n: int) -> bytes:
        if not self.is_fake:
            return self.serial.read(n)
        if n <= 0:
            return b""
        if not self._rx_buffer:
            return b""
        data = self._rx_buffer[:n]
        del self._rx_buffer[:n]
        return bytes(data)

    def write(self, b: bytes) -> int:
        if not self.is_fake:
            return self.serial.write(b)  # type: ignore
        self.writes.append(bytes(b))
        return len(b)


@pytest.fixture
def fake_serial_factory(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """
    Monkeypatch pypdm.pdm.serial.Serial to return a FakeSerial.
    Returns (factory, created) so you can enqueue responses.
    """

    created: List[FakeSerial] = []

    def factory(
        dev: str,
        baudrate: int = 125000,
        timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
    ) -> FakeSerial:
        fs = FakeSerial(dev, baudrate, timeout=timeout, write_timeout=write_timeout)
        created.append(fs)
        return fs

    monkeypatch.setattr(pdm_mod.serial, "Serial", factory)
    return types.SimpleNamespace(
        factory=factory,
        created=created,
        make_response=make_response,
        calc_chk=calc_chk,
        OK_RESP=OK_RESP,
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--device",
        action="store",
        default=None,
        help="Path to serial device for real tests (e.g., /dev/ttyUSB0 or COM3)",
    )


def _resolve_device_path(config: pytest.Config) -> Optional[str]:
    cli = config.getoption("--device")
    if cli:
        return cli
    return os.getenv("PYPDM_DEVICE")


@pytest.fixture
def device_path(request: pytest.FixtureRequest) -> str:
    """
    Returns the real device path for tests marked as 'real', or skips if missing.
    """
    dev = _resolve_device_path(request.config)
    if not dev:
        pytest.skip(
            "Real tests skipped: no device path provided (--device or PYPDM_DEVICE)."
        )
    return dev


def pytest_collection_modifyitems(
    config: pytest.Config, items: List[pytest.Item]
) -> None:
    """
    Auto-skip tests marked 'real' when no device path is provided.
    """
    device = _resolve_device_path(config)
    if device:
        return
    skip_marker = pytest.mark.skip(
        reason="Real tests skipped: no device path provided (--device or PYPDM_DEVICE)."
    )
    for item in items:
        if "real" in item.keywords:
            item.add_marker(skip_marker)
