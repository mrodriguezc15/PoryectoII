"""
ui/chat_bot.py
Lógica del flujo conversacional automatizado.
El chatbot define qué mensaje envía el asistente y cómo procesa la respuesta del usuario.
"""
from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass, field


class State(Enum):
    """Estados del flujo conversacional."""
    GREETING         = auto()   # Saludo inicial — pide nombre
    AWAIT_NAME       = auto()   # Esperando nombre del usuario
    ASK_CONTINUE     = auto()   # ¿Desea hacer EDA?
    ASK_FORMAT       = auto()   # CSV o XLSX
    ASK_URL          = auto()   # Solicita URL del dataset (solo Google Drive)
    LOADING_DATA     = auto()   # Cargando datos (bloqueado)
    ASK_QUANT_COLS   = auto()   # Indica columnas cuantitativas
    ASK_QUAL_COLS    = auto()   # Indica columnas cualitativas
    GENERATING_PDF   = auto()   # Generando PDF (bloqueado)
    ASK_EMAIL        = auto()   # Solicita correo
    SENDING_EMAIL    = auto()   # Enviando correo (bloqueado)
    HISTORY_MENU     = auto()   # Menú de consulta de historial
    SHOW_HISTORY     = auto()   # Señal para mostrar historial en UI
    FAREWELL         = auto()   # Despedida / cierre
    DONE             = auto()   # Terminal


# Alias de estados que bloquean la entrada del usuario
BLOCKING_STATES = {State.LOADING_DATA, State.GENERATING_PDF, State.SENDING_EMAIL}


@dataclass
class ChatContext:
    """Datos acumulados durante la sesión de chat."""
    session_id: int = 0
    user_name: str = ""
    file_type: str = "csv"        # 'csv' o 'xlsx'
    dataset_url: str = ""
    quantitative_cols: list[str] = field(default_factory=list)
    qualitative_cols: list[str] = field(default_factory=list)
    available_columns: list[str] = field(default_factory=list)
    pdf_path: str = ""
    report_id: int = 0
    email: str = ""
    source_type: str = "url"   # 'url' o 'drive'
    state: State = State.GREETING


def initial_message() -> str:
    return "¡Hola! ¿Cómo estás? 😊\n¿Cómo te llamas?"


