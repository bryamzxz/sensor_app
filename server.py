#!/usr/bin/env python3
"""Aplicación principal para la captura de sensores."""

import os
import sys
import time
import random
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
import requests
import serial
import serial.tools.list_ports
from datetime import datetime
from typing import Any, Dict
import pytz

__version__ = "1.0.0"

# ------------------------------
# ⚙️ Configuración general
# ------------------------------
ZONA_HORARIA_LOCAL = pytz.timezone("America/Bogota")
DATA_DIR = "data"
LOG_DIR = "logs"
DB_FILE = os.path.join(DATA_DIR, "datos.db")
LOG_FILE = os.path.join(LOG_DIR, "eventos.log")

MIN_ESCRITURA_DB = 300  # 5 minutos
MAX_ESCRITURA_DB = 600  # 10 minutos

load_dotenv()  # lee .env y carga las variables en os.environ

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    logging.error(
        "❌ Debes definir TELEGRAM_TOKEN y TELEGRAM_CHAT_ID en las variables de entorno."
    )
    sys.exit(1)

ARDUINO_VID = 0x2341
ARDUINO_PID = 0x1002

COLUMNAS = [
    "Tiempo",
    "TMP117_Temp",
    "BME680_Temp",
    "Humedad",
    "Presion",
    "Gas_Resistencia",
]

# ------------------------------
# 📓 Logging con zona local y rotación
# ------------------------------
os.makedirs(LOG_DIR, exist_ok=True)


class TZFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, ZONA_HORARIA_LOCAL)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
fmt = "%(asctime)s - %(levelname)s - %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
handler.setFormatter(TZFormatter(fmt, datefmt))
logger.addHandler(handler)


# ------------------------------
# 🗄️ SQLite optimizado y seguro
# ------------------------------
def conectar_db(path):
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute(
        """
      CREATE TABLE IF NOT EXISTS lecturas (
        Tiempo TEXT PRIMARY KEY,
        TMP117_Temp REAL,
        BME680_Temp REAL,
        Humedad REAL,
        Presion REAL,
        Gas_Resistencia REAL
      )
    """
    )
    return conn


# --- [ELIMINADO] La función obtener_ultimo_registro ya no es necesaria ---


def parse_sensor_block(lines: list[str]) -> Dict[str, float]:
    """Parsea un bloque de líneas proveniente del serial."""
    datos: Dict[str, float] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        val = val.strip().split(" ")[0]
        try:
            num = float(val)
        except ValueError:
            continue
        if "TMP117 Temp" in key:
            datos["TMP117_Temp"] = num
        elif "BME680 Temp" in key:
            datos["BME680_Temp"] = num
        elif "Humedad" in key:
            datos["Humedad"] = num
        elif "Presion" in key or "Presión" in key:
            datos["Presion"] = num
        elif "Gas Resistencia" in key:
            datos["Gas_Resistencia"] = num
    return datos


def safe_execute(conn: sqlite3.Connection, query: str, params: tuple | None = None) -> bool:
    """Ejecuta una consulta SQLite y registra cualquier error."""
    try:
        if params is None:
            conn.execute(query)
        else:
            conn.execute(query, params)
        return True
    except sqlite3.DatabaseError as e:
        logging.error(f"❌ Error en DB: {e}")
        return False


def flush_db(conn: sqlite3.Connection, buffer: list[Dict[str, Any]]) -> int:
    """Inserta los registros del buffer en la base de datos de forma segura."""
    registros = [tuple(d.get(c) for c in COLUMNAS) for d in buffer]
    try:
        with conn:
            conn.executemany("INSERT OR REPLACE INTO lecturas VALUES (?,?,?,?,?,?)", registros)
    except sqlite3.DatabaseError as e:
        logging.error(f"❌ Error al escribir en BD: {e}")
        return 0
    safe_execute(conn, "DELETE FROM lecturas WHERE Tiempo < datetime('now','-7 days')")
    conn.commit()
    return len(registros)


# ------------------------------
# 🔌 Serial con reconexión
# ------------------------------
def detectar_puerto_arduino():
    for p in serial.tools.list_ports.comports():
        if p.vid == ARDUINO_VID and p.pid == ARDUINO_PID:
            logging.info(f"Arduino detectado en {p.device}")
            return p.device
    return None


def conectar_serial():
    while True:
        puerto = detectar_puerto_arduino()
        if puerto:
            try:
                ser = serial.Serial(puerto, 115200, timeout=2)
                logging.info(f"Conectado a {puerto}")
                ser.reset_input_buffer()
                return ser
            except serial.SerialException as e:
                logging.error(f"Error abriendo {puerto}: {e}")
        else:
            logging.warning("Esperando conexión con Arduino...")
        time.sleep(5)


# ------------------------------
# 📲 Envío a Telegram
# ------------------------------
session = requests.Session()
session.headers.update({"Connection": "keep-alive"})


