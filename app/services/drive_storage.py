import datetime
import time
import random
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

class DriveStorage:
    def __init__(self, credentials_path: str, parent_folder_id: str = None):
        self.credentials_path = credentials_path
        self.parent_folder_id = parent_folder_id
        self.service = self._autenticar()

    def _autenticar(self):
        creds = service_account.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        return build('drive', 'v3', credentials=creds)

    def _crear_o_obtener_carpeta(self, nombre: str) -> str:
        query = f"name='{nombre}' and mimeType='application/vnd.google-apps.folder'"
        if self.parent_folder_id:
            query += f" and '{self.parent_folder_id}' in parents"
        else:
            query += " and 'root' in parents"

        resultados = self.service.files().list(q=query, fields="files(id, name)").execute()
        archivos = resultados.get('files', [])
        if archivos:
            logger.info(f"📁 Carpeta '{nombre}' ya existe en Drive.")
            return archivos[0]['id']

        metadata = {
            'name': nombre,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if self.parent_folder_id:
            metadata['parents'] = [self.parent_folder_id]

        folder = self.service.files().create(body=metadata, fields='id').execute()
        logger.info(f"📁 Carpeta '{nombre}' creada en Drive.")
        return folder['id']

    def subir_archivo(self, ruta_local: str, nombre_archivo: str, folder_id: str):
        media = MediaFileUpload(ruta_local, resumable=True)
        metadata = {
            'name': nombre_archivo,
            'parents': [folder_id]
        }
        self.service.files().create(body=metadata, media_body=media).execute()
        logger.info(f"☁️ Subido a Drive: {nombre_archivo}")

    def subir_comprobante(self, ruta_local: str, nombre_archivo: str, max_reintentos: int = 3):
        """Sube el archivo a Drive con reintentos automáticos."""
        for intento in range(1, max_reintentos + 1):
            try:
                fecha = datetime.date.today().strftime("%Y-%m-%d")
                folder_id = self._crear_o_obtener_carpeta(f"FACTURAS DEL {fecha}")
                self.subir_archivo(ruta_local, nombre_archivo, folder_id)
                return  # Éxito
            except Exception as e:
                logger.warning(f"Intento {intento}/{max_reintentos} fallido para {nombre_archivo}: {e}")
                if intento < max_reintentos:
                    time.sleep(2 ** intento + random.uniform(0, 1))
                else:
                    logger.error(f"No se pudo subir {nombre_archivo} después de {max_reintentos} intentos.")
                    raise