def process_input(ctx: ChatContext, user_text: str) -> tuple[list[str], bool]:
    """
    Procesa la entrada del usuario según el estado actual.

    Returns:
        (lista de mensajes del asistente, debe_cerrar_programa)
    """
    text = user_text.strip()

    # Validación global: entrada vacía (excepto estados bloqueados)
    if not text and ctx.state not in BLOCKING_STATES:
        return (["⚠️ No puedes dejar ese campo vacío. Por favor, complétalo."], False)

    # --- AWAIT_NAME ---
    if ctx.state == State.AWAIT_NAME:
        ctx.user_name = text
        ctx.state = State.ASK_CONTINUE
        return (
            [
                f"Mucho gusto, <b>{ctx.user_name}</b> 👋",
                "¿Deseas realizar un análisis exploratorio de datos?\n\nResponde <b>Sí</b> o <b>No</b>.",
            ],
            False,
        )

    # --- ASK_CONTINUE ---
    if ctx.state == State.ASK_CONTINUE:
        if _is_yes(text):
            ctx.state = State.ASK_FORMAT
            return (
                [
                    "Excelente! ¿Qué formato tiene tu dataset?\n\n"
                    "<b>1.</b> Datos medianos o pequeños con Pandas — CSV\n"
                    "<b>2.</b> Datos medianos o pequeños con Pandas — XLSX\n\n"
                    "Escribe <b>1</b> o <b>2</b>."
                ],
                False,
            )
        elif _is_no(text):
            ctx.state = State.FAREWELL
            return (["Gracias por usar nuestros servicios. 👋\n¡Hasta pronto!"], True)
        else:
            return (["Por favor responde <b>Sí</b> o <b>No</b>."], False)

    # --- ASK_FORMAT ---
    if ctx.state == State.ASK_FORMAT:
        if text in ("1", "csv"):
            ctx.file_type = "csv"
        elif text in ("2", "xlsx"):
            ctx.file_type = "xlsx"
        else:
            return (["Opción no válida. Escribe <b>1</b> para CSV o <b>2</b> para XLSX."], False)
        ctx.source_type = "drive"
        ctx.state = State.ASK_URL
        return (
            [
                "📁 Google Drive — Pasos para compartir tu archivo:\n\n"
                "1. Abre el archivo en Google Drive\n"
                "2. Clic derecho → Compartir\n"
                "3. Cambia el acceso a 'Cualquiera con el enlace'\n"
                "4. Copia el enlace y pégalo aquí:"
            ],
            False,
        )

    # --- ASK_URL ---
    if ctx.state == State.ASK_URL:
        if not text.startswith(("http://", "https://")):
            return (["\u26a0\ufe0f El link no es v\u00e1lido. Debe empezar con https://"], False)
        if "drive.google.com" not in text and "docs.google.com" not in text:
            return (
                [
                    "\u26a0\ufe0f Solo se aceptan links de Google Drive.\n\n"
                    "Aseg\u00farate de copiar el link desde Google Drive \u2192 Compartir."
                ],
                False,
            )
        ctx.dataset_url = text
        ctx.state = State.LOADING_DATA
        return (["Un momento por favor, cargando los datos desde Google Drive..."], False)

    # --- ASK_QUANT_COLS ---
    if ctx.state == State.ASK_QUANT_COLS:
        cols = _parse_columns(text, ctx.available_columns)
        if not cols:
            return (
                [
                    "⚠️ No reconocí ninguna columna válida. "
                    f"Las columnas disponibles son:\n<b>{', '.join(ctx.available_columns)}</b>\n\n"
                    "Escríbelas separadas por coma."
                ],
                False,
            )
        ctx.quantitative_cols = cols
        ctx.state = State.ASK_QUAL_COLS
        remaining = [c for c in ctx.available_columns if c not in cols]
        remaining_txt = f"\n\nColumnas restantes: <b>{', '.join(remaining)}</b>" if remaining else ""
        return (
            [f"✅ Columnas cuantitativas registradas: <b>{', '.join(cols)}</b>{remaining_txt}",
             "Ahora, ¿cuáles son las columnas <b>cualitativas</b>?\nEscríbelas separadas por coma, o escribe <b>ninguna</b>."],
            False,
        )

    # --- ASK_QUAL_COLS ---
    if ctx.state == State.ASK_QUAL_COLS:
        if text.lower() in ("ninguna", "none", "no", "n/a", "-"):
            ctx.qualitative_cols = []
        else:
            cols = _parse_columns(text, ctx.available_columns)
            ctx.qualitative_cols = cols
        ctx.state = State.GENERATING_PDF
        return (
            [
                f"✅ Columnas cualitativas: <b>{', '.join(ctx.qualitative_cols) or 'Ninguna'}</b>",
                "📊 Generando informe en PDF... Por favor espera unos momentos.",
            ],
            False,
        )

    # --- ASK_EMAIL ---
    if ctx.state == State.ASK_EMAIL:
        if "@" not in text or "." not in text.split("@")[-1]:
            return ([f"⚠️ El correo '<b>{text}</b>' no parece válido. Por favor verifica e intenta de nuevo."], False)
        ctx.email = text
        ctx.state = State.SENDING_EMAIL
        return ([f"⏳ Un momento por favor, enviando el informe a <b>{ctx.email}</b>..."], False)

    # --- HISTORY_MENU ---
    if ctx.state == State.HISTORY_MENU:
        return _handle_history_menu(ctx, text)

    return (["Estado inesperado. Por favor reinicia la aplicación."], False)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _is_yes(text: str) -> bool:
    return text.lower() in ("si", "sí", "s", "yes", "y", "claro", "ok", "1")


def _is_no(text: str) -> bool:
    return text.lower() in ("no", "n", "nope", "2")


def _parse_columns(text: str, available: list[str]) -> list[str]:
    """
    Parsea columnas escritas por el usuario (separadas por coma).
    Hace matching case-insensitive y tolerante a espacios.
    """
    candidates = [c.strip() for c in text.split(",") if c.strip()]
    available_lower = {c.lower(): c for c in available}
    matched = []
    for candidate in candidates:
        exact = available_lower.get(candidate.lower())
        if exact and exact not in matched:
            matched.append(exact)
    return matched


def _handle_history_menu(ctx: ChatContext, text: str) -> tuple[list[str], bool]:
    """Maneja el submenú de historial."""
    t = text.lower().strip()

    # Cerrar aplicación
    if t in ("salir", "exit", "no", "n", "cerrar", "2"):
        ctx.state = State.DONE
        return ([f"Muchas gracias por usar nuestros servicios, <b>{ctx.user_name}</b>. 👋"], True)

    # Ver historial
    if t in ("si", "sí", "s", "yes", "y", "historial", "ver", "1"):
        ctx.state = State.SHOW_HISTORY
        return (["SHOW_HISTORY"], False)  # Señal especial — la UI la intercepta

    return (
        [
            "Por favor escribe:\n"
            "<b>1</b> o <b>historial</b> para ver el historial\n"
            "<b>2</b> o <b>salir</b> para cerrar"
        ],
        False,
    )