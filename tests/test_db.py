import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("TELEGRAM_TOKEN", "x")
os.environ.setdefault("TELEGRAM_CHAT_ID", "x")

from server import conectar_db, flush_db, safe_execute, wal_checkpoint  # noqa: E402


def test_safe_execute_error(tmp_path):
    db_path = tmp_path / "db.sqlite"
    conn = conectar_db(db_path)
    # Force error by executing bad query
    result = safe_execute(conn, "INSERT INTO no_table VALUES (1)")
    assert result is False


def test_flush_db(tmp_path):
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

    inserted = flush_db(conn, buffer)
    wal_checkpoint(conn)
    assert inserted == 1
    cur = conn.execute("SELECT COUNT(*) FROM lecturas")
    assert cur.fetchone()[0] == 1
