import base64
import io
import logging
import zipfile
from typing import Optional

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class SunatAPIClient:
    BASE_URL = "https://api-cpe.sunat.gob.pe/v1/contribuyente/consultacpe/comprobantes"

    def __init__(self, token: str):
        self.token = token
        self.session = self._crear_sesion()

    def _crear_sesion(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Origin": "https://e-factura.sunat.gob.pe",
                "Referer": "https://e-factura.sunat.gob.pe/",
            }
        )
        return s

    def actualizar_token(self, nuevo_token: str):
        self.token = nuevo_token
        self.session = self._crear_sesion()

    @staticmethod
    def _extraer_contenido(zip_bytes: bytes, sufijo: str, etiqueta: str) -> Optional[bytes]:
        extension = ".pdf" if sufijo == "01" else ".xml"

        # Algunos comprobantes llegan sin comprimir
        contenido_xml = zip_bytes.lstrip(b"\xef\xbb\xbf \r\n\t")
        if contenido_xml[:5].lower() == b"<?xml" or contenido_xml[:5] == b"%PDF-":
            return contenido_xml

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                nombres = zf.namelist()
                if not nombres:
                    logger.error("[%s] El ZIP de SUNAT está vacío", etiqueta)
                    return None

                candidatos = [n for n in nombres if n.lower().endswith(extension)]
                if not candidatos:
                    candidatos = [n for n in nombres if not n.endswith("/")]
                if not candidatos:
                    logger.error("[%s] El ZIP no contiene archivos: %s", etiqueta, nombres)
                    return None

                mejor = max(candidatos, key=lambda n: zf.getinfo(n).file_size)
                return zf.read(mejor)
        except zipfile.BadZipFile:
            logger.error("[%s] La respuesta de SUNAT no es un ZIP válido", etiqueta)
            return None

    def _descargar_archivo(
        self, ruc: str, tipo: str, serie: str, numero: str, sufijo: str, etiqueta: str
    ) -> Optional[bytes]:
        llave = f"{ruc}-{tipo}-{serie}-{numero}"
        url = f"{self.BASE_URL}/{llave}-2/{sufijo}"
        try:
            resp = self.session.get(url, timeout=30)
        except requests.RequestException as e:
            logger.error("[%s] Error de red para %s: %s", etiqueta, llave, e)
            return None

        if resp.status_code == 401:
            raise PermissionError("Token expirado")

        if resp.status_code != 200:
            logger.error(
                "[%s] HTTP %s para %s: %s",
                etiqueta,
                resp.status_code,
                llave,
                resp.text[:200],
            )
            return None

        try:
            data = resp.json()
        except ValueError:
            logger.error("[%s] Respuesta no es JSON para %s", etiqueta, llave)
            return None

        b64 = data.get("valArchivo") or ""
        if not b64:
            logger.error("[%s] valArchivo vacío para %s", etiqueta, llave)
            return None

        logger.info("[%s] %s | b64=%s caracteres", etiqueta, data.get("nomArchivo", "?"), len(b64))
        try:
            zip_bytes = base64.b64decode(b64)
        except Exception as e:
            logger.error("[%s] base64 inválido para %s: %s", etiqueta, llave, e)
            return None

        contenido = self._extraer_contenido(zip_bytes, sufijo, etiqueta)
        if contenido is None:
            return None

        logger.info("[%s] ✅ %s bytes para %s", etiqueta, f"{len(contenido):,}", llave)
        return contenido

    def fetch_pdf(self, ruc, tipo, serie, numero) -> Optional[bytes]:
        return self._descargar_archivo(ruc, tipo, serie, numero, "01", "PDF")

    def fetch_xml(self, ruc, tipo, serie, numero) -> Optional[bytes]:
        return self._descargar_archivo(ruc, tipo, serie, numero, "02", "XML")
