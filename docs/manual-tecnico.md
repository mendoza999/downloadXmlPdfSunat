# Manual Tecnico - SUNAT Bot V2

## 1. Arquitectura General

El sistema esta construido como un servicio web usando **FastAPI** y ejecuta tareas de descarga en segundo plano. Utiliza **Playwright** para automatizar el login en el portal de SUNAT y la **API REST de SUNAT** para descargar los comprobantes.

```
┌─────────────────────────────────────────────────────────────┐
│                     SUNAT Bot V2                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   FastAPI    │    │   Playwright  │    │  API SUNAT   │  │
│  │   (Server)   │───>│  (Login Auto) │───>│  (PDF/XML)   │  │
│  └──────┬──────┘    └──────────────┘    └──────────────┘  │
│         │                                                  │
│         ▼                                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  PostgreSQL  │    │  Google Drive │    │  SMTP Email  │  │
│  │  (Jobs/Users)│    │  (Opcional)   │    │  (Notif.)    │  │
│  └─────────────┘    └──────────────┘    └──────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Flujo de Datos

```
[Usuario sube Excel]
        │
        ▼
  FastAPI (/descargar) ──> Job en BD (pending)
        │
        ▼  (BackgroundTasks)
  DocumentPipeline.run()
        │
        ├── leer_excel() ──> Lista de Comprobantes
        │
        ├── Para cada comprobante (paralelo):
        │       │
        │       ├── sunat_auth.py ──> Playwright login ──> Token Bearer
        │       │
        │       ├── sunat_api.py ──> GET PDF/XML desde API SUNAT
        │       │
        │       ├── storage.py ──> Guardar local
        │       │
        │       └── drive_storage*.py ──> Subir a Google Drive
        │
        └── notifications.py ──> Correo SMTP de resumen
```

---

## 2. Estructura del Proyecto

```
SUNAT-BOT-V2/
├── .dockerignore              # Archivos excluidos del contenedor Docker
├── .env                       # Variables de entorno (CREDENCIALES - NO SUBIR A GIT)
├── Dockerfile                 # Imagen Docker basada en Playwright
├── requirements.txt           # Dependencias Python
├── service_account.json       # Credenciales Service Account Google (NO SUBIR A GIT)
├── Compras Abril 2026.xlsx    # Archivo Excel de ejemplo
├── sunat_bot.zip              # Archivo comprimido (backup/distribucion)
│
├── docs/                      # Documentacion
│   ├── manual-usuario.md      # Manual de usuario
│   └── manual-tecnico.md      # Manual tecnico
│
└── app/                       # Codigo fuente principal
    ├── main.py                # Punto de entrada FastAPI
    │
    ├── core/                  # Configuracion y utilidades base
    │   ├── __init__.py
    │   ├── config.py          # Carga de variables de entorno
    │   ├── database.py        # Configuracion SQLAlchemy + PostgreSQL
    │   └── logging.py         # Configuracion de logging
    │
    ├── api/                   # Endpoints HTTP (FastAPI Router)
    │   ├── __init__.py
    │   └── routes.py          # Rutas: /descargar, /estado, /auth/google
    │
    ├── models/                # Modelos de datos
    │   ├── __init__.py
    │   ├── comprobante.py     # Modelo Comprobante + lector de Excel
    │   └── db_models.py       # Modelos SQLAlchemy: User, Job
    │
    └── services/              # Logica de negocio
        ├── __init__.py
        ├── sunat_auth.py      # Login automatizado con Playwright
        ├── sunat_api.py       # Cliente API REST para descarga
        ├── pipeline.py        # Orquestador: lee Excel, descarga, reintentos
        ├── storage.py         # Almacenamiento local
        ├── drive_storage.py   # Google Drive (Service Account)
        ├── drive_storage_oauth.py  # Google Drive (OAuth)
        └── notifications.py   # Envio de correos SMTP
