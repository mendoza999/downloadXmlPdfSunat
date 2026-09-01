import os
from dotenv import load_dotenv

load_dotenv()

# Credenciales
SUNAT_RUC = os.getenv("SUNAT_RUC", "")
SUNAT_USUARIO = os.getenv("SUNAT_USUARIO", "")
SUNAT_CLAVE = os.getenv("SUNAT_CLAVE", "")

# Archivo Excel
EXCEL_FILE = os.getenv("EXCEL_FILE", "Compras Abril 2026.xlsx")

# Opciones de descarga
DESCARGAR_PDF = os.getenv("DESCARGAR_PDF", "true").lower() == "true"
DESCARGAR_XML = os.getenv("DESCARGAR_XML", "true").lower() == "true"

# Directorio de descargas
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./descargas_sunat")

# Parametros de concurrencia y reintentos
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "3"))
MAX_REINTENTOS_INMEDIATOS = int(os.getenv("MAX_REINTENTOS_INMEDIATOS", "2"))
DELAY_REINTENTO = float(os.getenv("DELAY_REINTENTO", "2.0"))
PAUSA_MIN_ENTRE_CPE = float(os.getenv("PAUSA_MIN_ENTRE_CPE", "0.8"))
PAUSA_MAX_ENTRE_CPE = float(os.getenv("PAUSA_MAX_ENTRE_CPE", "1.5"))
PAUSA_MIN_ENTRE_ARCHIVOS = float(os.getenv("PAUSA_MIN_ENTRE_ARCHIVOS", "0.5"))
PAUSA_MAX_ENTRE_ARCHIVOS = float(os.getenv("PAUSA_MAX_ENTRE_ARCHIVOS", "1.2"))
ESPERA_BASE_RONDA_SEG = int(os.getenv("ESPERA_BASE_RONDA_SEG", "60"))
FACTOR_BACKOFF = float(os.getenv("FACTOR_BACKOFF", "1.5"))
ESPERA_MAX_RONDA_SEG = int(os.getenv("ESPERA_MAX_RONDA_SEG", "300"))
MAX_RONDAS_ARCHIVOS = int(os.getenv("MAX_RONDAS_ARCHIVOS", "10"))

GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", None)

EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "465"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO", "")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")