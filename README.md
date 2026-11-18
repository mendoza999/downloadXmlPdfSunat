# SUNAT Bot V2

Aplicación para descargar XML y PDF desde el portal de SUNAT Perú.

Bot automatizado para la descarga de comprobantes de pago (facturas y boletas) desde el portal de la SUNAT (Superintendencia Nacional de Aduanas y de Administracion Tributaria del Peru).

## Caracteristicas

- Descarga automatica de PDFs y XMLs desde la API de SUNAT
- Login automatizado mediante Playwright (navegador headless)
- Interfaz REST API para subir archivos Excel y consultar estados
- Integracion con Google Drive (Service Account y OAuth)
- Notificaciones por correo electronico
- Sistema de reintentos con backoff exponencial
- Almacenamiento local y en la nube
- Despliegue con Docker

## Requisitos

- Python 3.10+
- Credenciales SUNAT (RUC, usuario, clave)
- Cuenta de Gmail (opcional, para notificaciones)
- Google Cloud Project (opcional, para Google Drive)
- PostgreSQL (opcional, para persistencia de jobs)

## Instalacion

### 1. Clonar el repositorio

```bash
git clone https://github.com/SuperInkaWeb/automatizacion-sunat-descarga-pdf-xml-backend.git
cd automatizacion-sunat-descarga-pdf-xml-backend
```

### 2. Crear entorno virtual

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales
```

## Configuracion

Crea un archivo `.env` en la raiz del proyecto con las siguientes variables:

```env
# Credenciales SUNAT (Requerido)
SUNAT_RUC=tu_ruc
SUNAT_USUARIO=tu_usuario
SUNAT_CLAVE=tu_clave

# Archivo Excel
EXCEL_FILE=comprobantes.xlsx

# Opciones de descarga
DESCARGAR_PDF=true
DESCARGAR_XML=true
OUTPUT_DIR=./descargas_sunat

# Google Drive (Opcional)
GOOGLE_CREDENTIALS_PATH=service_account.json
GOOGLE_DRIVE_FOLDER_ID=

# Correo electronico (Opcional)
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=465
EMAIL_USER=tu_correo@gmail.com
EMAIL_PASSWORD=tu_contrasena_de_aplicacion
EMAIL_DESTINATARIO=destinatario@ejemplo.com

# Google OAuth (Opcional)
GOOGLE_CLIENT_ID=tu_client_id
GOOGLE_CLIENT_SECRET=tu_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# Base de datos (Opcional)
DATABASE_URL=postgresql://user:password@host/database
```

> El `.env` es la fuente de verdad para las credenciales SUNAT. Si la base de
> datos conserva un usuario con credenciales antiguas, se registra una
> advertencia y se usan igualmente las del `.env`.

## Uso

### Ejecutar el servidor

```bash
python -m app.main
```

El servidor estara disponible en: `http://localhost:8000`

### Subir un Excel y descargar comprobantes

El Excel debe tener una fila de encabezados con las columnas **Tipo**, **Serie**,
**Numero** y **RUC Emisor** (el orden no importa). Si no se detectan los
encabezados, se asumen las columnas G, H, I y J.

```bash
curl -X POST "http://localhost:8000/descargar" \
  -F "file=@comprobantes.xlsx"
```

### Descargar varios comprobantes desde un JSON (lote)

Para solicitar la descarga sin Excel, envíe un array JSON con los datos de cada
comprobante. El endpoint crea un trabajo en segundo plano y responde de
inmediato con `job_id`; el avance se consulta con `GET /estado/{job_id}`.

```bash
curl -X POST "http://localhost:8000/descargar/lote" \
  -H "Content-Type: application/json" \
  -d '[
        {"tipo_doc": "01", "serie": "F001", "numero": "123", "ruc_emisor": "20123456789"},
        {"tipo_doc": "03", "serie": "B001", "numero": "45",  "ruc_emisor": "20123456789"}
      ]'
```

**Response:**
```json
{
  "job_id": "uuid-del-trabajo",
  "status": "pending",
  "total": 2,
  "duplicados_omitidos": 0
}
```

