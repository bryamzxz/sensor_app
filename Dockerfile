FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

COPY . /app

RUN mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app/data /app/logs

USER appuser

VOLUME ["/app/data", "/app/logs"]

CMD ["python", "server.py"]

