FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Asegura que el directorio de datos exista dentro del contenedor
RUN mkdir -p /app/data /app/logs
VOLUME [ "/app/data", "/app/logs" ]


CMD ["python", "server.py"]

