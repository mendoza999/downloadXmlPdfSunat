# Usamos la imagen oficial de Playwright que incluye Python y todas las dependencias del navegador (basada en Ubuntu Jammy)
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

# Configuramos variables de entorno para evitar prompts y usar buffers sin imprimir a pantalla
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Definir el directorio de trabajo
WORKDIR /app

# Instalar dependencias adicionales del sistema si hicieran falta (opcional, Playwright ya trae la mayoría)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libsqlite3-dev \
#     && rm -rf /var/lib/apt/lists/*

# Copiar primero el requirements.txt para aprovechar la cache de capas de Docker
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación, el archivo Excel y el service account (IMPORTANTE para que funcionen dentro del contenedor)
COPY . .

# Crear el directorio de descargas que espera la app
RUN mkdir -p /app/descargas_sunat /app/uploads

# Exponer el puerto
EXPOSE 8000

# Comando para iniciar FastAPI, leyendo la variable PORT que provee Cloud Run o Render (por defecto 8000)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
