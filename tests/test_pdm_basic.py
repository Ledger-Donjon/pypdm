import struct
import pytest

from pypdm.pdm import PDM, Link, Command, Mode


def version_resp(v_major, v_minor, make_response):
    # DATA: U08_X, U08_Y
    return make_response(0x00, bytes([v_major, v_minor]))


def test_read_protocol_version(fake_serial_factory):
    # 1) __init__ va lire la version -> fournir une première réponse
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    fs.queue_response(version_resp(3, 4, fake_serial_factory.make_response))
    link = Link("/dev/ttyFAKE")
    pdm = PDM(1, link)
    # 2) lecture explicite -> fournir une seconde réponse
    fs.queue_response(version_resp(3, 5, fake_serial_factory.make_response))
    assert pdm.read_protocol_version() == "3.5"


def test_read_address_uses_address_zero(fake_serial_factory):
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    # __init__ handshake version
    fs.queue_response(version_resp(3, 4, fake_serial_factory.make_response))
    link = Link("/dev/ttyFAKE")
    pdm = PDM(7, link)
    # Réponse pour READ_ADDRESS: DATA0=U08_ADD
    fs.queue_response(fake_serial_factory.make_response(0x00, bytes([5])))
    addr = pdm.read_address()
    assert addr == 5
    # Vérifier que la trame envoyée utilisait ADD=0
    # Dernière écriture correspond au READ_ADDRESS
    frame = fs.writes[-1]
    assert frame[1] == 0  # ADD
    assert frame[2] == Command.READ_ADDRESS.value


def test_mode_from_read_cw_pulse(fake_serial_factory):
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    # __init__ handshake
    fs.queue_response(version_resp(3, 4, fake_serial_factory.make_response))
    link = Link("/dev/ttyFAKE")
    pdm = PDM(1, link)
    # Réponse pour READ_CW_PULSE: DATA0=STATE (0=pulsed, 1=continuous)
    fs.queue_response(fake_serial_factory.make_response(0x00, bytes([1])))
    assert pdm.mode == Mode.CONTINUOUS
    fs.queue_response(fake_serial_factory.make_response(0x00, bytes([0])))
    assert pdm.mode == Mode.PULSED


def test_offset_current_read_and_write(fake_serial_factory):
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    # __init__ handshake
    fs.queue_response(version_resp(3, 4, fake_serial_factory.make_response))
    link = Link("/dev/ttyFAKE")
    pdm = PDM(1, link)

    # Lecture: renvoyer F32 big-endian 12.5
    fs.queue_response(fake_serial_factory.make_response(0x00, struct.pack(">f", 12.5)))
    assert pytest.approx(pdm.offset_current, rel=1e-6) == 12.5

    # Écriture: vérifier WRITE_INSTRUCTION (0x10) avec U16 id + F32
    pdm.offset_current = 10.0
    frame = fs.writes[-1]
    assert frame[2] == Command.WRITE_INSTRUCTION.value
    # DATA = U16 instruction id (15) + F32
    data = frame[3:-1]  # sans checksum
    assert data[:2] == (15).to_bytes(2, "big")
    assert data[2:] == struct.pack(">f", 10.0)


