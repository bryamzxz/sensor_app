# Sensor App

Este repositorio contiene un script en Python para capturar lecturas de sensores TMP117 y BME680 conectados a un Arduino, almacenarlas en SQLite (modo WAL), y enviar notificaciones periódicas a Telegram.

## Características

* Reconexión automática al puerto serial del Arduino.
* Lectura y parseo de bloques de 6 líneas con temperatura, humedad, presión y resistencia de gas.
* Escritura periódica en SQLite con modo WAL y checkpoint seguro.
* Mantenimiento de un historial de los últimos 7 días (elimina automáticamente registros anteriores).
* Notificaciones automáticas a Telegram tras cada escritura.
* Logging rotativo con timestamps en zona `America/Bogota`.
* Dockerfile incluido para despliegue en contenedor.

## Estructura del proyecto

```
├── Dockerfile
├── README.md       ← este archivo
├── requirements.txt
└── server.py       ← script principal
```

## Requisitos previos

* Python 3.8+
* SQLite 3 con soporte WAL
* Arduino R4 WiFi (u otro con TMP117 y BME680)
* Token y chat\_id de Telegram
* Docker (opcional)

## Instalación manual

1. Clona el repositorio:

   ```bash
   git clone https://github.com/tu_usuario/sensor_app.git
   cd sensor_app
   ```
2. Crea un entorno virtual e instala dependencias:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Configura tus credenciales en variables de entorno o en un archivo `.env`:

   ```bash
   export TELEGRAM_TOKEN="<tu_token>"
   export TELEGRAM_CHAT_ID="<tu_chat_id>"
   ```
4. Ejecuta el script:

   ```bash
   python server.py
   ```

## Uso con Docker

1. Construye la imagen:

   ```bash
   docker build -t sensor_app .
   ```
2. Ejecuta el contenedor:

   ```bash
   docker run -d \
     -v $(pwd)/data:/app/data \
     -v $(pwd)/logs:/app/logs \
     -e TELEGRAM_TOKEN="<tu_token>" \
     -e TELEGRAM_CHAT_ID="<tu_chat_id>" \
     --device=/dev/ttyACM0 \
     --name sensor_app sensor_app
   ```

## Configuración adicional

* **Intervalos**:

  * `MIN_ESCRITURA_DB` y `MAX_ESCRITURA_DB`: intervalo aleatorio (segundos) entre escrituras en DB.
  * Puede ajustarse al gusto dentro de `server.py`.
* **Retención**:

  * La línea `DELETE FROM lecturas WHERE Tiempo < datetime('now','-7 days')` mantiene sólo 7 días de datos. Modifícala si necesitas otro periodo.

## Contribuciones

¡Bienvenidas! Abre un issue o pull request para sugerir mejoras o reportar bugs.

## Licencia

Este proyecto usa la licencia MIT. Consulte el archivo `LICENSE` para más detalles.
