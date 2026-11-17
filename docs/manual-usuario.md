# Manual de Usuario - SUNAT Bot V2

## 1. Introduccion

**SUNAT Bot V2** es una herramienta automatizada que descarga comprobantes de pago (facturas y boletas) desde el portal de la SUNAT (Superintendencia Nacional de Aduanas y de Administracion Tributaria del Peru).

El bot permite:

- Leer un archivo Excel con los datos de los comprobantes a descargar.
- Ingresar automaticamente al portal SOL de la SUNAT.
- Descargar los archivos PDF y XML de cada comprobante.
- Guardar los archivos localmente en su equipo.
- Opcionalmente, subir los archivos a Google Drive.
- Recibir un correo electronico con el resumen de la operacion.

---

## 2. Requisitos Previos

### 2.1 Credenciales SUNAT

Necesitas tener acceso al portal SOL de la SUNAT con las siguientes credenciales:

| Dato | Descripcion |
|------|-------------|
| RUC | Numero de RUC de la empresa o persona |
| Usuario | Usuario del portal SOL (ej: `TU_USUARIO`) |
| Clave | Contrasena del portal SOL |

### 2.2 Archivo Excel

El archivo Excel debe contener los comprobantes a descargar. El bot detecta las columnas por el nombre del encabezado, por lo que el orden puede variar:

| Encabezado | Contenido | Ejemplo |
|------------|-----------|---------|
| Tipo / Tipo de documento | `1` (Factura), `3` (Boleta) o el codigo SUNAT | `1` |
| Serie | Serie del comprobante | `F001`, `B001` |
| Numero / Nro Comprobante | Numero del comprobante | `12345` |
| RUC Emisor / RUC del emisor | RUC del emisor (11 digitos) | `12345678901` |

> **Nota:** El archivo debe tener una fila de encabezados (puede no ser la primera fila). Si el archivo no tiene encabezados reconocibles, se asume la estructura clasica: columnas G (tipo), H (serie), I (numero) y J (RUC emisor).

### 2.3 Cuenta de Gmail (Opcional)

Si deseas recibir notificaciones por correo o subir archivos a Google Drive, necesitas:

- Una cuenta de Gmail
- Una contrasena de aplicacion de Gmail (no la contrasena normal)
- Habilitar el envio de correos SMTP en la cuenta

### 2.4 Google Drive (Opcional)

Si deseas subir archivos automaticamente a Google Drive, necesitas configurar una de estas opciones:

- **Service Account:** Un archivo JSON de credenciales de Google Cloud
- **OAuth:** Client ID y Client Secret de Google Cloud Console

---

## 3. Configuracion

### 3.1 Archivo de Variables de Entorno

El archivo `.env` en la raiz del proyecto contiene toda la configuracion necesaria:

```env
# Credenciales SUNAT
SUNAT_RUC=12345678901
SUNAT_USUARIO=TU_USUARIO
SUNAT_CLAVE=TU_CLAVE

# Nombre del archivo Excel con los comprobantes
EXCEL_FILE=Compras Abril 2026.xlsx

# Opciones de descarga (true/false)
DESCARGAR_PDF=true
DESCARGAR_XML=true

# Directorio de salida
OUTPUT_DIR=./descargas_sunat

# Parametros de concurrencia (opcionales)
# MAX_WORKERS=3
# MAX_RONDAS=10

# Google Drive (Service Account)
GOOGLE_CREDENTIALS_PATH=service_account.json
# GOOGLE_DRIVE_FOLDER_ID=

# Correo electronico
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=465
EMAIL_USER=tu_correo@gmail.com
EMAIL_PASSWORD=tu_contrasena_de_aplicacion
EMAIL_DESTINATARIO=destinatario@ejemplo.com

# Google OAuth
GOOGLE_CLIENT_ID=tu_client_id
GOOGLE_CLIENT_SECRET=tu_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# Base de datos
DATABASE_URL=postgresql://usuario:password@host/database
```

### 3.2 Descripcion de Variables

#### Credenciales SUNAT (Requerido)

