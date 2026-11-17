# Despliegue en VPS bajo un subdirectorio

Guia para publicar la API en:

```
https://servicios.algoritmojuridico.com/downloadpdf
```

La aplicacion se ejecuta con Docker en `127.0.0.1:8010` y Nginx la publica
bajo el prefijo `/downloadpdf/`.

---

## 1. Requisitos en la VPS

- Ubuntu 22.04 / 24.04 (o similar)
- Docker Engine + plugin `docker compose`
- Nginx instalado y sirviendo `servicios.algoritmojuridico.com`
- Registro DNS del dominio apuntando a la VPS
- Al menos **1 GB de RAM** libre (Chromium/Playwright consume memoria)

```bash
sudo apt update
sudo apt install -y nginx git
# Docker: seguir la guia oficial si aun no esta instalado
```

---

## 2. Obtener el proyecto

```bash
sudo mkdir -p /opt/downloadpdf
sudo chown -R $USER:$USER /opt/downloadpdf
git clone https://github.com/mendoza999/downloadXmlPdfSunat.git /opt/downloadpdf
cd /opt/downloadpdf
```

---

## 3. Configurar variables de entorno

```bash
cp .env.example .env
nano .env
```

Valores minimos para produccion:

```env
SUNAT_RUC=20000000001
SUNAT_USUARIO=USUARIO_SOL
SUNAT_CLAVE=CLAVE_SOL

ROOT_PATH=/downloadpdf
CORS_ORIGINS=https://servicios.algoritmojuridico.com

GOOGLE_REDIRECT_URI=https://servicios.algoritmojuridico.com/downloadpdf/auth/google/callback

DESCARGAR_PDF=true
DESCARGAR_XML=true
```

> `docker-compose.yml` fuerza `DATABASE_URL=sqlite:////app/data/sunat.db`, por lo
> que la base queda persistida en `./data/`. Si usa PostgreSQL, edite esa linea
> del compose.

Crear las carpetas persistentes:

```bash
mkdir -p data descargas_sunat uploads
```

---

## 4. Levantar el contenedor

```bash
docker compose up -d --build
docker compose logs -f --tail=100
```

Verificacion local (sin pasar por Nginx):

```bash
curl http://127.0.0.1:8010/health
# {"status":"ok"}

curl -I http://127.0.0.1:8010/docs
# 200 OK
```

Si el puerto `8010` esta ocupado, cambie `APP_PORT` en el `.env`:

```env
APP_PORT=8011
```

---

## 5. Configurar Nginx

Edite el `server {}` del dominio (normalmente en
`/etc/nginx/sites-available/servicios.algoritmojuridico.com`) y agregue:

```nginx
location = /downloadpdf {
    return 301 /downloadpdf/;
}

location /downloadpdf/ {
    # La barra final elimina el prefijo /downloadpdf/ antes de llegar a FastAPI
    proxy_pass http://127.0.0.1:8010/;

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    client_max_body_size 25m;
    proxy_connect_timeout 60s;
    proxy_send_timeout 600s;
    proxy_read_timeout 600s;
}
```

Tambien puede copiar el archivo listo `deploy/nginx-downloadpdf.conf`.

Aplicar cambios:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Si aun no tiene SSL:

```bash
sudo certbot --nginx -d servicios.algoritmojuridico.com
```

### Alternativa con Apache

```apache
RedirectMatch ^/downloadpdf$ /downloadpdf/

ProxyPreserveHost On
ProxyPass        /downloadpdf/ http://127.0.0.1:8010/
ProxyPassReverse /downloadpdf/ http://127.0.0.1:8010/

RequestHeader set X-Forwarded-Proto "https"
ProxyTimeout 600
```

Habilitar modulos: `a2enmod proxy proxy_http headers rewrite` y recargar Apache.

---

## 6. Probar la URL publica

```bash
curl https://servicios.algoritmojuridico.com/downloadpdf/health
```

Documentacion interactiva:

```
https://servicios.algoritmojuridico.com/downloadpdf/docs
```

Descarga puntual:

```bash
curl -X POST "https://servicios.algoritmojuridico.com/downloadpdf/descargar/comprobante" \
  -H "Content-Type: application/json" \
  -d '{"tipo_doc":"01","serie":"F001","numero":"123","ruc_emisor":"20123456789"}'
```

Las rutas devueltas en `descarga_url` y `descarga_zip_url` ya incluyen el
prefijo `/downloadpdf`, por ejemplo:

```
/downloadpdf/comprobante/archivo?tipo_doc=01&serie=F001&numero=123&ruc_emisor=20123456789&formato=zip
```

---

## 7. Google Drive (opcional)

En Google Cloud Console, en el cliente OAuth, agregue como URI de redireccion
autorizado:

```
https://servicios.algoritmojuridico.com/downloadpdf/auth/google/callback
```

Luego abra una vez:

```
https://servicios.algoritmojuridico.com/downloadpdf/auth/google
```

---

## 8. Operacion

```bash
# Ver estado
docker compose ps

# Logs
docker compose logs -f --tail=200

# Actualizar desde GitHub
git pull
docker compose up -d --build

# Detener
docker compose down
```

Datos persistentes:

| Ruta local | Contenido |
|---|---|
| `./data/` | Base de datos SQLite |
| `./descargas_sunat/` | PDFs y XMLs descargados |
| `./uploads/` | Excels subidos (se eliminan al procesar) |

---

## 9. Puntos importantes

- `ROOT_PATH` debe ser exactamente el prefijo publico (`/downloadpdf`) y Nginx
  debe quitar ese prefijo con la barra final de `proxy_pass`.
- No publique el puerto `8010` en Internet: solo Nginx debe acceder a el.
- La descarga puntual puede tardar por el login con Playwright y los reintentos;
  por eso los timeouts de Nginx son amplios.
- El contenedor necesita `shm_size: 1gb` (ya incluido en `docker-compose.yml`)
  para que Chromium funcione correctamente.
- Mantenga `.env` fuera de Git (ya esta en `.gitignore`).
