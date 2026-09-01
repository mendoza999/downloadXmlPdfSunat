import base64
import io
import zipfile
import requests
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class SunatAPIClient:
    BASE_URL = "https://api-cpe.sunat.gob.pe/v1/contribuyente/consultacpe/comprobantes"

    def __init__(self, token: str):
        self.token = token
        self.session = self._crear_sesion()

    def _crear_sesion(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "Mozilla/5.0 ...",
            "Accept": "application/json",
            "Origin": "https://e-factura.sunat.gob.pe",
            "Referer": "https://e-factura.sunat.gob.pe/",
        })
        return s

    def actualizar_token(self, nuevo_token: str):
        self.token = nuevo_token
        self.session = self._crear_sesion()

    def _descargar_archivo(self, ruc: str, tipo: str, serie: str, numero: str,
                           sufijo: str, etiqueta: str) -> Optional[bytes]:
        llave = f"{ruc}-{tipo}-{serie}-{numero}"
        url = f"{self.BASE_URL}/{llave}-2/{sufijo}"
        try:
            resp = self.session.get(url, timeout=30)
        except requests.RequestException as e:
            logger.error(f"[{etiqueta}] Error de red: {e}")
            return None

        if resp.status_code == 401:
            raise PermissionError("Token expirado")
        if resp.status_code != 200:
            logger.error(f"[{etiqueta}] HTTP {resp.status_code}: {resp.text[:150]}")
            return None

        try:
            data = resp.json()
        except ValueError:
            logger.error(f"[{etiqueta}] Respuesta no es JSON")
            return None

        b64 = data.get("valArchivo", "")
        if not b64:
            logger.error(f"[{etiqueta}] valArchivo vacío")
            return None

        logger.info(f"[{etiqueta}] {data.get('nomArchivo', '?')} | b64={len(b64)}")
        try:
            zip_bytes = base64.b64decode(b64)
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                nombres = zf.namelist()
                if not nombres:
                    raise Exception("ZIP vacío")
                
                extension = ".pdf" if sufijo == "01" else ".xml"
                candidatos = [n for n in nombres if n.lower().endswith(extension)]

                if not candidatos:
                    candidatos = nombres

                mejor = max(candidatos, key=lambda n: zf.getinfo(n).file_size)
                contenido = zf.read(mejor)
            
                logger.info(f"[{etiqueta}] ✅ {len(contenido):,} bytes")
                return contenido
        except Exception as e:
            logger.error(f"[{etiqueta}] Error al descomprimir: {e}")
            return None

    def fetch_pdf(self, ruc, tipo, serie, numero) -> Optional[bytes]:
        return self._descargar_archivo(ruc, tipo, serie, numero, "01", "PDF")

    def fetch_xml(self, ruc, tipo, serie, numero) -> Optional[bytes]:
        return self._descargar_archivo(ruc, tipo, serie, numero, "02", "XML")