def enviar_notificacion(datos):
    if not datos:
        logging.warning("No hay datos para notificar.")
        return

    tiempo_para_mostrar = datos.get("Tiempo", "N/A")
    if datos.get("Tiempo"):
        try:
            dt_utc = datetime.strptime(datos["Tiempo"], "%Y-%m-%d %H:%M:%S")
            dt_utc = pytz.utc.localize(dt_utc)
            dt_local = dt_utc.astimezone(ZONA_HORARIA_LOCAL)
            tiempo_para_mostrar = dt_local.strftime("%Y-%m-%d %H:%M:%S %Z")
        except (ValueError, TypeError) as e:
            logging.error(f"Error convirtiendo tiempo para notificación: {e}")

    # [MEJORA] Formateo de números a 2 decimales para un mensaje más limpio
    mensaje = (
        f"📊 **Lectura de Sensores** 📊\n\n"
        f"🕒 **Tiempo:** {tiempo_para_mostrar}\n"
        f"🌡️ **TMP117:** {datos.get('TMP117_Temp', 0):.2f} °C\n"
        f"🌡️ **BME680:** {datos.get('BME680_Temp', 0):.2f} °C\n"
        f"💧 **Humedad:** {datos.get('Humedad', 0):.2f} %\n"
        f"📈 **Presión:** {datos.get('Presion', 0):.2f} hPa\n"
        f"🟢 **Gas:** {datos.get('Gas_Resistencia', 0):.2f} kΩ"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    logging.info(f"🔔 Notificando a Telegram con datos de las {tiempo_para_mostrar}")

    r = None
    try:
        r = session.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": mensaje,
                "parse_mode": "Markdown",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        msg_id = data.get("result", {}).get("message_id", "n/a")
        logging.info(f"🔔 Telegram OK: status {r.status_code}, message_id={msg_id}")
    except requests.exceptions.RequestException as e:
        error_msg = f"❌ Error de red en Telegram: {e}"
        if r is not None:
            error_msg += f"; status={r.status_code}; resp={r.text[:200]}"
        logging.error(error_msg)
    except Exception as e:
        logging.error(f"❌ Error inesperado en enviar_notificación: {e}")


def main() -> None:
    """Punto de entrada principal del script."""

    conn = conectar_db(DB_FILE)
    ser = conectar_serial()

    buffer = []
    contador_total = conn.execute("SELECT COUNT(*) FROM lecturas").fetchone()[0] or 0
    logging.info(f"Se reanuda el script. Registros en BD: {contador_total}")

    ahora = time.time()
    proximo_flush_db = ahora + random.randint(MIN_ESCRITURA_DB, MAX_ESCRITURA_DB)

    logging.info("📡 Iniciando captura de datos...")

    try:
        while True:
            if not ser.is_open:
                logging.warning("El puerto serial no está abierto. Reconectando...")
                ser = conectar_serial()
                continue

            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
            except serial.SerialException:
                logging.error("Serial perdido. Cerrando y reconectando...")
                ser.close()
                ser = conectar_serial()
                continue

            if "------ Lecturas ------" in line and line:
                ahora_local = datetime.now(ZONA_HORARIA_LOCAL)
                tiempo_utc_str = ahora_local.astimezone(pytz.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                datos: Dict[str, Any] = {"Tiempo": tiempo_utc_str}

                ser.timeout = 1
                lost_serial = False
                sensor_lines: list[str] = []
                for _ in range(6):
                    try:
                        sensor_line = ser.readline().decode("utf-8", errors="ignore").strip()
                    except serial.SerialException:
                        logging.error("Serial perdido durante lectura. Cerrando y reconectando...")
                        ser.close()
                        ser = conectar_serial()
                        lost_serial = True
                        break
                    sensor_lines.append(sensor_line)
                ser.timeout = 2
                if lost_serial:
                    continue

                datos.update(parse_sensor_block(sensor_lines))
                if any(k in datos for k in COLUMNAS if k != "Tiempo"):
                    buffer.append(datos)

            ahora = time.time()

            if ahora >= proximo_flush_db and buffer:
                logging.info(f"Iniciando flush de {len(buffer)} registros a la BD.")
                t0 = time.time()
                escritos = flush_db(conn, buffer)
                t1 = time.time()
                if escritos:
                    contador_total += escritos
                    logging.info(
                        f"✔ Flusheo completado en {t1 - t0:.2f}s. Total en BD: {contador_total}"
                    )
                    enviar_notificacion(buffer[-1])
                    buffer.clear()
                    proximo_flush_db = ahora + random.randint(
                        MIN_ESCRITURA_DB, MAX_ESCRITURA_DB
                    )

            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("🚫 Detenido manualmente.")
    finally:
        if ser.is_open:
            ser.close()
        conn.close()
        session.close()
        logging.info("Script finalizado. Conexiones cerradas.")


if __name__ == "__main__":
    main()
