import types
import struct
import pytest


def calc_chk(bytes_iterable):
    val = 0
    for b in bytes_iterable:
        val ^= b
    return (val - 1) % 256


def make_response(status: int, data: bytes) -> bytes:
    length = 3 + len(data)
    body = bytearray([length, status]) + bytearray(data)
    body.append(calc_chk(body))
    return bytes(body)


class FakeSerial:
    def __init__(self, dev, baudrate, timeout=None, write_timeout=None):
        self.dev = dev
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._rx_buffer = bytearray()
        self.writes = []

    def queue_response(self, frame: bytes):
        self._rx_buffer.extend(frame)

    def read(self, n: int) -> bytes:
        if n <= 0:
            return b""
        if not self._rx_buffer:
            return b""
        data = self._rx_buffer[:n]
        del self._rx_buffer[:n]
        return bytes(data)

    def write(self, b: bytes) -> int:
        self.writes.append(bytes(b))
        return len(b)


@pytest.fixture
def fake_serial_factory(monkeypatch):
    """
    Monkeypatch pypdm.pdm.serial.Serial pour renvoyer un FakeSerial.
    Retourne (factory, created) afin de pouvoir empiler des réponses.
    """
    import pypdm.pdm as pdm_mod

    created = []

    def factory(dev, baudrate=125000, timeout=None, write_timeout=None):
        fs = FakeSerial(dev, baudrate, timeout=timeout, write_timeout=write_timeout)
        created.append(fs)
        return fs

    monkeypatch.setattr(pdm_mod.serial, "Serial", factory)
    return types.SimpleNamespace(factory=factory, created=created, make_response=make_response, calc_chk=calc_chk)


