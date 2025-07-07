#!/usr/bin/env python3
import os
import time
import random
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
import requests
import serial
import serial.tools.list_ports
from datetime import datetime
import pytz

# ------------------------------
# ⚙️ Configuración general
# ------------------------------
ZONA_HORARIA_LOCAL = pytz.timezone("America/Bogota")
DATA_DIR = "data"
LOG_DIR = "logs"
DB_FILE = os.path.join(DATA_DIR, "datos.db")
LOG_FILE = os.path.join(LOG_DIR, "eventos.log")

MIN_ESCRITURA_DB    = 300   # 5 minutos
MAX_ESCRITURA_DB    = 600   # 10 minutos

TELEGRAM_TOKEN   = "7895956023:AAHiOAZtA-cSkuRF6oikdMHJu2-YJtTPLs8"  # tu token de Telegram
TELEGRAM_CHAT_ID = "1410731981"  # tu chat_id

ARDUINO_VID = 0x2341
ARDUINO_PID = 0x1002

COLUMNAS = ["Tiempo", "TMP117_Temp", "BME680_Temp", "Humedad", "Presion", "Gas_Resistencia"]

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
    conn.execute("""
      CREATE TABLE IF NOT EXISTS lecturas (
        Tiempo TEXT PRIMARY KEY,
        TMP117_Temp REAL,
        BME680_Temp REAL,
        Humedad REAL,
        Presion REAL,
        Gas_Resistencia REAL
      )
    """)
    return conn

# --- [ELIMINADO] La función obtener_ultimo_registro ya no es necesaria ---

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
            dt_utc = datetime.strptime(datos['Tiempo'], "%Y-%m-%d %H:%M:%S")
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
            data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"},
            timeout=15
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

# ------------------------------
# 🚀 Inicio del sistema
# ------------------------------
conn = conectar_db(DB_FILE)
ser = conectar_serial()

buffer = []
contador_total = conn.execute("SELECT COUNT(*) FROM lecturas").fetchone()[0] or 0
logging.info(f"Se reanuda el script. Registros en BD: {contador_total}")

ahora = time.time()
proximo_flush_db = ahora + random.randint(MIN_ESCRITURA_DB, MAX_ESCRITURA_DB)
# --- [ELIMINADO] La variable proxima_notificacion ya no es necesaria ---

logging.info("📡 Iniciando captura de datos...")

# ------------------------------
# 🔁 Bucle principal
# ------------------------------
try:
    while True:
        if not ser.is_open:
            logging.warning("El puerto serial no está abierto. Reconectando...")
            ser = conectar_serial()
            continue

        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
        except serial.SerialException:
            logging.error("Serial perdido. Cerrando y reconectando...")
            ser.close()
            ser = conectar_serial()
            continue

        if "------ Lecturas ------" in line and line:
            ahora_local = datetime.now(ZONA_HORARIA_LOCAL)
            tiempo_utc_str = ahora_local.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
            datos = {"Tiempo": tiempo_utc_str}

            ser.timeout = 1
            for _ in range(6):
                l = ser.readline().decode('utf-8', errors='ignore').strip()
                try:
                    if ":" not in l: continue
                    key, val = l.split(":", 1)
                    val = val.strip().split(" ")[0]
                    if "TMP117 Temp" in key:     datos["TMP117_Temp"] = float(val)
                    elif "BME680 Temp" in key:   datos["BME680_Temp"] = float(val)
                    elif "Humedad" in key:       datos["Humedad"] = float(val)
                    elif "Presión" in key:       datos["Presion"] = float(val)
                    elif "Gas Resistencia" in key: datos["Gas_Resistencia"] = float(val)
                except (ValueError, IndexError) as e:
                    logging.warning(f"Error parseando línea del sensor '{l}': {e}")
            ser.timeout = 2

            if any(k in datos for k in COLUMNAS if k != "Tiempo"):
                buffer.append(datos)

        ahora = time.time()

        # [LÓGICA CONSERVADA] Flush y notificación aleatoria cada 5-10 minutos
        if ahora >= proximo_flush_db and buffer:
            logging.info(f"Iniciando flush de {len(buffer)} registros a la BD.")
            t0 = time.time()

            registros_para_insertar = [tuple(d.get(c) for c in COLUMNAS) for d in buffer]

            # Paso 1: Transacción atómica para escribir y borrar datos.
            with conn:
                conn.executemany("INSERT OR REPLACE INTO lecturas VALUES (?,?,?,?,?,?)", registros_para_insertar)
                conn.execute("DELETE FROM lecturas WHERE Tiempo < datetime('now', '-7 days')")

            # Paso 2: Ejecutar el checkpoint DESPUÉS de que la transacción anterior haya terminado.
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                logging.info("✔ Checkpoint WAL completado exitosamente.")
            except sqlite3.OperationalError as e:
                # Este error aún podría ocurrir si otro proceso accede a la DB, pero ya no por el script mismo.
                logging.error(f"❌ Error en WAL checkpoint: {e}")

            t1 = time.time()
            contador_total += len(buffer)
            logging.info(f"✔ Flusheo completado en {t1-t0:.2f}s. Total en BD: {contador_total}")
            
            # Notificar con el último dato del buffer que se acaba de guardar
            enviar_notificacion(buffer[-1])
            
            buffer.clear()
            proximo_flush_db = ahora + random.randint(MIN_ESCRITURA_DB, MAX_ESCRITURA_DB)

        # --- [ELIMINADO] El bloque de notificación periódica ya no existe ---

        time.sleep(1)

except KeyboardInterrupt:
    logging.info("🚫 Detenido manualmente.")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
    if 'conn' in locals():
        conn.close()
    logging.info("Script finalizado. Conexiones cerradas.")
    print("\nFinalizado.")
