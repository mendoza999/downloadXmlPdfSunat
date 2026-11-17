import datetime
import logging
import random
import time

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)


class DriveStorage:
    def __init__(self, credentials_path: str, parent_folder_id: str = None):
        self.credentials_path = credentials_path
        self.parent_folder_id = parent_folder_id
        self.service = self._autenticar()
        self._carpetas: dict[str, str] = {}

    def _autenticar(self):
        creds = service_account.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        return build("drive", "v3", credentials=creds)

    def _crear_o_obtener_carpeta(self, nombre: str) -> str:
        if nombre in self._carpetas:
            return self._carpetas[nombre]

        nombre_escapado = nombre.replace("\\", "\\\\").replace("'", "\\'")
        query = (
            f"name='{nombre_escapado}' and mimeType='application/vnd.google-apps.folder' "
            "and trashed=false"
        )
        if self.parent_folder_id:
            query += f" and '{self.parent_folder_id}' in parents"
        else:
            query += " and 'root' in parents"

        resultados = self.service.files().list(q=query, fields="files(id, name)").execute()
        archivos = resultados.get("files", [])
        if archivos:
            logger.info("📁 Carpeta '%s' ya existe en Drive.", nombre)
            self._carpetas[nombre] = archivos[0]["id"]
            return archivos[0]["id"]

        metadata = {"name": nombre, "mimeType": "application/vnd.google-apps.folder"}
        if self.parent_folder_id:
            metadata["parents"] = [self.parent_folder_id]

        folder = self.service.files().create(body=metadata, fields="id").execute()
        logger.info("📁 Carpeta '%s' creada en Drive.", nombre)
        self._carpetas[nombre] = folder["id"]
        return folder["id"]

    def _existe_archivo(self, nombre_archivo: str, folder_id: str) -> bool:
        nombre_escapado = nombre_archivo.replace("\\", "\\\\").replace("'", "\\'")
        query = (
            f"name='{nombre_escapado}' and '{folder_id}' in parents and trashed=false"
        )
        resultados = (
            self.service.files()
            .list(q=query, fields="files(id)", pageSize=1)
            .execute()
        )
        return bool(resultados.get("files"))

    def subir_archivo(self, ruta_local: str, nombre_archivo: str, folder_id: str):
        media = MediaFileUpload(ruta_local, resumable=True)
        metadata = {"name": nombre_archivo, "parents": [folder_id]}
        self.service.files().create(body=metadata, media_body=media).execute()
        logger.info("☁️ Subido a Drive: %s", nombre_archivo)

    def subir_comprobante(self, ruta_local: str, nombre_archivo: str, max_reintentos: int = 3):
        """Sube el archivo a Drive con reintentos automáticos."""
        for intento in range(1, max_reintentos + 1):
            try:
                fecha = datetime.date.today().strftime("%Y-%m-%d")
                folder_id = self._crear_o_obtener_carpeta(f"FACTURAS DEL {fecha}")
                if self._existe_archivo(nombre_archivo, folder_id):
                    logger.info("☁️ %s ya existe en Drive, se omite.", nombre_archivo)
                    return
                self.subir_archivo(ruta_local, nombre_archivo, folder_id)
                return  # Éxito
            except Exception as e:
                logger.warning(
                    "Intento %s/%s fallido para %s: %s", intento, max_reintentos, nombre_archivo, e
                )
                if intento < max_reintentos:
                    time.sleep(2 ** intento + random.uniform(0, 1))
                else:
                    logger.error(
                        "No se pudo subir %s después de %s intentos.",
                        nombre_archivo,
                        max_reintentos,
                    )
                    raise
