import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Set, Tuple

from app.core import config
from app.models.comprobante import Comprobante, leer_excel
from app.services.notifications import enviar_correo
from app.services.storage import LocalStorage
from app.services.sunat_api import SunatAPIClient, SunatErrorPermanente

logger = logging.getLogger(__name__)

# Centinela: SUNAT indicó que el comprobante no existe / no corresponde.
_NO_ENCONTRADO = object()


class DocumentPipeline:
    def __init__(
        self,
        excel_path: Optional[str],
        token: str,
        storage: LocalStorage,
        drive=None,
        descargar_pdf: bool = True,
        descargar_xml: bool = True,
        sunat_credentials: Optional[Tuple[str, str, str]] = None,
    ):
        self.excel_path = excel_path
        self.sunat_credentials = sunat_credentials
        ruc_logueado = sunat_credentials[0] if sunat_credentials else None
        self.client = SunatAPIClient(token, ruc_logueado=ruc_logueado)
        self.storage = storage
        self.drive = drive
        self.descargar_pdf = descargar_pdf
        self.descargar_xml = descargar_xml
        self._token_lock = threading.Lock()
        if self.client.ruc_logueado:
            logger.info("RUC autenticado en SUNAT: %s", self.client.ruc_logueado)

    # ── utilidades internas ────────────────────────────────────────────
    def _falta_algo(self, cpe: Comprobante) -> Set[str]:
        falta = set()
        if self.descargar_pdf and not self.storage.existe_pdf(cpe):
            falta.add("pdf")
        if self.descargar_xml and not self.storage.existe_xml(cpe):
            falta.add("xml")
        return falta

    def _comprobante_completo(self, cpe: Comprobante) -> bool:
        return not bool(self._falta_algo(cpe))

    def _renovar_token(self):
        """Regenera el token SUNAT. Serializado para evitar logins simultáneos."""
        if not self.sunat_credentials:
            raise RuntimeError("No hay credenciales SUNAT para renovar el token")
        with self._token_lock:
            ruc, usuario, clave = self.sunat_credentials
            nuevo = self._obtener_token(ruc, usuario, clave)
            self.client.actualizar_token(nuevo)
            logger.info("🔐 Token renovado correctamente.")

    @staticmethod
    def _obtener_token(ruc: str, usuario: str, clave: str) -> str:
        # Import local: Playwright tarda en cargar y solo se necesita aquí
        from app.services.sunat_auth import obtener_token_con_reintentos

        return obtener_token_con_reintentos(ruc, usuario, clave)

    def _descargar_archivo_con_reintento(
        self, cpe: Comprobante, tipo: str, etiqueta: str
    ) -> Optional[bytes]:
        for intento in range(1 + config.MAX_REINTENTOS_INMEDIATOS):
            try:
                if tipo == "pdf":
                    data = self.client.fetch_pdf(cpe.ruc, cpe.tipo, cpe.serie, cpe.numero)
                else:
                    data = self.client.fetch_xml(cpe.ruc, cpe.tipo, cpe.serie, cpe.numero)
            except PermissionError:
                raise
            except SunatErrorPermanente as e:
                cpe._motivo = str(e)  # type: ignore[attr-defined]
                logger.warning(
                    "[%s] %s-%s (RUC %s): %s",
                    etiqueta,
                    cpe.serie,
                    cpe.numero,
                    cpe.ruc,
                    e,
                )
                return _NO_ENCONTRADO
            except Exception as e:
                logger.error("[%s] %s-%s: excepción %s", etiqueta, cpe.serie, cpe.numero, e)
                data = None

            if data:
                return data
            if intento < config.MAX_REINTENTOS_INMEDIATOS:
                time.sleep(config.DELAY_REINTENTO)
        return None

    def _guardar_y_subir(self, cpe: Comprobante, tipo: str, data: bytes):
        """Guarda localmente y, si Drive está configurado, sube a la nube."""
        self.storage.guardar(cpe, tipo, data)

        if self.drive:
            nombre_archivo = f"{self.storage.nombre_base(cpe)}.{tipo}"
            ruta_local = (
                self.storage.path_pdf(cpe) if tipo == "pdf" else self.storage.path_xml(cpe)
            )
            try:
                self.drive.subir_comprobante(ruta_local, nombre_archivo)
            except Exception as e:
                logger.error("No se pudo subir %s a Drive: %s", nombre_archivo, e)

    def _procesar_comprobante(self, cpe: Comprobante) -> Optional[Comprobante]:
        falta = self._falta_algo(cpe)
        if not falta:
            return None

        permanentes = set()
        for archivo in sorted(falta):
            time.sleep(
                random.uniform(config.PAUSA_MIN_ENTRE_ARCHIVOS, config.PAUSA_MAX_ENTRE_ARCHIVOS)
            )
            data = self._descargar_archivo_con_reintento(cpe, archivo, archivo.upper())
            if data is _NO_ENCONTRADO:
                permanentes.add(archivo)
            elif data:
                self._guardar_y_subir(cpe, archivo, data)
                falta.discard(archivo)

        if falta:
            cpe._falta = falta  # type: ignore[attr-defined]
            if falta <= permanentes:
                # SUNAT no tiene el comprobante para este RUC: no tiene sentido
                # seguir reintentando en las siguiente rondas.
                cpe._permanente = True  # type: ignore[attr-defined]
                logger.error(
                    "No encontrado en SUNAT %s-%s (RUC %s): falta %s. No se reintentará.",
                    cpe.serie,
                    cpe.numero,
                    cpe.ruc,
                    ", ".join(sorted(falta)),
                )
            else:
                logger.warning(
                    "Pendiente %s-%s (RUC %s): falta %s",
                    cpe.serie,
                    cpe.numero,
                    cpe.ruc,
                    ", ".join(sorted(falta)),
                )
            return cpe
        return None

    def _resumen(self, todos: List[Comprobante], rondas: int) -> Dict:
        ok_pdf = sum(1 for c in todos if self.storage.existe_pdf(c))
        ok_xml = sum(1 for c in todos if self.storage.existe_xml(c))
        faltantes = [c for c in todos if self._falta_algo(c)]
        return {
            "total": len(todos),
            "pdfs_descargados": ok_pdf,
            "xmls_descargados": ok_xml,
            "completos": len(todos) - len(faltantes),
            "rondas": rondas,
            "faltantes": [
                {
                    "fila": c.fila,
                    "ruc": c.ruc,
                    "tipo": c.tipo,
                    "serie": c.serie,
                    "numero": c.numero,
                    "falta": sorted(self._falta_algo(c)),
                    "motivo": getattr(c, "_motivo", None),
                }
                for c in faltantes
            ],
        }

    @staticmethod
    def _notificar(resumen: Dict):
        cuerpo = "Proceso finalizado.\n\n"
        cuerpo += f"Comprobantes leídos : {resumen['total']}\n"
        cuerpo += f"PDFs descargados    : {resumen['pdfs_descargados']}/{resumen['total']}\n"
        cuerpo += f"XMLs descargados    : {resumen['xmls_descargados']}/{resumen['total']}\n"

        faltantes = resumen["faltantes"]
        if faltantes:
            asunto = "Descarga SUNAT - Incompleta"
            cuerpo += f"\n⚠️ Quedaron {len(faltantes)} comprobantes pendientes:\n"
            for c in faltantes:
                cuerpo += (
                    f"  - Fila {c['fila']}: {c['serie']}-{c['numero']} "
                    f"(RUC {c['ruc']}) → falta {', '.join(c['falta'])}\n"
                )
        else:
            asunto = "Descarga SUNAT - Completada con éxito"

        enviar_correo(asunto, cuerpo)

    # ── ejecución principal ────────────────────────────────────────────
    def descargar_lista(self, comprobantes: List[Comprobante]) -> Dict:
        """Descarga inmediata de una lista corta de comprobantes.

        Hace una sola pasada (sin esperas entre rondas ni notificacion por
        correo), pensada para descargas puntuales solicitadas por API.
        """
        pendientes = [c for c in comprobantes if not self._comprobante_completo(c)]
        for cpe in pendientes:
            logger.info("Descarga puntual: %s", cpe)
            try:
                self._procesar_comprobante(cpe)
            except PermissionError:
                logger.warning("🔐 Token expirado, regenerando...")
                self._renovar_token()
                self._procesar_comprobante(cpe)

        return self._resumen(comprobantes, 1 if pendientes else 0)

    def run(self, comprobantes: Optional[List[Comprobante]] = None) -> Dict:
        """Ejecuta el pipeline completo (rondas + notificacion).

        Si se entrega ``comprobantes`` se procesa esa lista (solicitud JSON);
        en caso contrario se leen los comprobantes del Excel configurado.
        """
        modos = []
        if self.descargar_pdf:
            modos.append("PDF")
        if self.descargar_xml:
            modos.append("XML")
        if not modos:
            raise ValueError(
                "No hay nada que descargar: DESCARGAR_PDF y DESCARGAR_XML están desactivados."
            )

        if comprobantes is None:
            origen = f"Excel: {self.excel_path}"
            todos = leer_excel(self.excel_path)
        else:
            origen = f"Solicitud JSON: {len(comprobantes)} comprobante(s)"
            todos = list(comprobantes)
        logger.info("Modo de descarga: %s | %s", " + ".join(modos), origen)

        pendientes = [c for c in todos if not self._comprobante_completo(c)]
        logger.info(
            "Total: %s | Ya completos: %s | Pendientes: %s",
            len(todos),
            len(todos) - len(pendientes),
            len(pendientes),
        )

        ronda = 0
        if pendientes:
            espera_ronda = 0
            while pendientes and ronda < config.MAX_RONDAS_ARCHIVOS:
                ronda += 1
                if espera_ronda > 0:
                    espera = min(espera_ronda, config.ESPERA_MAX_RONDA_SEG) + random.randint(0, 15)
                    mins, segs = divmod(espera, 60)
                    logger.info("⏳ Esperando %s min %s s antes de la ronda %s...", mins, segs, ronda)
                    time.sleep(espera)

                logger.info(
                    "\n%s\nRONDA %s/%s — %s pendientes\n%s",
                    "=" * 60,
                    ronda,
                    config.MAX_RONDAS_ARCHIVOS,
                    len(pendientes),
                    "=" * 60,
                )
                nuevos_pendientes: List[Comprobante] = []
                future_to_cpe: Dict = {}

                with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
                    for cpe in pendientes:
                        future = executor.submit(self._procesar_comprobante, cpe)
                        future_to_cpe[future] = cpe
                        time.sleep(
                            random.uniform(config.PAUSA_MIN_ENTRE_CPE, config.PAUSA_MAX_ENTRE_CPE)
                        )

                    for future in as_completed(future_to_cpe):
                        cpe = future_to_cpe[future]
                        try:
                            res = future.result()
                        except PermissionError:
                            logger.warning("🔐 Token expirado, regenerando...")
                            try:
                                self._renovar_token()
                                res = self._procesar_comprobante(cpe)
                            except Exception as e:
                                logger.error("No se pudo renovar el token: %s", e)
                                res = cpe
                        except Exception as e:
                            logger.error(
                                "Error en worker para %s-%s: %s", cpe.serie, cpe.numero, e
                            )
                            res = cpe

                        if res and not getattr(res, "_permanente", False):
                            nuevos_pendientes.append(res)

                pendientes = [c for c in nuevos_pendientes if self._falta_algo(c)]
                if not pendientes:
                    logger.info("✅ Todos completados en esta ronda.")
                    break

                espera_ronda = config.ESPERA_BASE_RONDA_SEG * (
                    config.FACTOR_BACKOFF ** (ronda - 1)
                )
        else:
            logger.info("✅ Nada pendiente.")

        resumen = self._resumen(todos, ronda)
        self._notificar(resumen)
        logger.info(
            "Pipeline finalizado: %s/%s completos en %s ronda(s).",
            resumen["completos"],
            resumen["total"],
            ronda,
        )
        return resumen
