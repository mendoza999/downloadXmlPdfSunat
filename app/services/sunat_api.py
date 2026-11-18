import base64
import io
import json
import logging
import zipfile
from typing import Dict, Optional, Set

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class SunatErrorPermanente(RuntimeError):
    """Error de SUNAT que no se soluciona reintentando la misma consulta."""


class ComprobanteNoEncontrado(SunatErrorPermanente):
    """SUNAT no devolvio resultados para el comprobante consultado."""


class SolicitudRechazada(SunatErrorPermanente):
    """SUNAT rechazo los datos del comprobante (tipo, serie, RUC, etc.)."""


def _decodificar_payload_token(token: str) -> Dict:
    """Lee el payload del JWT sin verificar la firma (solo para obtener el RUC)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        datos = json.loads(base64.urlsafe_b64decode(payload))
        return datos if isinstance(datos, dict) else {}
    except Exception:
        return {}


def _ruc_desde_token(token: str) -> Optional[str]:
    datos = _decodificar_payload_token(token)
    userdata = datos.get("userdata") or {}
    ruc = datos.get("sub") or userdata.get("numRUC")
    return str(ruc) if ruc else None


def _codigos_error(data: Dict) -> Set[str]:
    return {
        str(error.get("codError"))
        for error in (data.get("errors") or [])
        if isinstance(error, dict) and error.get("codError") is not None
    }


def _detalle_error(data: Dict) -> str:
    detalles = [
        f"{error.get('codError')}: {error.get('desError')}"
        for error in (data.get("errors") or [])
        if isinstance(error, dict)
    ]
    return "; ".join(detalles) or str(data)[:300]


class SunatAPIClient:
    BASE_URL = "https://api-cpe.sunat.gob.pe/v1/contribuyente/consultacpe/comprobantes"

    def __init__(self, token: str, ruc_logueado: Optional[str] = None):
        self.token = token
        self.ruc_logueado = ruc_logueado or _ruc_desde_token(token)
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
        self.ruc_logueado = self.ruc_logueado or _ruc_desde_token(nuevo_token)
        self.session = self._crear_sesion()

    def _modos_consulta(self, ruc_emisor: str):
        """``1`` = comprobantes emitidos; ``2`` = comprobantes recibidos.

        Si el RUC emisor es el mismo RUC autenticado, el comprobante se busca
        como emitido (``-1``). En caso contrario se busca como recibido (``-2``).
        Si no se pudo leer el RUC del token, se prueban ambos.
        """
        if not self.ruc_logueado:
            return ["2", "1"]
        if str(ruc_emisor) == str(self.ruc_logueado):
            return ["1"]
        return ["2"]

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
        modos = self._modos_consulta(ruc)
        ultimo_error = ""

        for posicion, modo in enumerate(modos):
            url = f"{self.BASE_URL}/{llave}-{modo}/{sufijo}"
            try:
                resp = self.session.get(url, timeout=30)
            except requests.RequestException as e:
                logger.error("[%s] Error de red para %s: %s", etiqueta, llave, e)
                return None

            if resp.status_code == 401:
                raise PermissionError("Token expirado")

            if resp.status_code == 422:
                try:
                    data = resp.json()
                except ValueError:
                    data = {}
                codigos = _codigos_error(data)
                detalle = _detalle_error(data)
                ultimo_error = detalle

                # 105: el emisor debe ser el RUC logueado -> probar el otro modo
                if "105" in codigos and posicion + 1 < len(modos):
                    logger.info(
                        "[%s] %s requiere consulta como emitido; reintentando modo -1",
                        etiqueta,
                        llave,
                    )
                    continue
                # 113: no hay resultados para esa consulta (error permanente)
                if "113" in codigos:
                    if posicion + 1 < len(modos):
                        # Sin RUC conocido en el token: probar el otro modo
                        continue
                    raise ComprobanteNoEncontrado(
                        f"SUNAT no encontró {llave} para el RUC autenticado "
                        f"({self.ruc_logueado or 'desconocido'}). {detalle}"
                    )
                raise SolicitudRechazada(f"SUNAT rechazó {llave}: {detalle}")

            if resp.status_code != 200:
                logger.error(
                    "[%s] HTTP %s para %s: %s",
                    etiqueta,
                    resp.status_code,
                    llave,
                    resp.text[:500],
                )
                if resp.status_code >= 500:
                    # Errores 5xx de SUNAT son intermitentes: se reintentan
                    return None
                raise SolicitudRechazada(
                    f"SUNAT respondió HTTP {resp.status_code} para {llave}: "
                    f"{resp.text[:300]}"
                )

            try:
                data = resp.json()
            except ValueError:
                logger.error("[%s] Respuesta no es JSON para %s", etiqueta, llave)
                return None

            b64 = data.get("valArchivo") or ""
            if not b64:
                logger.error("[%s] valArchivo vacío para %s", etiqueta, llave)
                return None

            logger.info(
                "[%s] %s | modo -%s | b64=%s caracteres",
                etiqueta,
                data.get("nomArchivo", "?"),
                modo,
                len(b64),
            )
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

        if ultimo_error:
            raise SolicitudRechazada(f"SUNAT rechazó {llave}: {ultimo_error}")
        return None

    def fetch_pdf(self, ruc, tipo, serie, numero) -> Optional[bytes]:
        return self._descargar_archivo(ruc, tipo, serie, numero, "01", "PDF")

    def fetch_xml(self, ruc, tipo, serie, numero) -> Optional[bytes]:
        return self._descargar_archivo(ruc, tipo, serie, numero, "02", "XML")
