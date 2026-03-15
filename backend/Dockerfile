FROM python:3.11-slim

# FIX: instalar curl para que el healthcheck de docker-compose funcione.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# NOTA: en desarrollo se corre como root para evitar problemas de permisos
# con el volumen montado desde Windows (Docker Desktop).
# Para producción, descomentar las líneas siguientes:
#   RUN adduser --disabled-password --gecos "" appuser \
#       && chown -R appuser:appuser /app
#   USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]