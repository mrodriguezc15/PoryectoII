# 📊 Proyecto M — Asistente de Análisis Exploratorio de Datos

Aplicación de escritorio con interfaz estilo **WhatsApp** que guía al usuario a través del análisis exploratorio de datos (EDA), genera un informe PDF profesional y lo envía por correo. Historial almacenado en **PostgreSQL en Railway**.

---

## 🗂️ Estructura del Proyecto

```
proyecto_M/
├── .env                    ← Tus credenciales 
├── requirements.txt        ← Dependencias Python
├── main.py                 ← Punto de entrada
├── config/
│   └── settings.py         ← Carga variables de entorno
├── database/
│   ├── connection.py       ← Pool de conexiones PostgreSQL
│   └── models.py           ← DDL + CRUD (sessions, messages, reports)
├── core/
│   ├── data_loader.py      ← Descarga CSV/XLSX desde URL
│   ├── eda.py              ← Motor de análisis exploratorio
│   └── pdf_generator.py    ← Generador de informe PDF profesional
├── services/
│   └── email_sender.py     ← Envío de correo con PDF adjunto (Gmail)
└── ui/
    ├── chat_bot.py         ← Máquina de estados del flujo conversacional
    └── chat_window.py      ← Interfaz gráfica estilo WhatsApp (CustomTkinter)
```

---

## ⚙️ Configuración Paso a Paso

### 1. Requisitos
- Python 3.11 o superior
- pip actualizado

### 2. activar entorno virtual 
- python -m venv env 
- env\Scripts\activate


### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Ejecutar la aplicación
```bash
python main.py
```

---

## 🗄️ Esquema de Base de Datos

```sql
-- Una sesión por conversación
sessions (id, user_name, started_at, ended_at, status)

-- Mensajes del chat
messages (id, session_id → sessions, sender, content, sent_at)

-- Reportes PDF generados
reports (id, session_id → sessions, dataset_url, recipient_email, pdf_path, email_sent, created_at)
```

Las tablas se crean automáticamente al iniciar la aplicación.

---

## 💬 Flujo de la Conversación

```
Saludo → Nombre → ¿Hacer EDA? → Formato (CSV/XLSX) → URL del dataset
  → Cargar datos* → Columnas cuantitativas → Columnas cualitativas
  → Generar PDF* → Email → Enviar correo* → Historial → Cierre
```
*\* = proceso bloqueante (input deshabilitado mientras procesa)*

---

## 📦 Dependencias Principales

| Paquete | Uso |
|---------|-----|
| `customtkinter` | UI moderna estilo WhatsApp |
| `pandas` | Análisis de datos |
| `openpyxl` | Lectura de archivos XLSX |
| `matplotlib` / `seaborn` | Gráficos estadísticos |
| `reportlab` | Generación de PDF profesional |
| `psycopg2-binary` | Conexión a PostgreSQL |
| `python-dotenv` | Variables de entorno |
| `requests` | Descarga de datasets desde URL |

---
