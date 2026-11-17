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
│   └── manual-tecnico.md    # Manual tecnico
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