```

---

## 3. Tecnologias

| Tecnologia | Version | Uso |
|------------|---------|-----|
| **Python** | 3.x | Lenguaje principal |
| **FastAPI** | - | Framework web (API REST) |
| **Uvicorn** | - | Servidor ASGI |
| **Playwright** | 1.60.0 | Navegador headless para login en SUNAT |
| **SQLAlchemy** | - | ORM para base de datos |
| **PostgreSQL** | - | Base de datos relacional |
| **Pandas** | - | Lectura de archivos Excel |
| **openpyxl** | - | Soporte para archivos .xlsx |
| **Requests** | - | Cliente HTTP para API de SUNAT |
| **Google API Client** | - | Integracion con Google Drive |
| **python-dotenv** | - | Carga de variables de entorno |

### Dependencias (requirements.txt)

```
playwright
pandas
requests
openpyxl
python-dotenv
google-api-python-client
google-auth-oauthlib
fastapi
uvicorn
sqlalchemy
psycopg2-binary
python-multipart
```

---

## 4. Descripcion de Modulos

### 4.1 `app/main.py` - Punto de Entrada

```python
app = FastAPI(title="SUNAT Descargas API", version="1.0")
```

**Funcion:** Crea la aplicacion FastAPI, incluye el router de rutas y crea las tablas de la base de datos al iniciar.

**Responsabilidades:**
- Inicializar la app FastAPI
- Crear tablas de BD con `Base.metadata.create_all()`
- Configurar logging
- Ejecutar el servidor con Uvicorn

**Ejecucion:**
```bash
python -m app.main
# o
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

### 4.2 `app/core/config.py` - Configuracion

**Funcion:** Carga todas las variables de entorno desde el archivo `.env` usando `python-dotenv`.

**Variables configuradas:**
- Credenciales SUNAT (RUC, usuario, clave)
- Opciones de descarga (PDF, XML, directorio)
- Parametros de concurrencia y reintentos
- Credenciales Google Drive
- Configuracion SMTP
- URL de base de datos

**Ejemplo de uso:**
```python
from app.core import config

ruc = config.SUNAT_RUC  # "12345678901"
max_workers = config.MAX_WORKERS  # 3
```

---

### 4.3 `app/core/database.py` - Base de Datos

**Funcion:** Configura la conexion a PostgreSQL usando SQLAlchemy.

**Componentes:**
- `engine`: Motor de conexion a la BD
- `SessionLocal`: Fabrica de sesiones
- `Base`: Base declarativa para modelos ORM
- `get_db()`: Dependencia de FastAPI para inyectar sesiones

**Configuracion:**
```python
DATABASE_URL = "postgresql://user:password@host/database"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
```

**Nota:** `pool_pre_ping=True` verifica la conexion antes de cada uso, evitando errores por conexiones caducadas.

---

### 4.4 `app/core/logging.py` - Sistema de Logs

**Funcion:** Configura el formato de logs para toda la aplicacion.

**Formato:**
```
2026-09-01 10:00:00 [INFO] (archivo.py:linea) - Mensaje
```

**Nivel:** INFO (configurable)

---

### 4.5 `app/api/routes.py` - Endpoints HTTP

**Funcion:** Define las rutas de la API REST.

#### Endpoints

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| `POST` | `/descargar` | Sube un Excel e inicia la descarga |
| `POST` | `/descargar/comprobante` | Descarga puntual (sincrona) de PDF/XML de un comprobante |
| `GET` | `/comprobante/archivo` | Entrega un PDF, XML o ZIP ya descargado |
| `GET` | `/estado/{job_id}` | Consulta el estado de un trabajo |
| `GET` | `/auth/google` | Inicia el flujo de autenticacion OAuth con Google |
| `GET` | `/auth/google/callback` | Callback de autenticacion OAuth |

#### `POST /descargar`

**Request:**
```http
POST /descargar
Content-Type: multipart/form-data

file: Compras Abril 2026.xlsx
```

**Response:**
```json
{
  "job_id": "uuid-del-trabajo",
  "status": "pending"
}
```

**Proceso:**
1. Valida que el archivo sea `.xlsx` o `.xls`
2. Guarda el archivo en `uploads/`
3. Crea un registro de `Job` en la BD con estado `pending`
4. Ejecuta el pipeline en segundo plano con `BackgroundTasks`

#### `POST /descargar/comprobante`

Descarga **sincrona** de un solo comprobante. No usa `BackgroundTasks` ni crea
un `Job`: recibe los datos, obtiene el token SUNAT y descarga los archivos
habilitados (`DESCARGAR_PDF` / `DESCARGAR_XML`).

