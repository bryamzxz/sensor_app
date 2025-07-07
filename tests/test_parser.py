import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("TELEGRAM_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "x")

from server import parse_sensor_block


def test_parse_sensor_block_valid():
    lines = [
        "TMP117 Temp: 25.2 C",
        "BME680 Temp: 25.6 C",
        "Humedad: 40 %",
        "Presion: 1015 hPa",
        "Gas Resistencia: 900 kOhm",
        "",
    ]
    expected = {
        "TMP117_Temp": 25.2,
        "BME680_Temp": 25.6,
        "Humedad": 40.0,
        "Presion": 1015.0,
        "Gas_Resistencia": 900.0,
    }
    assert parse_sensor_block(lines) == expected


def test_parse_sensor_block_invalid():
    lines = ["foo", "bar"]
    assert parse_sensor_block(lines) == {}


