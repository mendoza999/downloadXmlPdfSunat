# Imagen oficial de Playwright con Python y las librerías del navegador
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

# Evitar prompts, buffering y archivos .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Dependencias de Python (primero para aprovechar la cache de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Asegura que el navegador descargado coincida con la versión de Playwright instalada
RUN playwright install --with-deps chromium

# Copiar el código de la aplicación
COPY . .

# Carpetas que usa la aplicación en tiempo de ejecución
RUN mkdir -p /app/descargas_sunat /app/uploads

EXPOSE 8000

# Cloud Run / Render proveen la variable PORT.
# ROOT_PATH permite publicar la app en un subdirectorio (ej: /downloadpdf).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --root-path \"${ROOT_PATH:-}\" --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-*}\""]