| Variable | Descripcion | Valor por defecto |
|----------|-------------|-------------------|
| `SUNAT_RUC` | Numero de RUC | `12345678901` |
| `SUNAT_USUARIO` | Usuario del portal SOL | `TU_USUARIO` |
| `SUNAT_CLAVE` | Contrasena del portal SOL | `TU_CLAVE` |

#### Archivo Excel

| Variable | Descripcion | Valor por defecto |
|----------|-------------|-------------------|
| `EXCEL_FILE` | Ruta al archivo Excel | `Compras Abril 2026.xlsx` |

#### Opciones de Descarga

| Variable | Descripcion | Valor por defecto |
|----------|-------------|-------------------|
| `DESCARGAR_PDF` | Descargar archivos PDF | `true` |
| `DESCARGAR_XML` | Descargar archivos XML | `true` |
| `OUTPUT_DIR` | Carpeta de salida | `./descargas_sunat` |

#### Concurrencia y Reintentos

| Variable | Descripcion | Valor por defecto |
|----------|-------------|-------------------|
| `MAX_WORKERS` | Hilos simultaneos para descarga | `3` |
| `MAX_REINTENTOS_INMEDIATOS` | Reintentos inmediatos por archivo | `2` |
| `DELAY_REINTENTO` | Espera entre reintentos (segundos) | `2.0` |
| `PAUSA_MIN_ENTRE_CPE` | Pausa minima entre comprobantes | `0.8` |
| `PAUSA_MAX_ENTRE_CPE` | Pausa maxima entre comprobantes | `1.5` |
| `PAUSA_MIN_ENTRE_ARCHIVOS` | Pausa minima entre archivos | `0.5` |
| `PAUSA_MAX_ENTRE_ARCHIVOS` | Pausa maxima entre archivos | `1.2` |
| `ESPERA_BASE_RONDA_SEG` | Espera base entre rondas | `60` |
| `FACTOR_BACKOFF` | Factor de backoff exponencial | `1.5` |
| `ESPERA_MAX_RONDA_SEG` | Espera maxima entre rondas | `300` |
| `MAX_RONDAS_ARCHIVOS` | Maximo de rondas de reintento | `10` |

#### Google Drive

| Variable | Descripcion | Valor por defecto |
|----------|-------------|-------------------|
| `GOOGLE_CREDENTIALS_PATH` | Ruta al archivo JSON de Service Account | `""` |
| `GOOGLE_DRIVE_FOLDER_ID` | ID de carpeta padre en Drive | `None` |

#### Correo Electronico

| Variable | Descripcion | Valor por defecto |
|----------|-------------|-------------------|
| `EMAIL_SMTP_SERVER` | Servidor SMTP | `smtp.gmail.com` |
| `EMAIL_SMTP_PORT` | Puerto SMTP | `465` |
| `EMAIL_USER` | Correo remitente | `""` |
| `EMAIL_PASSWORD` | Contrasena de aplicacion | `""` |
| `EMAIL_DESTINATARIO` | Correo destinatario | `""` |

#### Google OAuth

| Variable | Descripcion | Valor por defecto |
|----------|-------------|-------------------|
| `GOOGLE_CLIENT_ID` | Client ID de Google Cloud | `""` |
| `GOOGLE_CLIENT_SECRET` | Client Secret de Google Cloud | `""` |
| `GOOGLE_REDIRECT_URI` | URI de redireccionamiento | `http://localhost:8000/auth/google/callback` |

#### Base de Datos

| Variable | Descripcion | Valor por defecto |
|----------|-------------|-------------------|
| `DATABASE_URL` | URL de conexion a PostgreSQL | `sqlite:///./test.db` |

---

## 4. Uso del Bot

### 4.1 Preparar el Archivo Excel

1. Crea un archivo Excel con los comprobantes a descargar.
2. Asegurate de que las columnas G, H, J y M contengan los datos correctos.
3. La primera fila debe tener encabezados.
4. Guarda el archivo en formato `.xlsx`.

**Ejemplo de estructura del Excel:**

