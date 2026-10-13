"""
core/data_loader.py
Descarga y carga datasets CSV o XLSX desde una URL.

Fuentes soportadas:
  - URL directa (cualquier servidor HTTP/HTTPS)
  - Google Drive  (enlaces /file/d/... o /open?id=...)
  - Dropbox       (enlaces compartidos dl=0 → dl=1)

Google Drive maneja automáticamente:
  - Archivos pequeños  → descarga directa
  - Archivos grandes   → bypass del aviso de virus-scan de Google
"""
from __future__ import annotations
import io
import re
from typing import Callable
import requests
import pandas as pd

_CONNECT_TIMEOUT = 15    # segundos para establecer conexión
_READ_TIMEOUT    = 180   # segundos para leer
_CHUNK_SIZE      = 1024 * 128  # 128 KB por chunk

# Headers que simulan un navegador real (evita bloqueos de algunos servidores)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Resolución de URLs
# ---------------------------------------------------------------------------

def extract_drive_file_id(url: str) -> str | None:
    """Extrae el file ID de cualquier formato de URL de Google Drive."""
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",   # /file/d/ID/view
        r"/d/([a-zA-Z0-9_-]+)",         # /d/ID
        r"[?&]id=([a-zA-Z0-9_-]+)",     # ?id=ID  o  open?id=ID
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_google_drive_url(url: str) -> bool:
    return "drive.google.com" in url or "docs.google.com" in url


def _resolve_dropbox_url(url: str) -> str:
    if "dropbox.com" in url:
        # Forzar descarga directa
        url = re.sub(r"[?&]dl=0", "", url)
        url = url + ("&dl=1" if "?" in url else "?dl=1")
    return url


# ---------------------------------------------------------------------------
# Descarga desde Google Drive
# ---------------------------------------------------------------------------

def _download_google_drive(
    file_id: str,
    notify: Callable[[str], None],
) -> bytes:
    """
    Descarga un archivo de Google Drive manejando el aviso de virus-scan
    que Google muestra para archivos > ~25 MB.
    """
    session = requests.Session()
    session.headers.update(_HEADERS)

    base_url = "https://drive.google.com/uc"
    params = {"export": "download", "id": file_id}

    notify("Conectando a Google Drive...")

    # Primera solicitud
    response = session.get(
        base_url, params=params,
        timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
        stream=True,
    )
    response.raise_for_status()

    # Google Drive devuelve HTML con un formulario de confirmación
    # para archivos grandes (aviso de virus scan)
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        notify("Confirmando descarga en Google Drive...")
        # Extraer token de confirmación del HTML
        html = response.text
        token_match = re.search(r'name="uuid"\s+value="([^"]+)"', html)
        if not token_match:
            # Intentar formato alternativo más nuevo
            token_match = re.search(r'"downloadUrl":"([^"]+)"', html)
            if token_match:
                download_url = token_match.group(1).replace("\\u003d", "=").replace("\\u0026", "&")
                response = session.get(
                    download_url,
                    timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
                    stream=True,
                )
            else:
                # Fallback: intentar con confirm=t
                response = session.get(
                    base_url,
                    params={**params, "confirm": "t"},
                    timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
                    stream=True,
                )
        else:
            uuid = token_match.group(1)
            response = session.get(
                "https://drive.usercontent.google.com/download",
                params={"id": file_id, "export": "download",
                        "authuser": "0", "confirm": "t", "uuid": uuid},
                timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
                stream=True,
            )
        response.raise_for_status()

    return _stream_download(response, notify)


# ---------------------------------------------------------------------------
# Descarga genérica con streaming
# ---------------------------------------------------------------------------

def _stream_download(
    response: requests.Response,
    notify: Callable[[str], None],
) -> bytes:
    """Lee la respuesta en chunks mostrando progreso."""
    total = response.headers.get("Content-Length")
    total_mb = int(total) / (1024 * 1024) if total else None

    if total_mb:
        notify(f"Descargando {total_mb:.1f} MB desde el servidor...")
    else:
        notify("Descargando datos...")

    chunks = []
    downloaded = 0

    for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
        if chunk:
            chunks.append(chunk)
            downloaded += len(chunk)
            dl_mb = downloaded / (1024 * 1024)
            if total_mb:
                pct = min(downloaded / int(total) * 100, 100)
                notify(f"Descargando... {dl_mb:.1f}/{total_mb:.1f} MB ({pct:.0f}%)")
            else:
                notify(f"Descargando... {dl_mb:.1f} MB recibidos")

    return b"".join(chunks)


# ---------------------------------------------------------------------------
# Función principal pública
# ---------------------------------------------------------------------------

def load_dataset(
    url: str,
    file_type: str = "csv",
    progress_callback: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """
    Descarga y carga un dataset desde la URL dada.

    Args:
        url: Enlace directo, Google Drive o Dropbox.
        file_type: 'csv' o 'xlsx'.
        progress_callback: función que recibe strings de progreso en tiempo real.

    Returns:
        DataFrame con los datos cargados.
    """
    file_type = file_type.lower().strip()
    if file_type not in ("csv", "xlsx"):
        raise ValueError(f"Tipo no soportado: '{file_type}'. Use 'csv' o 'xlsx'.")

    url = url.strip()

    def notify(msg: str):
        if progress_callback:
            progress_callback(msg)

    # --- Google Drive ---
    if is_google_drive_url(url):
        file_id = extract_drive_file_id(url)
        if not file_id:
            raise RuntimeError(
                "No se pudo extraer el ID del archivo de Google Drive.\n"
                "Asegúrate de compartir el archivo como 'Cualquiera con el enlace'."
            )
        try:
            raw = _download_google_drive(file_id, notify)
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(
                f"Error al descargar desde Google Drive (HTTP {exc.response.status_code}).\n"
                "Verifica que el archivo sea público: Compartir → 'Cualquiera con el enlace'."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Error de conexión con Google Drive: {exc}") from exc

    # --- URL directa / Dropbox ---
    else:
        if "dropbox.com" in url:
            url = _resolve_dropbox_url(url)

        notify("Conectando al servidor...")
        try:
            response = requests.get(
                url,
                headers=_HEADERS,
                timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
                allow_redirects=True,
                stream=True,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectTimeout:
            raise RuntimeError("No se pudo conectar. Verifica la URL e intenta de nuevo.")
        except requests.exceptions.ReadTimeout:
            raise RuntimeError("La descarga tardó demasiado. Intenta con Google Drive para mayor velocidad.")
        except requests.exceptions.HTTPError:
            raise RuntimeError(
                f"Error HTTP {response.status_code}. "
                "Verifica que el enlace sea público y directo al archivo."
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"No se pudo acceder a la URL: {exc}")

        raw = _stream_download(response, notify)

    # --- Leer con Pandas ---
    notify("Procesando archivo con Pandas...")
    content = io.BytesIO(raw)

    try:
        if file_type == "csv":
            df = pd.read_csv(content, sep=None, engine="python", encoding_errors="replace")
        else:
            df = pd.read_excel(content, engine="openpyxl")
    except Exception as exc:
        raise RuntimeError(f"No se pudo leer el archivo como {file_type.upper()}: {exc}")

    if df.empty:
        raise RuntimeError("El dataset está vacío. Verifica el archivo.")

    notify(f"¡Listo! {df.shape[0]:,} filas × {df.shape[1]} columnas cargadas.")
    return df