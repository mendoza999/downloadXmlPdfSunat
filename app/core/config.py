import os

from dotenv import load_dotenv

load_dotenv()

# Raiz del proyecto (carpeta que contiene app/, uploads/, descargas_sunat/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ruta_absoluta(valor: str) -> str:
    """Convierte una ruta relativa del .env en absoluta respecto al proyecto."""
    valor = os.path.expanduser(valor)
    if os.path.isabs(valor):
        return valor
    return os.path.abspath(os.path.join(BASE_DIR, valor))


def _booleano(nombre: str, defecto: bool) -> bool:
    return os.getenv(nombre, str(defecto)).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


# Credenciales
SUNAT_RUC = os.getenv("SUNAT_RUC", "").strip()
SUNAT_USUARIO = os.getenv("SUNAT_USUARIO", "").strip()
SUNAT_CLAVE = os.getenv("SUNAT_CLAVE", "")

# Archivo Excel
EXCEL_FILE = _ruta_absoluta(os.getenv("EXCEL_FILE", "comprobantes.xlsx"))

# Opciones de descarga
DESCARGAR_PDF = _booleano("DESCARGAR_PDF", True)
DESCARGAR_XML = _booleano("DESCARGAR_XML", True)

# Directorios
OUTPUT_DIR = _ruta_absoluta(os.getenv("OUTPUT_DIR", "./descargas_sunat"))
UPLOAD_DIR = _ruta_absoluta(os.getenv("UPLOAD_DIR", "./uploads"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))

# Parametros de concurrencia y reintentos
MAX_WORKERS = max(1, int(os.getenv("MAX_WORKERS", "3")))
MAX_REINTENTOS_INMEDIATOS = max(0, int(os.getenv("MAX_REINTENTOS_INMEDIATOS", "2")))
DELAY_REINTENTO = float(os.getenv("DELAY_REINTENTO", "2.0"))
PAUSA_MIN_ENTRE_CPE = float(os.getenv("PAUSA_MIN_ENTRE_CPE", "0.8"))
PAUSA_MAX_ENTRE_CPE = float(os.getenv("PAUSA_MAX_ENTRE_CPE", "1.5"))
PAUSA_MIN_ENTRE_ARCHIVOS = float(os.getenv("PAUSA_MIN_ENTRE_ARCHIVOS", "0.5"))
PAUSA_MAX_ENTRE_ARCHIVOS = float(os.getenv("PAUSA_MAX_ENTRE_ARCHIVOS", "1.2"))
ESPERA_BASE_RONDA_SEG = int(os.getenv("ESPERA_BASE_RONDA_SEG", "60"))
FACTOR_BACKOFF = float(os.getenv("FACTOR_BACKOFF", "1.5"))
ESPERA_MAX_RONDA_SEG = int(os.getenv("ESPERA_MAX_RONDA_SEG", "300"))
MAX_RONDAS_ARCHIVOS = max(1, int(os.getenv("MAX_RONDAS_ARCHIVOS", "10")))

# Navegador (login SUNAT)
SUNAT_HEADLESS = _booleano("SUNAT_HEADLESS", True)
SUNAT_SLOW_MO = int(os.getenv("SUNAT_SLOW_MO", "0"))
SUNAT_TIMEOUT_MS = int(os.getenv("SUNAT_TIMEOUT_MS", "45000"))
SUNAT_LOGIN_INTENTOS = max(1, int(os.getenv("SUNAT_LOGIN_INTENTOS", "2")))
SUNAT_LOGIN_ESPERA_SEG = int(os.getenv("SUNAT_LOGIN_ESPERA_SEG", "10"))

GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID") or None

EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "465"))
EMAIL_USER = os.getenv("EMAIL_USER", "").strip()
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO", "").strip()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
)

# Base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db").strip()

# Normaliza rutas SQLite relativas para que no dependan del directorio actual
if DATABASE_URL.startswith("sqlite:///") and not DATABASE_URL.startswith("sqlite:////"):
    _ruta_sqlite = DATABASE_URL[len("sqlite:///"):]
    if _ruta_sqlite not in {":memory:", ""} and not os.path.isabs(_ruta_sqlite):
        DATABASE_URL = "sqlite:///" + _ruta_absoluta(_ruta_sqlite).replace("\\", "/")

# API
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
API_TITLE = os.getenv("API_TITLE", "SUNAT Descargas API")
API_VERSION = os.getenv("API_VERSION", "1.1")
UVICORN_RELOAD = _booleano("UVICORN_RELOAD", False)