**Request:**
```http
POST /descargar/comprobante
Content-Type: application/json

{
  "tipo_doc": "01",
  "serie": "F001",
  "numero": "123",
  "ruc_emisor": "20123456789"
}
```

**Response:**
```json
{
  "comprobante": {
    "tipo_doc": "01",
    "serie": "F001",
    "numero": "123",
    "ruc_emisor": "20123456789"
  },
  "completo": true,
  "archivos": [
    {
      "tipo": "pdf",
      "nombre": "20123456789_F001_123.pdf",
      "ruta": "descargas_sunat/pdfs/20123456789_F001_123.pdf",
      "descarga_url": "/comprobante/archivo?...&formato=pdf"
    }
  ],
  "faltantes": [],
  "descarga_zip_url": "/comprobante/archivo?...&formato=zip"
}
```

**Proceso:**
1. Normaliza y valida `tipo_doc`, `serie`, `numero` y `ruc_emisor`
   (reutiliza `crear_comprobante` de `app/models/comprobante.py`).
   Los parametros se leen desde JSON, formulario o query string, y los campos
   numericos aceptan texto o numero.
2. Si los archivos ya existen en `OUTPUT_DIR`, los reutiliza sin consultar SUNAT.
3. En caso contrario obtiene el token y ejecuta `DocumentPipeline.descargar_lista`
   (una sola pasada, con los reintentos inmediatos configurados).
4. Guarda en disco y sube a Google Drive si el usuario tiene OAuth vinculado.

**Errores:** `400` datos invalidos, `404` no se obtuvo ningun archivo,
`502` error de descarga/conexion, `503` credenciales SUNAT no configuradas.

#### `GET /comprobante/archivo`

Entrega un archivo previamente descargado. Parametros: `tipo_doc`, `serie`,
`numero`, `ruc_emisor` y `formato` (`pdf`, `xml` o `zip`; por defecto `pdf`).
Responde `404` si el archivo aun no fue descargado.

#### `GET /estado/{job_id}`

**Response:**
```json
{
  "job_id": "uuid",
  "status": "completed",
  "message": "Descarga completada exitosamente.",
  "excel_filename": "Compras Abril 2026.xlsx",
  "created_at": "2026-09-01T10:00:00"
}
```

#### `GET /auth/google`

Redirige al usuario a la pagina de consentimiento de Google para autorizar el acceso a Google Drive.

#### `GET /auth/google/callback`

Recibe el codigo de autorizacion de Google, lo intercambia por un refresh token y lo almacena en la BD del usuario.

---

### 4.6 `app/models/comprobante.py` - Modelo de Comprobante

**Funcion:** Define la estructura de datos para un comprobante de pago y la funcion para leerlos desde Excel.

#### Dataclass `Comprobante`

```python
@dataclass
class Comprobante:
    ruc: str        # RUC del emisor
    tipo: str       # Tipo de documento (01=Factura, 03=Boleta)
    serie: str      # Serie del comprobante
    numero: str     # Numero del comprobante
    fila: int       # Numero de fila en el Excel
```

**Propiedad:** `nombre_base` devuelve `{ruc}_{serie}_{numero}`

#### Funcion `leer_excel()`

```python
def leer_excel(excel_path: str) -> List[Comprobante]
```

- Lee el Excel usando Pandas
- Detecta la fila de encabezados y ubica las columnas por nombre (`Tipo`, `Serie`, `Numero`, `RUC Emisor` y sus variantes); si no las encuentra, usa las columnas G, H, I y J
- Convierte el tipo de documento (1 -> "01", 3 -> "03", etc.)
- Omite filas vacias o invalidas (por ejemplo, RUC que no tenga 11 digitos) y reporta un resumen en el log
- Devuelve una lista de objetos `Comprobante` (sin duplicados)

---

### 4.7 `app/models/db_models.py` - Modelos de Base de Datos

**Funcion:** Define los modelos ORM que se mapean a tablas en PostgreSQL.

#### Modelo `User`

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `id` | String (PK) | Identificador unico del usuario |
| `email` | String (unique) | Correo electronico |
| `google_refresh_token` | String (nullable) | Token de Google Drive |
| `sunat_ruc` | String (nullable) | RUC de SUNAT |
| `sunat_usuario` | String (nullable) | Usuario de SUNAT |
| `sunat_clave` | String (nullable) | Clave de SUNAT |
| `created_at` | DateTime | Fecha de creacion |
| `updated_at` | DateTime | Fecha de actualizacion |

