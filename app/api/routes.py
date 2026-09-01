import uuid
import os
import shutil
import json
import tempfile
from typing import Dict, Any

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

import google_auth_oauthlib.flow
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials

from app.core import config
from app.core.logging import setup_logging
from app.core.database import SessionLocal, get_db
from app.models.db_models import User, Job
from app.services.sunat_auth import obtener_token_automatico
from app.services.pipeline import DocumentPipeline
from app.services.storage import LocalStorage
from app.services.drive_storage_oauth import DriveStorageOAuth
from app.services.notifications import enviar_correo

logger = setup_logging()
router = APIRouter()

# ─── OAuth helpers (temporales, solo para el flujo de autorización) ──────
VERIFIERS_FILE = os.path.join(tempfile.gettempdir(), "sunat_oauth_verifiers.json")

def _guardar_verifier(state: str, code_verifier: str):
    data = {}
    if os.path.exists(VERIFIERS_FILE):
        with open(VERIFIERS_FILE, "r") as f:
            data = json.load(f)
    data[state] = code_verifier
    with open(VERIFIERS_FILE, "w") as f:
        json.dump(data, f)

def _obtener_verifier(state: str) -> str:
    if not os.path.exists(VERIFIERS_FILE):
        return None
    with open(VERIFIERS_FILE, "r") as f:
        data = json.load(f)
    return data.pop(state, None)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ─── Tarea en segundo plano ─────────────────────────────────────────────
def ejecutar_pipeline(job_id: str, excel_path: str):
    """
    Ejecuta el pipeline de descarga en segundo plano.
    Actualiza el estado en la base de datos y envía correo al finalizar.
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        job.status = "processing"
        db.commit()

        # Obtener credenciales del usuario
        user = db.query(User).filter(User.id == job.user_id).first()
        if not user:
            raise Exception("Usuario no encontrado")

        sunat_ruc = user.sunat_ruc or config.SUNAT_RUC
        sunat_usuario = user.sunat_usuario or config.SUNAT_USUARIO
        sunat_clave = user.sunat_clave or config.SUNAT_CLAVE
        token = obtener_token_automatico(sunat_ruc, sunat_usuario, sunat_clave)

        # Drive (si el usuario tiene token de Google)
        drive = None
        if user.google_refresh_token:
            creds = Credentials(
                None,
                refresh_token=user.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=config.GOOGLE_CLIENT_ID,
                client_secret=config.GOOGLE_CLIENT_SECRET,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
            creds.refresh(GoogleRequest())
            drive = DriveStorageOAuth(creds)

        storage = LocalStorage(config.OUTPUT_DIR)

        pipeline = DocumentPipeline(
            excel_path=excel_path,
            token=token,
            storage=storage,
            drive=drive,
            descargar_pdf=config.DESCARGAR_PDF,
            descargar_xml=config.DESCARGAR_XML,
        )
        pipeline.run()

        # Éxito
        job.status = "completed"
        job.message = "Descarga completada exitosamente."
        db.commit()

        enviar_correo(
            asunto="SUNAT - Descarga completada",
            cuerpo=(
                f"El trabajo {job_id} finalizó correctamente.\n"
                f"Archivo procesado: {job.excel_filename}\n"
                f"Los comprobantes fueron descargados en {config.OUTPUT_DIR}."
            )
        )

    except Exception as e:
        logger.error(f"Error en job {job_id}: {e}", exc_info=True)
        job = db.query(Job).filter(Job.id == job_id).first()  # refrescar
        if job:
            job.status = "failed"
            job.message = str(e)
            db.commit()
        enviar_correo(
            asunto="SUNAT - Descarga fallida",
            cuerpo=(
                f"El trabajo {job_id} falló.\n"
                f"Error: {str(e)}"
            )
        )
        try:
            os.remove(excel_path)
        except Exception:
            pass
    finally:
        db.close()


# ─── Endpoints ──────────────────────────────────────────────────────────
@router.post("/descargar")
async def iniciar_descarga(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "El archivo debe ser un Excel (.xlsx o .xls)")

    job_id = str(uuid.uuid4())
    excel_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")
    with open(excel_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Usuario fijo por ahora (luego será dinámico con autenticación)
    user_id = "default_user"
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # Crear usuario por defecto con credenciales del .env
        user = User(
            id=user_id,
            email="cliente@ejemplo.com",
            sunat_ruc=config.SUNAT_RUC,
            sunat_usuario=config.SUNAT_USUARIO,
            sunat_clave=config.SUNAT_CLAVE
        )
        db.add(user)
        db.commit()

    new_job = Job(
        id=job_id,
        user_id=user_id,
        status="pending",
        excel_filename=file.filename,
        excel_path=excel_path,
        message="Tarea encolada."
    )
    db.add(new_job)
    db.commit()

    background_tasks.add_task(ejecutar_pipeline, job_id, excel_path)
    return JSONResponse(content={"job_id": job_id, "status": "pending"})


@router.get("/estado/{job_id}")
async def obtener_estado(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return {
        "job_id": job.id,
        "status": job.status,
        "message": job.message,
        "excel_filename": job.excel_filename,
        "created_at": job.created_at
    }


@router.get("/auth/google")
async def auth_google():
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        {
            "web": {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=['https://www.googleapis.com/auth/drive.file'],
        redirect_uri=config.GOOGLE_REDIRECT_URI,
    )
    authorization_url, state = flow.authorization_url(prompt='consent')
    _guardar_verifier(state, flow.code_verifier)
    return RedirectResponse(url=authorization_url)


@router.get("/auth/google/callback")
async def auth_google_callback(code: str, state: str, db: Session = Depends(get_db)):
    code_verifier = _obtener_verifier(state)
    if not code_verifier:
        raise HTTPException(400, "Estado de autenticación no encontrado o expirado.")

    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        {
            "web": {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=['https://www.googleapis.com/auth/drive.file'],
        redirect_uri=config.GOOGLE_REDIRECT_URI,
        code_verifier=code_verifier,
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials
    refresh_token = credentials.refresh_token

    user_id = "default_user"
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, email="cliente@ejemplo.com")
        db.add(user)
    user.google_refresh_token = refresh_token
    db.commit()

    logger.info("✅ Usuario autenticado con Google Drive.")
    return {"message": "Autenticación exitosa. Ya podés cerrar esta página."}