| ... | G | ... | H | ... | J | ... | M |
|-----|------|-----|------|-----|------|-----|--------------|
| ... | Tipo | ... | Serie | ... | Numero | ... | RUC Emisor |
| ... | 1 | ... | F001 | ... | 12345 | ... | 12345678901 |
| ... | 1 | ... | F001 | ... | 12346 | ... | 12345678901 |

### 4.2 Ejecutar el Bot

#### Opcion 1: Ejecutar Localmente

```bash
# Instalar dependencias
pip install -r requirements.txt

# Instalar navegadores de Playwright
playwright install chromium

# Ejecutar el bot
python -m app.main
```

El servidor estara disponible en: `http://localhost:8000`

#### Opcion 2: Ejecutar con Docker

```bash
# Construir la imagen
docker build -t sunat-bot-v2 .

# Ejecutar el contenedor
docker run -d --name sunat-bot -p 8000:8000 sunat-bot-v2
```

### 4.3 Subir un Excel y Descargar Comprobantes

#### Usando cURL

```bash
# Subir el archivo Excel e iniciar la descarga
curl -X POST "http://localhost:8000/descargar" \
  -F "file=@Compras Abril 2026.xlsx"

# Respuesta:
# {"job_id": "uuid-del-trabajo", "status": "pending"}
```

#### Usando PowerShell

```powershell
# Subir el archivo Excel e iniciar la descarga
Invoke-WebRequest -Uri "http://localhost:8000/descargar" `
  -Method POST `
  -InFile "Compras Abril 2026.xlsx" `
  -ContentType "multipart/form-data"
```

#### Usando Python

```python
import requests

url = "http://localhost:8000/descargar"
files = {"file": open("Compras Abril 2026.xlsx", "rb")}
response = requests.post(url, files=files)
print(response.json())  # {"job_id": "uuid", "status": "pending"}
```

### 4.4 Consultar Estado de un Trabajo

```bash
# Consultar el estado del trabajo
curl "http://localhost:8000/estado/{job_id}"

# Respuesta:
# {
#   "job_id": "uuid-del-trabajo",
#   "status": "completed",
#   "message": "Descarga completada exitosamente.",
#   "excel_filename": "Compras Abril 2026.xlsx",
#   "created_at": "2026-09-01T10:00:00"
# }
```

**Estados posibles del trabajo:**

| Estado | Descripcion |
|--------|-------------|
| `pending` | El trabajo esta en cola, esperando procesarse |
| `processing` | El trabajo se esta ejecutando |
| `completed` | La descarga finalizo correctamente |
| `failed` | La descarga fallo (ver message para detalles) |

### 4.5 Archivos Descargados

Los archivos se guardan en la carpeta configurada en `OUTPUT_DIR`:

```
descargas_sunat/
├── pdfs/
│   ├── 12345678901_F001_12345.pdf
│   ├── 12345678901_F001_12346.pdf
│   └── ...
└── xmls/
    ├── 12345678901_F001_12345.xml
    ├── 12345678901_F001_12346.xml
    └── ...
```

**Formato de nombre de archivo:** `{RUC}_{SERIE}_{NUMERO}.{ext}`

---

## 5. Integracion con Google Drive

### 5.1 Configuracion con Service Account

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto o selecciona uno existente.
3. Habilita la API de Google Drive.
4. Crea una cuenta de servicio (Service Account).
5. Descarga el archivo JSON de credenciales.
6. Coloca el archivo en la raiz del proyecto.
7. Configura la variable `GOOGLE_CREDENTIALS_PATH` en `.env`.

### 5.2 Configuracion con OAuth

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto o selecciona uno existente.
3. Habilita la API de Google Drive.
4. Crea credenciales OAuth 2.0.
5. Configura las variables en `.env`:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI`
6. Ejecuta el bot y accede a `http://localhost:8000/auth/google` para autenticarte.

### 5.3 Uso

Una vez configurado, los archivos se subiran automaticamente a Google Drive despues de ser descargados. Se creara una carpeta con la fecha actual (ej: `FACTURAS DEL 2026-09-01`).

---

## 6. Notificaciones por Correo

### 6.1 Configuracion de Gmail

