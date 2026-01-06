import struct
import pytest

from pypdm.pdm import Link, Command, StatusError, ChecksumError, ProtocolError


def test_send_frame_and_checksum(fake_serial_factory):
    # Préparer une réponse OK minimale (LEN=3, STS=0x00)
    resp = fake_serial_factory.make_response(0x00, b"")
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    fs.queue_response(resp)

    link = Link("/dev/ttyFAKE")
    link.command(1, Command.READ_PROTOCOL_VERSION, b"")

    assert len(fs.writes) == 1
    frame = fs.writes[0]
    # LEN, ADD, CMD, CHK
    assert len(frame) == 4
    assert frame[0] == 4
    assert frame[1] == 1
    assert frame[2] == Command.READ_PROTOCOL_VERSION.value
    # Vérifier checksum XOR-1
    chk = fake_serial_factory.calc_chk(frame[:-1])
    assert frame[-1] == chk


def test_status_error_timeout(fake_serial_factory):
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    # Réponse statut TIMEOUT (0x01), LEN=3
    fs.queue_response(fake_serial_factory.make_response(0x01, b""))
    link = Link("/dev/ttyFAKE")
    with pytest.raises(StatusError) as ei:
        link.command(1, Command.READ_PROTOCOL_VERSION, b"")
    assert int(ei.value.status) == 0x01


def test_checksum_error_detected(fake_serial_factory):
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    # Construire une réponse avec mauvais checksum
    body = bytearray([3, 0x00])  # LEN=3, STS=0x00, pas de data
    bad_chk = (fake_serial_factory.calc_chk(body) + 1) % 256  # rendre faux
    body.append(bad_chk)
    fs.queue_response(bytes(body))
    link = Link("/dev/ttyFAKE")
    with pytest.raises(ChecksumError):
        link.command(1, Command.READ_PROTOCOL_VERSION, b"")


def test_protocol_error_on_short_length(fake_serial_factory):
    fs = fake_serial_factory.factory("/dev/ttyFAKE")
    # LEN=2 (inférieur à 3) -> ProtocolError
    # Le code lit d'abord 1 octet (LEN), puis vérifie.
    fs.queue_response(bytes([2]))
    link = Link("/dev/ttyFAKE")
    with pytest.raises(ProtocolError):
        link.command(1, Command.READ_PROTOCOL_VERSION, b"")