#### Modelo `Job`

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `id` | String (PK) | UUID del trabajo |
| `user_id` | String (FK) | Referencia al usuario |
| `status` | String | Estado: pending/processing/completed/failed |
| `excel_filename` | String (nullable) | Nombre del archivo Excel |
| `excel_path` | String (nullable) | Ruta del archivo Excel |
| `message` | String (nullable) | Mensaje de estado |
| `created_at` | DateTime | Fecha de creacion |
| `updated_at` | DateTime | Fecha de actualizacion |
| `details` | JSON (nullable) | Detalles adicionales |

**Relaciones:**
- `User` tiene muchos `Job` (1:N)
- `Job` pertenece a un `User` (N:1)

---

### 4.8 `app/services/sunat_auth.py` - Login Automatizado

**Funcion:** Usa Playwright para hacer login en el portal SOL de SUNAT y capturar el token de autorizacion.

#### Funcion `obtener_token_automatico()`

```python
def obtener_token_automatico(ruc: str, usuario: str, clave: str) -> str
```

**Proceso detallado:**

1. **Iniciar navegador:** Lanza Chromium en modo headless con `--no-sandbox`
2. **Configurar interceptacion:** Registra un listener para capturar el header `Authorization: Bearer` de las requests HTTP
3. **Navegar a SUNAT:** Accede a `https://www.sunat.gob.pe/sol.html`
4. **Hacer click en "Consulta de documentos":** Abre el formulario de login
5. **Completar formulario:** Llena RUC, usuario y clave
6. **Cerrar modales:** Maneja modales informativos que aparecen despues del login
7. **Obtener token:**
   - Primero intenta interceptarlo de las requests HTTP
   - Si no, navega a la seccion de facturas para forzar una request con token
   - Como ultimo recurso, intenta leer de `sessionStorage` o `localStorage`
8. **Cerrar navegador:** Libera recursos

**Errores posibles:**
- Credenciales incorrectas
- Portal SUNAT caido
- Token no encontrado (timeout)

**Tiempo estimado:** 15-30 segundos por login

---

### 4.9 `app/services/sunat_api.py` - Cliente API SUNAT

**Funcion:** Cliente HTTP que consume la API REST de SUNAT para descargar PDFs y XMLs.

#### Clase `SunatAPIClient`

```python
class SunatAPIClient:
    BASE_URL = "https://api-cpe.sunat.gob.pe/v1/contribuyente/consultacpe/comprobantes"
```

**Metodos principales:**

| Metodo | Parametros | Retorna | Descripcion |
|--------|------------|---------|-------------|
| `fetch_pdf()` | ruc, tipo, serie, numero | bytes | Descarga el PDF del comprobante |
| `fetch_xml()` | ruc, tipo, serie, numero | bytes | Descarga el XML del comprobante |
| `actualizar_token()` | nuevo_token | None | Actualiza el token de autorizacion |

**Proceso de descarga:**

1. Construye la URL: `{BASE_URL}/{ruc}-{tipo}-{serie}-{numero}-2/{sufijo}`
   - Sufijo `01` para PDF
   - Sufijo `02` para XML
2. Realiza la request GET con headers de autorizacion
3. Si recibe 401, lanza `PermissionError` (token expirado)
4. Decodifica la respuesta JSON y extrae `valArchivo` (base64)
5. Decodifica el base64 a bytes
6. Descomprime el ZIP y extrae el archivo (PDF o XML)
7. Retorna el contenido del archivo

**Headers configurados:**
```
Authorization: Bearer {token}
User-Agent: Mozilla/5.0 ...
Accept: application/json
Origin: https://e-factura.sunat.gob.pe
Referer: https://e-factura.sunat.gob.pe/
```

---

### 4.10 `app/services/pipeline.py` - Orquestador Principal

**Funcion:** Coordina todo el proceso de descarga: lee el Excel, procesa comprobantes en paralelo, gestiona reintentos y envia notificaciones.

#### Clase `DocumentPipeline`

```python
class DocumentPipeline:
    def __init__(self, excel_path, token, storage, drive=None, 
                 descargar_pdf=True, descargar_xml=True):
```

