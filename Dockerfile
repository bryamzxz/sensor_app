FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

COPY --chown=appuser:appuser . /app

RUN mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app/data /app/logs && \
    chmod 700 /app/data /app/logs

USER appuser

VOLUME ["/app/data", "/app/logs"]

HEALTHCHECK CMD python -m py_compile /app/server.py || exit 1

CMD ["python", "server.py"]

