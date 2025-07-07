import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("TELEGRAM_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "x")

import serial  # noqa: E402

from server import (  # noqa: E402
    conectar_db,
    conectar_serial,
    flush_db,
    wal_checkpoint,
    parse_sensor_block,
    enviar_notificacion,
)  # noqa: E402


class DummySerial:
    def __init__(self, lines):
        self.lines = lines
        self.is_open = True
        self.index = 0

    def readline(self):
        if self.index < len(self.lines):
            line = self.lines[self.index]
            self.index += 1
            return line.encode()
        raise serial.SerialException("No more data")

    def close(self):
        self.is_open = False


# checkpoint failure


def test_flush_db_checkpoint_failure(tmp_path, monkeypatch):
    db_path = tmp_path / "db.sqlite"
    conn = conectar_db(db_path)
    buffer = [
        {
            "Tiempo": "2030-01-01 00:00:00",
            "TMP117_Temp": 1.0,
            "BME680_Temp": 2.0,
            "Humedad": 3.0,
            "Presion": 4.0,
            "Gas_Resistencia": 5.0,
        }
    ]

    def fake_safe_execute(conn, query, params=None):
        if "wal_checkpoint" in query:
            return False
        return True

    monkeypatch.setattr("server.safe_execute", fake_safe_execute)
    inserted = flush_db(conn, buffer)
    wal_checkpoint(conn)
    assert inserted == 1


def test_conectar_serial_reconnect():
    port = serial.tools.list_ports_common.ListPortInfo("/dev/ttyUSB0")
    port.vid = 0x2341
    port.pid = 0x1002

    ser_second = mock.Mock(spec=serial.Serial)

    serial_calls = [serial.SerialException("fail"), ser_second]

    def serial_side_effect(*args, **kwargs):
        result = serial_calls.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with mock.patch("serial.tools.list_ports.comports", return_value=[port]):
        with mock.patch("serial.Serial", side_effect=serial_side_effect):
            result = conectar_serial()
            assert result is ser_second


def test_full_flow(tmp_path, monkeypatch):
    db_path = tmp_path / "db.sqlite"
    conn = conectar_db(db_path)
    lines = [
        "------ Lecturas ------",
        "TMP117 Temp: 20.0 C",
        "BME680 Temp: 21.0 C",
        "Humedad: 50 %",
        "Presion: 1000 hPa",
        "Gas Resistencia: 200 kOhm",
        "",
    ]
    ser = DummySerial(lines)

    posts = []

    def fake_post(url, data, timeout):
        posts.append((url, data))

        class Resp:
            status_code = 200

            def json(self):
                return {"result": {"message_id": 1}}

            def raise_for_status(self):
                pass

        return Resp()

    monkeypatch.setattr("server.session.post", fake_post)

    header = ser.readline().decode()
    assert "Lecturas" in header
    sensor_lines = [ser.readline().decode().strip() for _ in range(6)]
    datos = {"Tiempo": "2030-01-01 00:00:00"}
    datos.update(parse_sensor_block(sensor_lines))
    inserted = flush_db(conn, [datos])
    wal_checkpoint(conn)
    enviar_notificacion(datos)

    assert inserted == 1
    assert posts
