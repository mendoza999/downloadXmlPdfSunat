import random
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Set, Dict, Tuple

from app.core import config
from app.models.comprobante import Comprobante, leer_excel
from app.services.sunat_api import SunatAPIClient
from app.services.storage import LocalStorage
from app.services.drive_storage import DriveStorage
from app.services.notifications import enviar_correo

logger = logging.getLogger(__name__)


class DocumentPipeline:
    def __init__(
        self,
        excel_path: str,
        token: str,
        storage: LocalStorage,
        drive: DriveStorage = None,
        descargar_pdf: bool = True,
        descargar_xml: bool = True,
    ):
        self.excel_path = excel_path
        self.client = SunatAPIClient(token)
        self.storage = storage
        self.drive = drive
        self.descargar_pdf = descargar_pdf
        self.descargar_xml = descargar_xml

    def _falta_algo(self, cpe: Comprobante) -> Set[str]:
        falta = set()
        if self.descargar_pdf and not self.storage.existe_pdf(cpe):
            falta.add("pdf")
        if self.descargar_xml and not self.storage.existe_xml(cpe):
            falta.add("xml")
        return falta

    def _comprobante_completo(self, cpe: Comprobante) -> bool:
        return not bool(self._falta_algo(cpe))

    def _descargar_archivo_con_reintento(
        self, cpe: Comprobante, sufijo: str, etiqueta: str
    ) -> Optional[bytes]:
        for intento in range(1 + config.MAX_REINTENTOS_INMEDIATOS):
            try:
                if sufijo == "01":
                    data = self.client.fetch_pdf(cpe.ruc, cpe.tipo, cpe.serie, cpe.numero)
                else:
                    data = self.client.fetch_xml(cpe.ruc, cpe.tipo, cpe.serie, cpe.numero)
            except PermissionError:
                raise
            except Exception as e:
                logger.error(f"[{etiqueta}] Excepción: {e}")
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
            nombre_archivo = f"{cpe.nombre_base}.{tipo}"
            ruta_local = self.storage.path_pdf(cpe) if tipo == "pdf" else self.storage.path_xml(cpe)
            try:
                self.drive.subir_comprobante(ruta_local, nombre_archivo)
            except Exception as e:
                logger.error(f"No se pudo subir {nombre_archivo} a Drive: {e}")

    def _procesar_comprobante(self, cpe: Comprobante) -> Optional[Comprobante]:
        if self._comprobante_completo(cpe):
            return None

        falta = self._falta_algo(cpe)
        for archivo in sorted(falta):
            time.sleep(random.uniform(config.PAUSA_MIN_ENTRE_ARCHIVOS, config.PAUSA_MAX_ENTRE_ARCHIVOS))
            sufijo = "01" if archivo == "pdf" else "02"
            data = self._descargar_archivo_con_reintento(cpe, sufijo, archivo.upper())
            if data:
                self._guardar_y_subir(cpe, archivo, data)
                falta.discard(archivo)

        if falta:
            cpe._falta = falta  # type: ignore
            return cpe
        return None

    def run(self):
        modo = []
        if self.descargar_pdf:
            modo.append("PDF")
        if self.descargar_xml:
            modo.append("XML")
        logger.info(f"Modo de descarga: {' + '.join(modo)}")

        todos = leer_excel(self.excel_path)
        pendientes = [c for c in todos if not self._comprobante_completo(c)]
        logger.info(
            f"Total: {len(todos)} | Ya completos: {len(todos) - len(pendientes)} | "
            f"Pendientes: {len(pendientes)}"
        )

        if not pendientes:
            logger.info("✅ Nada pendiente.")
            return

        ronda = 0
        espera_ronda = 0
        while pendientes and ronda < config.MAX_RONDAS_ARCHIVOS:
            ronda += 1
            if espera_ronda > 0:
                espera = min(espera_ronda, config.ESPERA_MAX_RONDA_SEG) + random.randint(0, 15)
                mins, segs = divmod(espera, 60)
                logger.info(f"\n⏳ Esperando {mins} min {segs} s antes de la ronda {ronda}...")
                time.sleep(espera)

            logger.info(
                f"\n{'='*60}\nRONDA {ronda}/{config.MAX_RONDAS_ARCHIVOS} — "
                f"{len(pendientes)} pendientes\n{'='*60}"
            )
            nuevos_pendientes: List[Comprobante] = []
            # Mapeo future -> cpe para manejar errores de token
            future_to_cpe: Dict = {}

            with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
                for cpe in pendientes:
                    future = executor.submit(self._procesar_comprobante, cpe)
                    future_to_cpe[future] = cpe
                    time.sleep(random.uniform(config.PAUSA_MIN_ENTRE_CPE, config.PAUSA_MAX_ENTRE_CPE))

                for future in as_completed(future_to_cpe):
                    cpe = future_to_cpe[future]
                    try:
                        res = future.result()
                    except PermissionError:
                        logger.warning("🔐 Token expirado, regenerando...")
                        from app.services.sunat_auth import obtener_token_automatico

                        nuevo = obtener_token_automatico(
                            config.SUNAT_RUC, config.SUNAT_USUARIO, config.SUNAT_CLAVE
                        )
                        self.client.actualizar_token(nuevo)
                        # Reintentamos el mismo comprobante inmediatamente
                        res = self._procesar_comprobante(cpe)
                        if res:
                            nuevos_pendientes.append(res)
                        continue
                    except Exception as e:
                        logger.error(f"Error en worker para {cpe.serie}-{cpe.numero}: {e}")
                        # Lo tratamos como pendiente
                        res = cpe

                    if res:
                        nuevos_pendientes.append(res)

            pendientes = [c for c in nuevos_pendientes if self._falta_algo(c)]
            if not pendientes:
                logger.info("✅ Todos completados en esta ronda.")
                break

            espera_ronda = config.ESPERA_BASE_RONDA_SEG * (config.FACTOR_BACKOFF ** (ronda - 1))

        # ── Resumen y notificación ────────────────────────────────────────
        ok_pdf = sum(1 for c in todos if self.storage.existe_pdf(c))
        ok_xml = sum(1 for c in todos if self.storage.existe_xml(c))
        faltantes = [c for c in todos if self._falta_algo(c)]

        cuerpo = "Proceso finalizado.\n\n"
        cuerpo += f"PDFs descargados : {ok_pdf}/{len(todos)}\n"
        cuerpo += f"XMLs descargados : {ok_xml}/{len(todos)}\n"

        if faltantes:
            asunto = "Descarga SUNAT - Incompleta"
            cuerpo += f"\n⚠️ Quedaron {len(faltantes)} comprobantes pendientes:\n"
            for c in faltantes:
                cuerpo += f"  - {c.serie}-{c.numero} (RUC {c.ruc}) → {self._falta_algo(c)}\n"
        else:
            asunto = "Descarga SUNAT - Completada con éxito"

        enviar_correo(asunto, cuerpo)
        logger.info("Pipeline finalizado.")