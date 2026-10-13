"""
database/models.py
Define el esquema normalizado y las operaciones CRUD.

Tablas:
  sessions        → Una sesión por conversación
  messages        → Mensajes individuales del chat
  reports         → Reportes PDF generados (metadata + ruta)
"""
from __future__ import annotations
import datetime
from database.connection import Database


# ---------------------------------------------------------------------------
# DDL – Creación de tablas (idempotente con IF NOT EXISTS)
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id          SERIAL PRIMARY KEY,
    user_name   VARCHAR(200)    NOT NULL,
    started_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ,
    status      VARCHAR(20)     NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'aborted'))
);

CREATE TABLE IF NOT EXISTS messages (
    id          SERIAL PRIMARY KEY,
    session_id  INTEGER         NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sender      VARCHAR(20)     NOT NULL CHECK (sender IN ('user', 'assistant')),
    content     TEXT            NOT NULL,
    sent_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reports (
    id              SERIAL PRIMARY KEY,
    session_id      INTEGER         NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    dataset_url     TEXT            NOT NULL,
    recipient_email VARCHAR(255)    NOT NULL,
    pdf_path        TEXT,
    email_sent      BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Índices de acceso frecuente
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_reports_session  ON reports(session_id);
"""


def create_tables() -> None:
    """Ejecuta el DDL para crear (o verificar) todas las tablas."""
    conn = Database.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    finally:
        Database.release_connection(conn)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def create_session(user_name: str) -> int:
    """Crea una nueva sesión y retorna su ID."""
    conn = Database.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (user_name) VALUES (%s) RETURNING id;",
                (user_name,),
            )
            session_id: int = cur.fetchone()[0]
        conn.commit()
        return session_id
    finally:
        Database.release_connection(conn)


def close_session(session_id: int, status: str = "completed") -> None:
    conn = Database.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET ended_at = NOW(), status = %s WHERE id = %s;",
                (status, session_id),
            )
        conn.commit()
    finally:
        Database.release_connection(conn)


def get_sessions() -> list[dict]:
    """Retorna todas las sesiones ordenadas por fecha descendente."""
    conn = Database.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_name, started_at, ended_at, status
                FROM sessions
                ORDER BY started_at DESC;
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "user_name": r[1],
                "started_at": r[2],
                "ended_at": r[3],
                "status": r[4],
            }
            for r in rows
        ]
    finally:
        Database.release_connection(conn)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def save_message(session_id: int, sender: str, content: str) -> None:
    conn = Database.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (session_id, sender, content) VALUES (%s, %s, %s);",
                (session_id, sender, content),
            )
        conn.commit()
    finally:
        Database.release_connection(conn)


def get_messages(session_id: int) -> list[dict]:
    conn = Database.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sender, content, sent_at FROM messages WHERE session_id = %s ORDER BY sent_at;",
                (session_id,),
            )
            rows = cur.fetchall()
        return [{"sender": r[0], "content": r[1], "sent_at": r[2]} for r in rows]
    finally:
        Database.release_connection(conn)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def create_report(session_id: int, dataset_url: str, recipient_email: str) -> int:
    conn = Database.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reports (session_id, dataset_url, recipient_email)
                VALUES (%s, %s, %s) RETURNING id;
                """,
                (session_id, dataset_url, recipient_email),
            )
            report_id: int = cur.fetchone()[0]
        conn.commit()
        return report_id
    finally:
        Database.release_connection(conn)


def update_report(report_id: int, pdf_path: str, email_sent: bool) -> None:
    conn = Database.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE reports SET pdf_path = %s, email_sent = %s WHERE id = %s;",
                (pdf_path, email_sent, report_id),
            )
        conn.commit()
    finally:
        Database.release_connection(conn)


def get_reports() -> list[dict]:
    conn = Database.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, s.user_name, r.dataset_url, r.recipient_email,
                       r.email_sent, r.created_at
                FROM reports r
                JOIN sessions s ON s.id = r.session_id
                ORDER BY r.created_at DESC;
                """
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "user_name": r[1],
                "dataset_url": r[2],
                "recipient_email": r[3],
                "email_sent": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]
    finally:
        Database.release_connection(conn)