**Metodo `run()`:**

```
1. Leer Excel ──> Lista de Comprobantes
2. Filtrar los que ya estan completos
3. Si no hay pendientes, terminar
4. Mientras haya pendientes y no se alcancen las rondas maximas:
   a. Esperar si es necesario (backoff exponencial)
   b. Ejecutar en paralelo con ThreadPoolExecutor
   c. Para cada comprobante:
      - Verificar si falta PDF o XML
      - Descargar con reintentos
      - Guardar localmente
      - Subir a Drive (si esta configurado)
   d. Si el token expira, regenerarlo automaticamente
   e. Actualizar lista de pendientes
5. Generar resumen y enviar correo
```

**Sistema de reintentos:**

1. **Reintentos inmediatos:** `MAX_REINTENTOS_INMEDIATOS` (default: 2) reintentos con `DELAY_REINTENTO` (default: 2s) entre ellos
2. **Rondas de reintento:** Hasta `MAX_RONDAS_ARCHIVOS` (default: 10) rondas
3. **Backoff exponencial:** Espera base de `ESPERA_BASE_RONDA_SEG` (default: 60s) multiplicada por `FACTOR_BACKOFF` (default: 1.5) elevado al numero de ronda
4. **Espera maxima:** `ESPERA_MAX_RONDA_SEG` (default: 300s / 5 min)

**Concurrencia:**

- `ThreadPoolExecutor(max_workers=MAX_WORKERS)` ejecuta descargas en paralelo
- Pausa aleatoria entre submissions: `PAUSA_MIN_ENTRE_CPE` a `PAUSA_MAX_ENTRE_CPE`

---

### 4.11 `app/services/storage.py` - Almacenamiento Local

**Funcion:** Guarda los archivos PDF y XML descargados en el disco local.

#### Clase `LocalStorage`

```python
class LocalStorage:
    def __init__(self, output_dir: str):
        self.dir_pdf = os.path.join(output_dir, "pdfs")
        self.dir_xml = os.path.join(output_dir, "xmls")
```

**Metodos:**

| Metodo | Descripcion |
|--------|-------------|
| `path_pdf(cpe)` | Retorna la ruta completa del PDF |
| `path_xml(cpe)` | Retorna la ruta completa del XML |
| `existe_pdf(cpe)` | Verifica si el PDF ya existe |
| `existe_xml(cpe)` | Verifica si el XML ya existe |
| `guardar(cpe, tipo, data)` | Guarda el archivo en disco |

**Estructura de carpetas:**
```
descargas_sunat/
├── pdfs/
│   └── {ruc}_{serie}_{numero}.pdf
└── xmls/
    └── {ruc}_{serie}_{numero}.xml
```

---

### 4.12 `app/services/drive_storage.py` - Google Drive (Service Account)

**Funcion:** Sube archivos a Google Drive usando una cuenta de servicio (Service Account).

#### Clase `DriveStorage`

```python
class DriveStorage:
    def __init__(self, credentials_path: str, parent_folder_id: str = None)
```

**Metodos:**

| Metodo | Descripcion |
|--------|-------------|
| `_autenticar()` | Se autentica con el archivo JSON de Service Account |
| `_crear_o_obtener_carpeta(nombre)` | Crea o busca una carpeta en Drive |
| `subir_archivo(ruta, nombre, folder_id)` | Sube un archivo a Drive |
| `subir_comprobante(ruta, nombre)` | Sube con reintentos automaticos |

**Comportamiento:**
- Crea carpetas con formato `FACTURAS DEL YYYY-MM-DD`
- Reintentos automaticos: 3 intentos con backoff exponencial
- Archivos subidos a la carpeta del dia actual

---

### 4.13 `app/services/drive_storage_oauth.py` - Google Drive (OAuth)

**Funcion:** Sube archivos a Google Drive usando autenticacion OAuth (refresh token).

#### Clase `DriveStorageOAuth`

```python
class DriveStorageOAuth:
    def __init__(self, credentials: Credentials)
```

**Diferencia con `DriveStorage`:**
- Usa credenciales OAuth en lugar de Service Account
- Las credenciales se obtienen del flujo de autenticacion web
- El refresh token se almacena en la BD del usuario

---

### 4.14 `app/services/notifications.py` - Notificaciones