1. Ve a la configuracion de tu cuenta de Google.
2. Habilita la verificacion en dos pasos.
3. Crea una contrasena de aplicacion en [Google Account > Security > App passwords](https://myaccount.google.com/apppasswords).
4. Configura las variables en `.env`:
   - `EMAIL_USER`: Tu correo de Gmail
   - `EMAIL_PASSWORD`: La contrasena de aplicacion generada
   - `EMAIL_DESTINATARIO`: Correo que recibira las notificaciones

### 6.2 Tipos de Notificacion

- **Descarga exitosa:** Se envia un correo con el resumen de archivos descargados.
- **Descarga fallida:** Se envia un correo con el error occurredido.
- **Descarga incompleta:** Se envia un correo indicando que comprobantes quedaron pendientes.

---

## 7. Solucion de Problemas

### Errores Comunes

| Error | Causa | Solucion |
|-------|-------|----------|
| `No se pudo obtener el token` | Credenciales SUNAT incorrectas o portal caido | Verifica tus credenciales en `.env` y que el portal SOL este operativo |
| `SUNAT solicita un CAPTCHA` | Demasiados intentos de login fallidos | Ingresa manualmente al portal SOL una vez para reiniciar el contador y vuelve a ejecutar la descarga |
| `Token expirado` | El token de SUNAT expiro durante la descarga | El bot intenta regenerarlo automaticamente. Si persiste, ejecuta manualmente |
| `El archivo debe ser un Excel` | Se subio un archivo que no es `.xlsx` o `.xls` | Asegurate de subir un archivo Excel valido |
| `No se encontraron comprobantes validos` | El Excel no tiene encabezados reconocibles o los RUC no tienen 11 digitos | Revisa la tabla de la seccion 2.2 y el detalle del error |
| `Job no encontrado` | El ID del trabajo no existe en la base de datos | Verifica que el ID sea correcto |
| `Error de red` | Problemas de conexion con la API de SUNAT | Verifica tu conexion a internet |
| `No se pudo subir a Drive` | Credenciales de Google incorrectas o API no habilitada | Revisa la configuracion de Google Drive |

### Logs

Los logs del bot muestran informacion detallada del proceso:

```
2026-09-01 10:00:00 [INFO] (pipeline.py:102) - Modo de descarga: PDF + XML
2026-09-01 10:00:00 [INFO] (pipeline.py:109) - Total: 50 | Ya completos: 0 | Pendientes: 50
2026-09-01 10:00:05 [INFO] (sunat_auth.py:24) - Token interceptado.
2026-09-01 10:00:10 [INFO] (sunat_api.py:76) - [PDF] 45,678 bytes
```

### Rendimiento

- **MAX_WORKERS=3:** Por defecto, 3 hilos simultaneos. Puedes aumentar para mayor velocidad, pero cuidado con los bloqueos de SUNAT.
- **Pausas entre requests:** Configuradas para evitar que SUNAT bloquee tu IP. No las reduzcas demasiado.
- **Backoff exponencial:** Si hay muchos errores, el bot espera mas tiempo entre rondas.

---

## 8. Preguntas Frecuentes

### P: Puedo usar el bot con multiples RUCs?

**R:** Si. El bot descarga comprobantes de cualquier RUC que este en el archivo Excel. Las credenciales en `.env` son para el login en SUNAT, pero los comprobantes pueden ser de cualquier emisor.

### P: Que pasa si el token de SUNAT expira?

**R:** El bot detecta automaticamente cuando el token expira (error 401) y lo regenera mediante un nuevo login en el portal SOL.

### P: Cuantos comprobantes puedo descargar a la vez?

**R:** No hay limite estricto. El bot procesa los comprobantes en rondas. Si hay muchos comprobantes, el proceso puede tardar varios minutos. Se recomienda no mas de 500 comprobantes por ejecucion.

### P: Puedo pausar y reanudar una descarga?

**R:** El bot implementa un sistema de reintentos. Si un comprobante falla, se intenta en la siguiente ronda. Los archivos ya descargados no se vuelven a descargar.

### P: El bot funciona en Windows, Linux y Mac?

**R:** Si, el bot funciona en cualquier sistema operativo. Sin embargo, se recomienda usar Docker para evitar problemas de compatibilidad con Playwright.
