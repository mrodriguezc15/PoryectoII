"""
services/email_sender.py
Envía el informe PDF al correo del usuario vía Gmail SMTP.
"""
from __future__ import annotations
import os
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.settings import settings


def send_report(
    recipient_email: str,
    user_name: str,
    pdf_path: str,
) -> None:
    """
    Envía el informe PDF por correo.

    Args:
        recipient_email: Correo destino.
        user_name: Nombre del usuario para personalizar el cuerpo.
        pdf_path: Ruta al archivo PDF generado.

    Raises:
        RuntimeError: Si el envío falla.
    """
    if not os.path.exists(pdf_path):
        raise RuntimeError(f"No se encontró el PDF en: {pdf_path}")

    msg = MIMEMultipart("mixed")
    msg["From"]    = settings.GMAIL_USER
    msg["To"]      = recipient_email
    msg["Subject"] = "📊 Su Informe de Análisis Exploratorio de Datos"

    # Cuerpo HTML
    html_body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #202124; line-height: 1.6;">
      <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #1A73E8; padding: 20px; border-radius: 8px 8px 0 0;">
          <h2 style="color: white; margin: 0;">📊 Informe de Análisis de Datos</h2>
        </div>
        <div style="background: #F8F9FA; padding: 24px; border: 1px solid #DADCE0; border-top: none; border-radius: 0 0 8px 8px;">
          <p>Estimado/a <strong>{user_name}</strong>,</p>
          <p>Adjunto encontrará el informe completo de análisis exploratorio de datos
          generado a partir del dataset que proporcionó.</p>
          <p>El informe incluye:</p>
          <ul>
            <li>Estructura y calidad del dataset</li>
            <li>Estadísticas descriptivas</li>
            <li>Distribuciones y gráficos</li>
            <li>Tablas de frecuencia y contingencia</li>
            <li>Mapa de correlación</li>
            <li>Interpretación y conclusiones</li>
          </ul>
          <hr style="border: none; border-top: 1px solid #DADCE0; margin: 20px 0;">
          <p style="font-size: 12px; color: #5F6368;">
            Este correo fue generado automáticamente por el sistema de análisis de datos.<br>
            Elaborado por: <strong>{settings.REPORT_AUTHOR}</strong>
          </p>
        </div>
      </div>
    </body></html>
    """
    msg.attach(MIMEText(html_body, "html"))

    # Adjuntar PDF
    with open(pdf_path, "rb") as f:
        attachment = MIMEBase("application", "pdf")
        attachment.set_payload(f.read())
        encoders.encode_base64(attachment)
        filename = os.path.basename(pdf_path)
        attachment.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(attachment)

    # Enviar con TLS
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
            server.sendmail(settings.GMAIL_USER, recipient_email, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Autenticación de Gmail fallida. Verifica GMAIL_USER y GMAIL_APP_PASSWORD en .env.\n"
            "Recuerda usar una 'Contraseña de aplicación', no tu contraseña normal de Gmail."
        )
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"Error al enviar el correo: {exc}")
