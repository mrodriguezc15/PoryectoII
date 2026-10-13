"""
config/settings.py
Carga y valida las variables de entorno del proyecto.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    GMAIL_USER: str = os.getenv("GMAIL_USER", "")
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")
    REPORT_AUTHOR: str = os.getenv("REPORT_AUTHOR", "Sebastian Romero")

    @classmethod
    def validate(cls) -> list[str]:
        """Retorna lista de variables faltantes."""
        missing = []
        if not cls.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not cls.GMAIL_USER:
            missing.append("GMAIL_USER")
        if not cls.GMAIL_APP_PASSWORD:
            missing.append("GMAIL_APP_PASSWORD")
        return missing


settings = Settings()
