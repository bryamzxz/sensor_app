import os
import sys
from unittest import mock

import serial

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("TELEGRAM_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "x")

from server import conectar_serial, detectar_puerto_arduino


class DummyPort:
    def __init__(self, device: str, vid: int = 0x2341, pid: int = 0x1002):
        self.device = device
        self.vid = vid
        self.pid = pid


def test_conectar_serial_success():
    port = DummyPort("/dev/ttyUSB0")
    with mock.patch("serial.tools.list_ports.comports", return_value=[port]):
        ser_mock = mock.MagicMock(spec=serial.Serial)
        with mock.patch("serial.Serial", return_value=ser_mock):
            result = conectar_serial()
            assert result is ser_mock
            serial.Serial.assert_called_with(port.device, 115200, timeout=2)


def test_detectar_puerto_arduino_none():
    with mock.patch("serial.tools.list_ports.comports", return_value=[]):
        assert detectar_puerto_arduino() is None


