import logging
import smtplib
from email.message import EmailMessage

from app.core import config

logger = logging.getLogger(__name__)


def enviar_correo(asunto: str, cuerpo: str) -> bool:
    """Envía un correo con el resumen de la descarga.

    Si las notificaciones no están configuradas se omite el envío sin
    generar errores en el flujo principal.
    """
    servidor = config.EMAIL_SMTP_SERVER
    puerto = config.EMAIL_SMTP_PORT
    usuario = config.EMAIL_USER
    clave = config.EMAIL_PASSWORD
    destinatarios = [
        d.strip()
        for d in config.EMAIL_DESTINATARIO.replace(";", ",").split(",")
        if d.strip()
    ]

    if not (servidor and usuario and clave and destinatarios):
        logger.info("Notificaciones por correo no configuradas; se omite el envío.")
        return False

    msg = EmailMessage()
    msg.set_content(cuerpo)
    msg["Subject"] = asunto
    msg["From"] = usuario
    msg["To"] = ", ".join(destinatarios)

    try:
        if puerto == 465:
            smtp = smtplib.SMTP_SSL(servidor, puerto, timeout=30)
        else:
            smtp = smtplib.SMTP(servidor, puerto, timeout=30)
            smtp.starttls()
        with smtp:
            smtp.login(usuario, clave)
            smtp.send_message(msg)
        logger.info("📧 Correo enviado a %s", ", ".join(destinatarios))
        return True
    except Exception as e:
        logger.error("Error enviando correo: %s", e)
        return False
