import smtplib
import logging
from email.message import EmailMessage
from app.core import config

logger = logging.getLogger(__name__)

def enviar_correo(asunto: str, cuerpo: str):
    """Envía un correo con el resumen de la descarga."""
    try:
        msg = EmailMessage()
        msg.set_content(cuerpo)
        msg['Subject'] = asunto
        msg['From'] = config.EMAIL_USER
        msg['To'] = config.EMAIL_DESTINATARIO

        with smtplib.SMTP_SSL(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT) as smtp:
            smtp.login(config.EMAIL_USER, config.EMAIL_PASSWORD)
            smtp.send_message(msg)
        logger.info(f"📧 Correo enviado a {config.EMAIL_DESTINATARIO}")
    except Exception as e:
        logger.error(f"Error enviando correo: {e}")