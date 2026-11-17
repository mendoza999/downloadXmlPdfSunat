import io
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import urlencode

import google_auth_oauthlib.flow
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import config
from app.core.database import SessionLocal, get_db
from app.core.logging import setup_logging
from app.models.comprobante import crear_comprobante
from app.models.db_models import Job, User
from app.services.drive_storage_oauth import DriveStorageOAuth
from app.services.notifications import enviar_correo
from app.services.pipeline import DocumentPipeline
from app.services.storage import LocalStorage
from app.services.sunat_auth import obtener_token_con_reintentos

logger = setup_logging()
router = APIRouter()

USER_ID_DEFAULT = "default_user"


# ─── OAuth helpers (temporales, solo para el flujo de autorización) ──────
VERIFIERS_FILE = os.path.join(tempfile.gettempdir(), "sunat_oauth_verifiers.json")


def _guardar_verifier(state: str, code_verifier: str):
    data = {}
    if os.path.exists(VERIFIERS_FILE):
        with open(VERIFIERS_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    data[state] = code_verifier
    with open(VERIFIERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _obtener_verifier(state: str) -> Optional[str]:
    if not os.path.exists(VERIFIERS_FILE):
        return None
    with open(VERIFIERS_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return None
    return data.pop(state, None)


def _crear_drive_oauth(user: User) -> Optional[DriveStorageOAuth]:
    """Construye el cliente de Drive del usuario, sin romper el job si falla."""
    if not user.google_refresh_token:
        return None
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        logger.warning("El usuario tiene token de Google pero faltan GOOGLE_CLIENT_ID/SECRET.")
        return None
    try:
        creds = Credentials(
            None,
            refresh_token=user.google_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=config.GOOGLE_CLIENT_ID,
            client_secret=config.GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        creds.refresh(GoogleRequest())
        return DriveStorageOAuth(creds, parent_folder_id=config.GOOGLE_DRIVE_FOLDER_ID)
    except Exception as exc:
        logger.warning("No se pudo autenticar en Google Drive, se omite la subida: %s", exc)
        return None


# ─── Tarea en segundo plano ─────────────────────────────────────────────
def _obtener_usuario_default(db: Session) -> User:
    """Devuelve (o crea) el usuario fijo usado mientras no hay autenticacion."""
    user = db.query(User).filter(User.id == USER_ID_DEFAULT).first()
    if not user:
        user = User(
            id=USER_ID_DEFAULT,
            email="cliente@ejemplo.com",
            sunat_ruc=config.SUNAT_RUC,
            sunat_usuario=config.SUNAT_USUARIO,
            sunat_clave=config.SUNAT_CLAVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _credenciales_sunat(user: User) -> Tuple[str, str, str]:
    ruc = user.sunat_ruc or config.SUNAT_RUC
    usuario = user.sunat_usuario or config.SUNAT_USUARIO
    clave = user.sunat_clave or config.SUNAT_CLAVE
    if not all((ruc, usuario, clave)):
        raise RuntimeError(
            "Faltan credenciales SUNAT. Configúrelas en el archivo .env"
        )
    return ruc, usuario, clave


def ejecutar_pipeline(job_id: str, excel_path: str):
    """Ejecuta el pipeline de descarga y actualiza el estado del job."""
    db = SessionLocal()
    job: Optional[Job] = None
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error("Job %s no encontrado en la base de datos.", job_id)
            return
        job.status = "processing"
        job.message = "Descargando comprobantes..."
        db.commit()

        user = db.query(User).filter(User.id == job.user_id).first()
        if not user:
            raise RuntimeError("Usuario no encontrado")

        sunat_ruc, sunat_usuario, sunat_clave = _credenciales_sunat(user)
        token = obtener_token_con_reintentos(sunat_ruc, sunat_usuario, sunat_clave)

        drive = _crear_drive_oauth(user)
        storage = LocalStorage(config.OUTPUT_DIR)

        pipeline = DocumentPipeline(
            excel_path=excel_path,
            token=token,
            storage=storage,
            drive=drive,
            descargar_pdf=config.DESCARGAR_PDF,
            descargar_xml=config.DESCARGAR_XML,
            sunat_credentials=(sunat_ruc, sunat_usuario, sunat_clave),
        )
        resumen = pipeline.run()

        faltantes = resumen.get("faltantes", [])
        job.status = "completed"
        job.details = resumen
        if faltantes:
            job.message = (
                f"Descarga finalizada con {len(faltantes)} comprobante(s) pendiente(s) "
                f"de {resumen.get('total', 0)}."
            )
        else:
            job.message = "Descarga completada exitosamente."
        db.commit()

    except Exception as e:
        logger.error("Error en job %s: %s", job_id, e, exc_info=True)
        if job is None:
            job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.message = str(e)
            db.commit()
        enviar_correo(
            asunto="SUNAT - Descarga fallida",
            cuerpo=f"El trabajo {job_id} falló.\nError: {e}",
        )
    finally:
        db.close()
        # El Excel subido ya no se necesita después del procesamiento
        try:
            os.remove(excel_path)
        except OSError:
            pass


# ─── Endpoints ──────────────────────────────────────────────────────────
@router.post("/descargar", tags=["descargas"])
async def iniciar_descarga(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    nombre_original = os.path.basename(file.filename or "").strip()
    if not nombre_original.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "El archivo debe ser un Excel (.xlsx o .xls)")

    nombre_seguro = re.sub(r"[^A-Za-z0-9._-]", "_", nombre_original)
    job_id = str(uuid.uuid4())
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    excel_path = os.path.join(config.UPLOAD_DIR, f"{job_id}_{nombre_seguro}")

    with open(excel_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    tamano_mb = os.path.getsize(excel_path) / (1024 * 1024)
    if tamano_mb > config.MAX_UPLOAD_MB:
        os.remove(excel_path)
        raise HTTPException(
            413, f"El archivo supera el tamaño máximo de {config.MAX_UPLOAD_MB} MB"
        )
    if tamano_mb == 0:
        os.remove(excel_path)
        raise HTTPException(400, "El archivo Excel está vacío")

    # Usuario fijo por ahora (luego será dinámico con autenticación)
    user = _obtener_usuario_default(db)

    new_job = Job(
        id=job_id,
        user_id=user.id,
        status="pending",
        excel_filename=nombre_original,
        excel_path=excel_path,
        message="Tarea encolada.",
    )
    db.add(new_job)
    db.commit()

    background_tasks.add_task(ejecutar_pipeline, job_id, excel_path)
    return JSONResponse(content={"job_id": job_id, "status": "pending"})


@router.get("/estado/{job_id}", tags=["descargas"])
async def obtener_estado(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return {
        "job_id": job.id,
        "status": job.status,
        "message": job.message,
        "excel_filename": job.excel_filename,
        "created_at": job.created_at,
        "details": job.details,
    }


@router.get("/jobs", tags=["descargas"])
async def listar_jobs(limit: int = 20, db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(max(1, min(limit, 100))).all()
    return [
        {
            "job_id": j.id,
            "status": j.status,
            "message": j.message,
            "excel_filename": j.excel_filename,
            "created_at": j.created_at,
        }
        for j in jobs
    ]


class DescargaComprobanteRequest(BaseModel):
    tipo_doc: Union[str, int] = Field(
        ..., description="Tipo de documento SUNAT (01, 03, 07, 08, 09)"
    )
    serie: Union[str, int] = Field(
        ..., description="Serie del comprobante, por ejemplo F001"
    )
    numero: Union[str, int] = Field(..., description="Numero correlativo del comprobante")
    ruc_emisor: Union[str, int] = Field(..., description="RUC del emisor (11 digitos)")


CAMPOS_COMPROBANTE = ("tipo_doc", "serie", "numero", "ruc_emisor")


async def _leer_parametros_comprobante(request: Request) -> Dict[str, Any]:
    """Obtiene los parametros desde query string, JSON o formulario.

    Asi el endpoint funciona igual con ``?tipo_doc=...``, con un cuerpo JSON o
    con ``application/x-www-form-urlencoded`` / ``multipart/form-data``.
    """
    datos: Dict[str, Any] = {
        clave: valor
        for clave, valor in request.query_params.items()
        if clave in CAMPOS_COMPROBANTE and valor.strip()
    }

    tipo_contenido = request.headers.get("content-type", "").lower()
    if "application/json" in tipo_contenido:
        try:
            cuerpo = await request.json()
        except Exception:
            cuerpo = None
        if isinstance(cuerpo, dict):
            datos.update(
                {
                    clave: valor
                    for clave, valor in cuerpo.items()
                    if clave in CAMPOS_COMPROBANTE
                    and valor is not None
                    and str(valor).strip()
                }
            )
    elif "form" in tipo_contenido:
        formulario = await request.form()
        datos.update(
            {
                clave: valor
                for clave, valor in formulario.items()
                if clave in CAMPOS_COMPROBANTE
                and isinstance(valor, str)
                and valor.strip()
            }
        )

    return datos


def _url_archivo(cpe, formato: str) -> str:
    query = urlencode(
        {
            "tipo_doc": cpe.tipo,
            "serie": cpe.serie,
            "numero": cpe.numero,
            "ruc_emisor": cpe.ruc,
            "formato": formato,
        }
    )
    return f"/comprobante/archivo?{query}"


def _ruta_visible(path: str) -> str:
    """Ruta relativa a la raiz del proyecto (evita exponer rutas absolutas)."""
    try:
        return os.path.relpath(path, config.BASE_DIR).replace(os.sep, "/")
    except ValueError:
        # En Windows, OUTPUT_DIR podria estar en otra unidad
        return path.replace(os.sep, "/")


@router.post(
    "/descargar/comprobante",
    tags=["descargas"],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": DescargaComprobanteRequest.model_json_schema()
                },
                "application/x-www-form-urlencoded": {
                    "schema": DescargaComprobanteRequest.model_json_schema()
                },
            },
        }
    },
)
def descargar_comprobante(
    datos: Dict[str, Any] = Depends(_leer_parametros_comprobante),
    db: Session = Depends(get_db),
):
    """Descarga puntual (sincrona) del PDF y XML de un comprobante.

    Acepta los datos como JSON, formulario o query string. Obtiene el token
    SUNAT, descarga los archivos habilitados (DESCARGAR_PDF / DESCARGAR_XML),
    los guarda en disco y, si el usuario tiene Google Drive vinculado, los sube
    a la nube.
    """
    faltan = [campo for campo in CAMPOS_COMPROBANTE if not datos.get(campo)]
    if faltan:
        raise HTTPException(
            422,
            "Faltan parametros: "
            + ", ".join(faltan)
            + ". Envie tipo_doc, serie, numero y ruc_emisor (JSON, formulario o query).",
        )

    try:
        cpe = crear_comprobante(
            datos["tipo_doc"],
            datos["serie"],
            datos["numero"],
            datos["ruc_emisor"],
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    user = _obtener_usuario_default(db)
    storage = LocalStorage(config.OUTPUT_DIR)
    ya_completo = (not config.DESCARGAR_PDF or storage.existe_pdf(cpe)) and (
        not config.DESCARGAR_XML or storage.existe_xml(cpe)
    )

    if ya_completo:
        logger.info("Comprobante ya descargado, se reutiliza: %s", cpe)
        resumen = {"faltantes": []}
    else:
        try:
            sunat_ruc, sunat_usuario, sunat_clave = _credenciales_sunat(user)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))

        try:
            token = obtener_token_con_reintentos(sunat_ruc, sunat_usuario, sunat_clave)
            pipeline = DocumentPipeline(
                excel_path=None,
                token=token,
                storage=storage,
                drive=_crear_drive_oauth(user),
                descargar_pdf=config.DESCARGAR_PDF,
                descargar_xml=config.DESCARGAR_XML,
                sunat_credentials=(sunat_ruc, sunat_usuario, sunat_clave),
            )
            resumen = pipeline.descargar_lista([cpe])
        except Exception as exc:
            logger.error(
                "Error al descargar %s-%s (RUC %s): %s",
                cpe.serie,
                cpe.numero,
                cpe.ruc,
                exc,
                exc_info=True,
            )
            raise HTTPException(502, f"No se pudo descargar el comprobante: {exc}")

    archivos = []
    if config.DESCARGAR_PDF and storage.existe_pdf(cpe):
        archivos.append(
            {
                "tipo": "pdf",
                "nombre": f"{storage.nombre_base(cpe)}.pdf",
                "ruta": _ruta_visible(storage.path_pdf(cpe)),
                "descarga_url": _url_archivo(cpe, "pdf"),
            }
        )
    if config.DESCARGAR_XML and storage.existe_xml(cpe):
        archivos.append(
            {
                "tipo": "xml",
                "nombre": f"{storage.nombre_base(cpe)}.xml",
                "ruta": _ruta_visible(storage.path_xml(cpe)),
                "descarga_url": _url_archivo(cpe, "xml"),
            }
        )

    faltantes = sorted(resumen["faltantes"][0]["falta"]) if resumen["faltantes"] else []
    if not archivos:
        raise HTTPException(
            404,
            "No se pudo descargar el comprobante. Verifique los datos y que exista "
            f"en SUNAT. Faltan: {', '.join(faltantes) or 'pdf, xml'}",
        )

    return {
        "comprobante": {
            "tipo_doc": cpe.tipo,
            "serie": cpe.serie,
            "numero": cpe.numero,
            "ruc_emisor": cpe.ruc,
        },
        "completo": not faltantes,
        "archivos": archivos,
        "faltantes": faltantes,
        "descarga_zip_url": _url_archivo(cpe, "zip"),
    }


@router.get("/comprobante/archivo", tags=["descargas"])
def descargar_archivo_comprobante(
    tipo_doc: str,
    serie: str,
    numero: str,
    ruc_emisor: str,
    formato: str = "pdf",
):
    """Entrega un archivo ya descargado (pdf, xml o zip con ambos).

    Pensado para usarse con los enlaces ``descarga_url`` / ``descarga_zip_url``
    que devuelve ``POST /descargar/comprobante``.
    """
    try:
        cpe = crear_comprobante(tipo_doc, serie, numero, ruc_emisor)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    formato = formato.strip().lower()
    storage = LocalStorage(config.OUTPUT_DIR)
    base = storage.nombre_base(cpe)

    if formato in {"pdf", "xml"}:
        path = storage.path_pdf(cpe) if formato == "pdf" else storage.path_xml(cpe)
        if not os.path.exists(path):
            raise HTTPException(
                404,
                "El archivo no existe. Ejecute primero POST /descargar/comprobante.",
            )
        media_type = "application/pdf" if formato == "pdf" else "application/xml"
        return FileResponse(path, media_type=media_type, filename=f"{base}.{formato}")

    if formato == "zip":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for ext, path in (("pdf", storage.path_pdf(cpe)), ("xml", storage.path_xml(cpe))):
                if os.path.exists(path):
                    zf.write(path, arcname=f"{base}.{ext}")
        if buffer.tell() == 0:
            raise HTTPException(
                404,
                "No hay archivos para comprimir. Ejecute primero "
                "POST /descargar/comprobante.",
            )
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{base}.zip"'},
        )

    raise HTTPException(400, "Formato invalido. Use: pdf, xml o zip")


def _config_oauth() -> Dict[str, Any]:
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        raise HTTPException(
            503,
            "Google OAuth no está configurado (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).",
        )
    return {
        "web": {
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


@router.get("/auth/google", tags=["google"])
async def auth_google():
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        _config_oauth(),
        scopes=["https://www.googleapis.com/auth/drive.file"],
        redirect_uri=config.GOOGLE_REDIRECT_URI,
    )
    authorization_url, state = flow.authorization_url(prompt="consent")
    _guardar_verifier(state, flow.code_verifier)
    return RedirectResponse(url=authorization_url)


@router.get("/auth/google/callback", tags=["google"])
async def auth_google_callback(code: str, state: str, db: Session = Depends(get_db)):
    code_verifier = _obtener_verifier(state)
    if not code_verifier:
        raise HTTPException(400, "Estado de autenticación no encontrado o expirado.")

    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        _config_oauth(),
        scopes=["https://www.googleapis.com/auth/drive.file"],
        redirect_uri=config.GOOGLE_REDIRECT_URI,
        code_verifier=code_verifier,
    )
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise HTTPException(400, f"No se pudo completar la autenticación con Google: {exc}")

    refresh_token = flow.credentials.refresh_token

    user = _obtener_usuario_default(db)
    if refresh_token:
        user.google_refresh_token = refresh_token
        db.commit()

    logger.info("✅ Usuario autenticado con Google Drive.")
    return {"message": "Autenticación exitosa. Ya podés cerrar esta página."}