Reglas de la solicitud:

- Cada elemento acepta los mismos formatos que `/descargar/comprobante`
  (código o nombre del tipo, `numero` y `ruc_emisor` como texto o número).
- Si un elemento es inválido, se rechaza todo el lote con `400` y el detalle del
  problema.
- Los duplicados exactos se omiten y se informan en `duplicados_omitidos`.
- El máximo por solicitud se configura con `MAX_COMPROBANTES_POR_LOTE`
  (por defecto `500`); si se supera, responde `422`.
- El resultado final queda en `GET /estado/{job_id}` (`details` incluye total,
  PDFs/XMLs descargados y faltantes).
- La API de SUNAT puede responder `HTTP 500` de forma intermitente; el pipeline
  reintenta por archivo y por rondas. Por eso el job puede permanecer en
  `processing` varios minutos antes de completarse.
- El endpoint detecta si el comprobante es **emitido** (RUC emisor igual al RUC
  autenticado) o **recibido** (RUC emisor distinto) y consulta el recurso
  correcto de SUNAT (`-1` o `-2`).
- Si SUNAT responde `HTTP 422` con `codError 113` (“No hay resultados para la
  consulta”), el comprobante no pertenece al RUC autenticado: se marca como no
  encontrado y **no se reintenta**. Verifique que el `.env` tenga el RUC dueño
  de los comprobantes (emisor o receptor).
- Si no se descargó ningún archivo, el job termina en `failed`; si se descargó
  al menos uno, termina en `completed` y los pendientes quedan en
  `details.faltantes` con el motivo reportado por SUNAT.

### Descargar un comprobante puntual (PDF y XML)

Ademas de la carga masiva por Excel, se puede solicitar la descarga de un solo
comprobante. La API obtiene el token de SUNAT, descarga los archivos habilitados
(`DESCARGAR_PDF` / `DESCARGAR_XML`), los guarda en disco y los sube a Google
Drive si el usuario lo tiene vinculado.

```bash
curl -X POST "http://localhost:8000/descargar/comprobante" \
  -H "Content-Type: application/json" \
  -d '{
        "tipo_doc": "01",
        "serie": "F001",
        "numero": "123",
        "ruc_emisor": "20123456789"
      }'
```

`tipo_doc` acepta el codigo SUNAT (`01` factura, `03` boleta, `07` nota de
credito, `08` nota de debito, `09` guia de remision) o su nombre (`factura`,
`boleta`, etc.). Los campos numericos (`numero`, `ruc_emisor`) pueden enviarse
como texto o como numero.

Tambien se aceptan los mismos campos como formulario
(`application/x-www-form-urlencoded` / `multipart/form-data`) o como query
string:

```bash
curl -X POST "http://localhost:8000/descargar/comprobante?tipo_doc=01&serie=F001&numero=123&ruc_emisor=20123456789"
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
      "descarga_url": "/comprobante/archivo?tipo_doc=01&serie=F001&numero=123&ruc_emisor=20123456789&formato=pdf"
    },
    {
      "tipo": "xml",
      "nombre": "20123456789_F001_123.xml",
      "ruta": "descargas_sunat/xmls/20123456789_F001_123.xml",
      "descarga_url": "/comprobante/archivo?tipo_doc=01&serie=F001&numero=123&ruc_emisor=20123456789&formato=xml"
    }
  ],
  "faltantes": [],
  "descarga_zip_url": "/comprobante/archivo?tipo_doc=01&serie=F001&numero=123&ruc_emisor=20123456789&formato=zip"
}
```

Si uno de los dos archivos no pudo descargarse, la respuesta es `200` con
`"completo": false` y el detalle en `faltantes`. Si ninguno se pudo obtener, la
API responde `404`; los errores de credenciales o de conexion responden `502`/`503`.

### Descargar un archivo ya obtenido

```bash
# PDF
curl -OJ "http://localhost:8000/comprobante/archivo?tipo_doc=01&serie=F001&numero=123&ruc_emisor=20123456789&formato=pdf"

# ZIP con PDF + XML
curl -OJ "http://localhost:8000/comprobante/archivo?tipo_doc=01&serie=F001&numero=123&ruc_emisor=20123456789&formato=zip"
```