**Funcion:** Envia correos electronicos con el resumen de la descarga.

#### Funcion `enviar_correo()`

```python
def enviar_correo(asunto: str, cuerpo: str)
```

**Configuracion SMTP:**
- Servidor: `smtp.gmail.com`
- Puerto: `465` (SMTP_SSL)
- Autenticacion: Login con correo y contrasena de aplicacion

**Tipos de correo:**

| Asunto | Contenido |
|--------|-----------|
| `SUNAT - Descarga completada` | Resumen exitoso con cantidad de archivos |
| `SUNAT - Descarga fallida` | Error occurredido durante la descarga |
| `Descarga SUNAT - Incompleta` | Lista de comprobantes pendientes |

---

## 5. Base de Datos

### 5.1 Esquema

```sql
CREATE TABLE users (
    id VARCHAR PRIMARY KEY,
    email VARCHAR UNIQUE,
    google_refresh_token VARCHAR,
    sunat_ruc VARCHAR,
    sunat_usuario VARCHAR,
    sunat_clave VARCHAR,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE TABLE jobs (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR REFERENCES users(id),
    status VARCHAR DEFAULT 'pending',
    excel_filename VARCHAR,
    excel_path VARCHAR,
    message VARCHAR,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    details JSON
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
```

### 5.2 Relaciones

```
┌─────────────┐         ┌─────────────┐
│    User      │    1:N  │     Job      │
├─────────────┤────────>├─────────────┤
│ id (PK)     │         │ id (PK)     │
│ email       │         │ user_id (FK) │
│ sunat_ruc   │         │ status      │
│ sunat_user  │         │ excel_file  │
│ sunat_clave │         │ message     │
│ g_token     │         │ details     │
└─────────────┘         └─────────────┘
```

### 5.3 Estados de Job

| Estado | Descripcion | Transiciones |
|--------|-------------|--------------|
| `pending` | En cola, esperando procesarse | -> processing |
| `processing` | Ejecutandose | -> completed, -> failed |
| `completed` | Finalizado exitosamente | Terminal |
| `failed` | Fallo con error | Terminal |

---

## 6. Despliegue

### 6.1 Docker

**Dockerfile:**
```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/descargas_sunat /app/uploads

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

**Construir:**
```bash
docker build -t sunat-bot-v2 .
```

**Ejecutar:**
```bash
docker run -d \
  --name sunat-bot \
  -p 8000:8000 \
  -e SUNAT_RUC=tu_ruc \
  -e SUNAT_USUARIO=tu_usuario \
  -e SUNAT_CLAVE=tu_clave \
  sunat-bot-v2
```

**Con Docker Compose (recomendado):**
```yaml
version: '3.8'
services:
  sunat-bot:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./descargas_sunat:/app/descargas_sunat
      - ./uploads:/app/uploads
    restart: unless-stopped
```

### 6.2 Despliegue en Cloud Run / Render

El Dockerfile esta disenado para ser compatible con Cloud Run y Render:

- Usa la variable `PORT` del entorno (proveida por la plataforma)
- Puerto por defecto: 8000
- Compatible con imagenes basadas en Playwright

### 6.3 Variables de Entorno en Produccion

**NUNCA** subas el archivo `.env` a un repositorio publico. En produccion, configura las variables directamente en la plataforma de despliegue.

---

## 7. Configuracion de Concurrencia

### 7.1 Parametros Anti-Baneo

El bot esta disenado para evitar ser bloqueado por SUNAT:

| Parametro | Valor | Funcion |
|-----------|-------|---------|
| `MAX_WORKERS` | 3 | Hilos simultaneos (no muy altos) |
| `PAUSA_MIN_ENTRE_CPE` | 0.8s | Pausa minima entre comprobantes |
| `PAUSA_MAX_ENTRE_CPE` | 1.5s | Pausa maxima entre comprobantes |
| `PAUSA_MIN_ENTRE_ARCHIVOS` | 0.5s | Pausa minima entre archivos |
| `PAUSA_MAX_ENTRE_ARCHIVOS` | 1.2s | Pausa maxima entre archivos |

### 7.2 Backoff Exponencial

Cuando hay errores, el bot aumenta el tiempo de espera entre rondas:

```
Ronda 1: 0s de espera
Ronda 2: 60s * (1.5^0) = 60s
Ronda 3: 60s * (1.5^1) = 90s
Ronda 4: 60s * (1.5^2) = 135s
Ronda 5: 60s * (1.5^3) = 202s
...
Ronda max: 300s (tope)
```

### 7.3 Recomendaciones

- **MAX_WORKERS <= 5:** Valores mas altos pueden causar bloqueos
- **Pausas:** No reduzcas por debajo de 0.5s
- **MAX_RONDAS_ARCHIVOS:** 10 rondas suelen ser suficientes para 99% de los casos
- **ESPERA_BASE_RONDA_SEG:** 60s es un buen balance entre velocidad y seguridad

---

## 8. Seguridad

### 8.1 Archivos Sensibles

**NUNCA** subir a repositorios publicos:

| Archivo | Contenido |
|---------|-----------|
| `.env` | Credenciales SUNAT, Gmail, Google, BD |
| `service_account.json` | Credenciales de Google Cloud |
| `*.xlsx` | Datos de comprobantes reales |

### 8.2 `.gitignore` Recomendado

```gitignore
# Variables de entorno
.env

