"""
main.py
Punto de entrada de la aplicación.
Verifica configuración y lanza la ventana principal.
"""
import sys
import os

# Asegurar que el directorio raíz esté en el PYTHONPATH
sys.path.insert(0, os.path.dirname(__file__))

from config.settings import settings


def main():
    # Verificar variables de entorno críticas
    missing = settings.validate()
    if missing:
        print("=" * 60)
        print("⚠️  CONFIGURACIÓN INCOMPLETA")
        print("=" * 60)
        print(f"Faltan las siguientes variables en el archivo .env:\n")
        for var in missing:
            print(f"  ✗ {var}")
        print("\nCopia el archivo .env.example como .env y completa los valores.")
        print("=" * 60)

    from ui.chat_window import ChatWindow
    app = ChatWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