### Consultar estado de un trabajo

```bash
curl "http://localhost:8000/estado/{job_id}"
```

### Documentacion de la API

Una vez ejecutado el servidor, accede a la documentacion automatica en:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Despliegue con Docker

### Construir la imagen

```bash
docker build -t sunat-bot-v2 .
```

### Ejecutar el contenedor

```bash
docker run -d \
  --name sunat-bot \
  -p 8000:8000 \
  --env-file .env \
  sunat-bot-v2
```

### Docker Compose

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
    restart: unless-stopped
```

```bash
docker-compose up -d
```

## Despliegue en VPS bajo un subdirectorio

Para publicar la API en `https://servicios.algoritmojuridico.com/downloadpdf`
se incluye `docker-compose.yml`, un ejemplo de Nginx en
`deploy/nginx-downloadpdf.conf` y la guia completa en
[docs/despliegue-vps-subdirectorio.md](docs/despliegue-vps-subdirectorio.md).

Resumen:

```bash
cp .env.example .env
# En .env:
#   ROOT_PATH=/downloadpdf
#   CORS_ORIGINS=https://servicios.algoritmojuridico.com

mkdir -p data descargas_sunat uploads
docker compose up -d --build
```

Nginx publica el contenedor (escucha solo en `127.0.0.1:8010`):

```nginx
location = /downloadpdf { return 301 /downloadpdf/; }

location /downloadpdf/ {
    proxy_pass http://127.0.0.1:8010/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
}
```

La app, su documentacion (`/downloadpdf/docs`) y los enlaces de descarga
respetan automaticamente el prefijo configurado en `ROOT_PATH`.

## Estructura del Proyecto

```
.
├── app/
│   ├── main.py              # Punto de entrada FastAPI
│   ├── core/
│   │   ├── config.py        # Variables de entorno
│   │   ├── database.py      # Configuracion PostgreSQL
│   │   └── logging.py       # Sistema de logs
│   ├── api/
│   │   └── routes.py        # Endpoints HTTP
│   ├── models/
│   │   ├── comprobante.py   # Modelo de comprobante
│   │   └── db_models.py     # Modelos de base de datos
│   └── services/
│       ├── sunat_auth.py    # Login automatizado en SUNAT
│       ├── sunat_api.py     # Cliente API REST
│       ├── pipeline.py      # Orquestador de descargas
│       ├── storage.py       # Almacenamiento local
│       ├── drive_storage.py # Google Drive (Service Account)
│       ├── drive_storage_oauth.py # Google Drive (OAuth)
│       └── notifications.py # Correo electronico
├── docs/
│   ├── manual-usuario.md    # Manual de usuario
│   ├── manual-tecnico.md    # Manual tecnico
│   └── despliegue-vps-subdirectorio.md # Guia de despliegue
├── deploy/
│   └── nginx-downloadpdf.conf # Ejemplo de Nginx para /downloadpdf
├── docker-compose.yml       # Despliegue con Docker
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Endpoints

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/` | Informacion basica del servicio |
| GET | `/health` | Health check |
| POST | `/descargar` | Sube un Excel e inicia la descarga |
| POST | `/descargar/lote` | Recibe un array JSON y encola la descarga de varios comprobantes |
| POST | `/descargar/comprobante` | Descarga puntual (sincrona) de PDF/XML de un comprobante |
| GET | `/comprobante/archivo` | Entrega un PDF, XML o ZIP ya descargado |
| GET | `/estado/{job_id}` | Consulta el estado de un trabajo |
| GET | `/jobs` | Lista los ultimos trabajos |
| GET | `/auth/google` | Inicia autenticacion OAuth con Google |
| GET | `/auth/google/callback` | Callback de autenticacion OAuth |

## Documentacion

- [Manual de Usuario](docs/manual-usuario.md)
- [Manual Tecnico](docs/manual-tecnico.md)

## Licencia

MIT License

## Soporte

Para problemas o preguntas, abrir un issue en el repositorio.