# Credenciales Google
service_account.json

# Archivos de datos
*.xlsx
*.xls

# Descargas
descargas_sunat/
uploads/

# Python
__pycache__/
*.py[cod]
venv/
.venv/

# Base de datos
*.db
*.sqlite3

# IDE
.vscode/
.idea/

# Sistema
.DS_Store
Thumbs.db
```

### 8.3 Credenciales en Produccion

- Usa variables de entorno de la plataforma (no archivos `.env`)
- Para Google Drive, usa Service Account en lugar de OAuth si es posible
- Habilita la autenticacion JWT para la API en produccion
- Usa HTTPS siempre

---

## 9. Solucion de Problemas Tecnicos

### 9.1 Errores Comunes

| Error | Causa | Solucion |
|-------|-------|----------|
| `PermissionError: Token expirado` | Token de SUNAT caduco | El pipeline lo regenera automaticamente |
| `No se pudo obtener el token` | Login fallido en SUNAT | Verificar credenciales y disponibilidad del portal |
| `Connection refused` | PostgreSQL no disponible | Verificar DATABASE_URL y que el servidor este corriendo |
| `SMTPAuthenticationError` | Credenciales Gmail incorrectas | Verificar EMAIL_USER y EMAIL_PASSWORD |
| `TimeoutError` | Playwright tardo mucho | Aumentar timeout o verificar conexion |

### 9.2 Logs

Los logs se guardan en la salida estandar con formato:
```
2026-09-01 10:00:00 [LEVEL] (archivo:linea) - Mensaje
```

Niveles de log:
- `INFO`: Proceso normal
- `WARNING`: Advertencias (token por expirar, reintentos)
- `ERROR`: Errores que no detienen el proceso
- `CRITICAL`: Errores fatales

### 9.3 Monitoreo

Para monitorear el sistema en produccion:

1. **Logs:** Revisa los logs de la plataforma (Cloud Run, Render, etc.)
2. **Base de datos:** Consulta la tabla `jobs` para ver trabajos activos
3. **API:** Usa `GET /estado/{job_id}` para verificar trabajos especificos
4. **Correo:** Recibe notificaciones automaticas al finalizar trabajos

---

## 10. Desarrollo

### 10.1 Ejecutar en Desarrollo

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Instalar dependencias
pip install -r requirements.txt

# Instalar navegadores de Playwright
playwright install chromium

# Configurar .env
cp .env.example .env
# Editar .env con tus credenciales

# Ejecutar
python -m app.main
```

### 10.2 Estructura de un Nuevo Servicio

Si necesitas agregar un nuevo servicio:

1. Crea el archivo en `app/services/tu_servicio.py`
2. Define una clase con el logica de negocio
3. Importalo en `app/api/routes.py` o `app/services/pipeline.py`
4. Agrega las variables de entorno necesarias en `app/core/config.py`

### 10.3 Pruebas

El proyecto actualmente no tiene tests. Para agregar tests:

```bash
# Instalar pytest
pip install pytest

# Ejecutar tests
pytest tests/
```

Estructura recomendada:
```
tests/
├── __init__.py
├── test_comprobante.py
├── test_sunat_api.py
├── test_pipeline.py
└── test_storage.py
```
