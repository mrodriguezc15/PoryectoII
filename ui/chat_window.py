"""
ui/chat_window.py
Interfaz estilo WhatsApp con CustomTkinter.
"""
from __future__ import annotations
import sys
import re
import threading
import time
import datetime
import tkinter as tk
import customtkinter as ctk

from ui.chat_bot import (
    ChatContext, State, BLOCKING_STATES,
    initial_message, process_input,
)
import database.models as db
from database.connection import Database
from core.data_loader import load_dataset
from core.eda import run_eda
from core.pdf_generator import generate_pdf
from services.email_sender import send_report

# Colores
BG_MAIN      = "#ECE5DD"
BG_PANEL     = "#128C7E"
BG_ASSISTANT = "#FFFFFF"
BG_USER      = "#DCF8C6"
BG_INPUT     = "#F0F0F0"
TEXT_DARK    = "#303030"
TEXT_LIGHT   = "#FFFFFF"
TEXT_TIME    = "#999999"
ACCENT       = "#25D366"
ACCENT_DARK  = "#128C7E"
SEND_BTN_BG  = "#25D366"
TYPING_COLOR = "#888888"

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")


def _strip_html(text: str) -> str:
    text = re.sub(r"<b>(.*?)</b>", r"\1", text)
    text = re.sub(r"<i>(.*?)</i>",  r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


class ChatWindow(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Asistente de Análisis de Datos")
        self.geometry("520x740")
        self.minsize(380, 500)
        self.configure(fg_color=BG_MAIN)
        self.ctx = ChatContext()
        self._msg_queue: list[tuple[str, float]] = []
        self._queue_running = False
        self._build_ui()
        self.bind("<Configure>", self._on_resize)
        self._bubble_widgets: list = []
        self._start_session()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        self.header = ctk.CTkFrame(self, fg_color=BG_PANEL, height=64, corner_radius=0)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        av = tk.Canvas(self.header, width=44, height=44, bg=BG_PANEL, highlightthickness=0)
        av.pack(side="left", padx=(14, 8), pady=10)
        av.create_oval(2, 2, 42, 42, fill=ACCENT, outline="")
        av.create_text(22, 22, text="🤖", font=("Segoe UI Emoji", 18))

        info = ctk.CTkFrame(self.header, fg_color="transparent")
        info.pack(side="left", fill="y", pady=8)
        ctk.CTkLabel(info, text="Asistente EDA",
                     font=ctk.CTkFont("Helvetica", 16, weight="bold"),
                     text_color=TEXT_LIGHT).pack(anchor="w")
        self.status_label = ctk.CTkLabel(info, text="en línea",
                                          font=ctk.CTkFont("Helvetica", 11),
                                          text_color="#B2DFDB")
        self.status_label.pack(anchor="w")

        ctk.CTkButton(
            self.header, text="📋 Historial", width=95, height=30,
            fg_color="#0E6E63", hover_color="#0B5950",
            text_color=TEXT_LIGHT, font=ctk.CTkFont("Helvetica", 11),
            corner_radius=6, command=self._show_history,
        ).pack(side="right", padx=14, pady=17)

        # Área de mensajes
        self.msg_frame = ctk.CTkScrollableFrame(
            self, fg_color=BG_MAIN, corner_radius=0)
        self.msg_frame.pack(fill="both", expand=True)

        # Indicador de escritura
        self.typing_frame = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
        self.typing_label = ctk.CTkLabel(
            self.typing_frame, text="● ● ●",
            font=ctk.CTkFont("Helvetica", 12), text_color=TYPING_COLOR)

        # Barra de entrada
        input_bar = ctk.CTkFrame(self, fg_color=BG_INPUT, height=68, corner_radius=0)
        input_bar.pack(fill="x", side="bottom")
        input_bar.pack_propagate(False)

        self.text_input = tk.Text(
            input_bar, height=1,
            font=("Helvetica", 13),
            fg=TEXT_DARK, bg="#FFFFFF",
            insertbackground=TEXT_DARK,
            selectforeground=TEXT_LIGHT,
            selectbackground=ACCENT_DARK,
            relief="flat", bd=0, wrap="word",
            padx=10, pady=8,
            highlightthickness=1,
            highlightbackground="#DDDDDD",
            highlightcolor=ACCENT,
        )
        self.text_input.pack(side="left", fill="x", expand=True, padx=(10, 6), pady=13)
        self.text_input.bind("<Return>",       self._on_enter)
        self.text_input.bind("<Shift-Return>", lambda e: None)

        self.send_btn = ctk.CTkButton(
            input_bar, text="➤", width=44, height=44,
            corner_radius=22, fg_color=SEND_BTN_BG, hover_color=ACCENT_DARK,
            text_color=TEXT_LIGHT, font=ctk.CTkFont("Helvetica", 18, weight="bold"),
            command=self._send_message,
        )
        self.send_btn.pack(side="right", padx=(0, 10), pady=12)

    # ── Responsivo ────────────────────────────────────────────────────────────

    def _on_resize(self, event):
        if event.widget is not self:
            return
        w = event.width
        max_chars = max(20, int(w * 0.055))   # chars por línea aprox
        for item in self._bubble_widgets:
            try:
                txt, bg = item
                if txt.winfo_exists():
                    txt.configure(width=max_chars)
                    txt.update_idletasks()
                    lines = int(txt.index("end-1c").split(".")[0])
                    txt.configure(height=max(1, lines))
            except Exception:
                pass

    # ── Burbujas ──────────────────────────────────────────────────────────────

    def _add_user_message(self, text: str):
        self._add_bubble(text, sender="user")

    def _add_assistant_message(self, text: str):
        clean = _strip_html(text)
        self._add_bubble(clean, sender="assistant")
        self._save_message("assistant", clean)

    def _add_bubble(self, text: str, sender: str):
        is_user = sender == "user"
        bg      = BG_USER if is_user else BG_ASSISTANT
        side    = "right" if is_user else "left"
        anchor  = "e" if is_user else "w"
        now     = datetime.datetime.now().strftime("%H:%M")
        tick    = " ✓✓" if is_user else ""

        # Fila — fill="x" para asistente, solo anchor para usuario
        row = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
        if is_user:
            row.pack(anchor="e", padx=6, pady=2, fill="x")
        else:
            row.pack(anchor="w", padx=6, pady=2, fill="x")

        # Burbuja compacta al contenido con margen al lado opuesto
        bubble = ctk.CTkFrame(row, fg_color=bg, corner_radius=12)
        if is_user:
            bubble.pack(side="right", anchor="ne", padx=(200, 8), pady=0)
        else:
            bubble.pack(side="left", anchor="nw", padx=(8, 200), pady=0)

        # ── tk.Text readonly: permite seleccionar y copiar con Ctrl+C ──────
        txt = tk.Text(
            bubble,
            font=("Helvetica", 12),
            fg=TEXT_DARK,
            bg=bg,
            relief="flat", bd=0,
            wrap="word",
            cursor="arrow",          # cursor normal, no de edición
            padx=10, pady=6,
            highlightthickness=0,
            exportselection=True,    # permite copiar con Ctrl+C al portapapeles
            selectbackground=ACCENT_DARK,
            selectforeground=TEXT_LIGHT,
            state="normal",
        )
        txt.insert("1.0", text)
        txt.configure(state="disabled")   # readonly tras insertar

        # Calcular alto exacto según líneas
        txt.update_idletasks()
        lines = int(txt.index("end-1c").split(".")[0])
        txt.configure(height=max(1, lines))
        txt.pack(padx=(0, 0), pady=(6, 0), anchor="w")

        # Guardar para resize
        self._bubble_widgets.append((txt, bg))

        # Hora
        ctk.CTkLabel(
            bubble, text=f"{now}{tick}",
            font=ctk.CTkFont("Helvetica", 9),
            text_color=TEXT_TIME,
        ).pack(padx=10, pady=(2, 6), anchor="e")

        # Habilitar selección aunque sea disabled (solo lectura, no escritura)
        def _allow_select(e):
            txt.configure(state="normal")
            txt.after(10, lambda: txt.configure(state="disabled"))
        txt.bind("<Button-1>", _allow_select)
        txt.bind("<B1-Motion>", _allow_select)
        txt.bind("<Shift-Button-1>", _allow_select)

        # Menú clic derecho
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="📋 Copiar selección",
                         command=lambda: self._copy_selection(txt))
        menu.add_command(label="📋 Copiar todo",
                         command=lambda t=text: (
                             self.clipboard_clear(), self.clipboard_append(t)))
        txt.bind("<Button-3>", lambda e, m=menu: m.tk_popup(e.x_root, e.y_root))

        self._scroll_bottom()

    def _copy_selection(self, txt: tk.Text):
        try:
            sel = txt.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.clipboard_clear()
            self.clipboard_append(sel)
        except tk.TclError:
            pass

    def _add_system_message(self, text: str):
        ctk.CTkLabel(
            self.msg_frame, text=text,
            font=ctk.CTkFont("Helvetica", 10),
            text_color=TYPING_COLOR, fg_color="#EEEEEE",
            corner_radius=8, wraplength=340,
        ).pack(pady=4, padx=40)
        self._scroll_bottom()

    # ── Typing indicator ──────────────────────────────────────────────────────

    def _show_typing_then(self, message: str, delay: float = 0.5):
        self._msg_queue.append((message, delay))
        if not self._queue_running:
            self._queue_running = True
            threading.Thread(target=self._process_queue, daemon=True).start()

    def _process_queue(self):
        while self._msg_queue:
            message, delay = self._msg_queue.pop(0)
            self._post_to_main(self._show_typing_indicator)
            time.sleep(delay)
            self._post_to_main(self._hide_typing_indicator)
            self._post_to_main(lambda m=message: self._add_assistant_message(m))
            time.sleep(0.1)
        self._queue_running = False

    def _show_typing_indicator(self):
        self.typing_frame.pack(fill="x", padx=8, pady=2, anchor="w")
        self.typing_label.pack(side="left", padx=12, pady=6)
        self._scroll_bottom()
        self._animate_typing()

    def _hide_typing_indicator(self):
        self.typing_frame.pack_forget()

    def _animate_typing(self, step=0):
        dots = ["● ● ●", "○ ● ●", "○ ○ ●", "○ ○ ○"]
        try:
            if self.typing_frame.winfo_ismapped():
                self.typing_label.configure(text=dots[step % len(dots)])
                self.after(300, lambda: self._animate_typing(step + 1))
        except Exception:
            pass

    # ── Burbuja de progreso ───────────────────────────────────────────────────

    def _create_progress_bubble(self):
        self._progress_row = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
        self._progress_row.pack(fill="x", padx=6, pady=2)
        bubble = ctk.CTkFrame(self._progress_row, fg_color=BG_ASSISTANT, corner_radius=12)
        bubble.pack(side="left", anchor="w", padx=4)
        self._progress_label = ctk.CTkLabel(
            bubble, text="⏳ Conectando a Google Drive...",
            font=ctk.CTkFont("Helvetica", 12),
            text_color="#666666", wraplength=320)
        self._progress_label.pack(padx=12, pady=10)
        self._scroll_bottom()

    def _update_progress_bubble(self, msg: str):
        try:
            if hasattr(self, "_progress_label") and self._progress_label.winfo_exists():
                self._progress_label.configure(text=f"⏳ {msg}")
                self._scroll_bottom()
        except Exception:
            pass

    def _remove_progress_bubble(self):
        try:
            if hasattr(self, "_progress_row") and self._progress_row.winfo_exists():
                self._progress_row.destroy()
        except Exception:
            pass

    # ── Sesión ────────────────────────────────────────────────────────────────

    def _start_session(self):
        try:
            Database.init()
            db.create_tables()
        except Exception as exc:
            self._add_system_message(f"⚠️ Sin BD: {exc}")
        self.ctx.state = State.AWAIT_NAME
        self._show_typing_then(initial_message(), delay=0.8)

    # ── Input ─────────────────────────────────────────────────────────────────

    def _on_enter(self, event):
        if not (event.state & 0x0001):
            self._send_message()
            return "break"

    def _send_message(self):
        if self._is_blocked():
            return
        raw = self.text_input.get("1.0", "end-1c").strip()
        self.text_input.delete("1.0", "end")
        if not raw:
            self.text_input.configure(bg="#FFE0E0")
            self.after(400, lambda: self.text_input.configure(bg="#FFFFFF"))
            self._add_assistant_message("⚠️ No puedes enviar un mensaje vacío.")
            return
        self._add_user_message(raw)
        self._save_message("user", raw)
        self._process_state(raw)

    def _process_state(self, user_text: str):
        responses, should_close = process_input(self.ctx, user_text)
        for msg in responses:
            if msg == "SHOW_HISTORY":
                self.after(400, self._show_history)
                self.ctx.state = State.HISTORY_MENU
                self._show_typing_then(
                    "Abriendo historial... Escribe salir para cerrar.", delay=0.3)
            else:
                self._show_typing_then(msg, delay=0.5)

        if self.ctx.state == State.LOADING_DATA:
            self._run_in_thread(self._load_data)
        elif self.ctx.state == State.GENERATING_PDF:
            self._run_in_thread(self._generate_pdf_thread)
        elif self.ctx.state == State.SENDING_EMAIL:
            self._run_in_thread(self._send_email_thread)

        if should_close:
            self.after(3000, self._close_app)

    # ── Hilos ────────────────────────────────────────────────────────────────

    def _run_in_thread(self, target):
        self._set_blocked(True)
        threading.Thread(target=target, daemon=True).start()

    def _load_data(self):
        self._post_to_main(self._create_progress_bubble)

        def _on_progress(msg: str):
            self._post_to_main(lambda m=msg: self._update_progress_bubble(m))

        try:
            df = load_dataset(self.ctx.dataset_url, self.ctx.file_type,
                              progress_callback=_on_progress)
            self.ctx.available_columns = list(df.columns)
            self._df = df
            try:
                self.ctx.session_id = db.create_session(self.ctx.user_name)
                db.save_message(self.ctx.session_id, "user", self.ctx.dataset_url)
            except Exception:
                pass
            cols_str = ", ".join(df.columns[:20])
            suffix = f"... y {len(df.columns)-20} más" if len(df.columns) > 20 else ""

            def _done():
                self._remove_progress_bubble()
                self._add_assistant_message("✅ Conjunto de datos cargado correctamente.")
                self._add_assistant_message(
                    f"📋 El dataset tiene {df.shape[0]:,} filas y {df.shape[1]} columnas.\n\n"
                    f"Columnas: {cols_str}{suffix}")
                self._add_assistant_message(
                    "¿Cuáles son las columnas cuantitativas (numéricas)?\n"
                    "Escríbelas separadas por coma.")
                self._set_state(State.ASK_QUANT_COLS)
                self._set_blocked(False)
            self._post_to_main(_done)
        except Exception as exc:
            err = str(exc)
            def _fail():
                self._remove_progress_bubble()
                self._add_assistant_message(
                    f"❌ Error al cargar:\n{err}\n\nVerifica que el archivo sea público.")
                self._set_state(State.ASK_URL)
                self._set_blocked(False)
            self._post_to_main(_fail)

    def _generate_pdf_thread(self):
        try:
            result = run_eda(self._df, self.ctx.quantitative_cols, self.ctx.qualitative_cols)
            pdf_path = generate_pdf(result, self.ctx.user_name, self.ctx.dataset_url)
            self.ctx.pdf_path = pdf_path
            try:
                self.ctx.report_id = db.create_report(
                    self.ctx.session_id, self.ctx.dataset_url, "")
            except Exception:
                pass
            def _done():
                self._add_assistant_message("✅ Informe generado exitosamente. 📄")
                self._add_assistant_message(
                    f"Por favor indique su correo, {self.ctx.user_name}, para enviarle el informe.")
                self._set_state(State.ASK_EMAIL)
                self._set_blocked(False)
            self._post_to_main(_done)
        except Exception as exc:
            err = str(exc)
            def _fail():
                self._add_assistant_message(f"❌ Error al generar PDF:\n{err}")
                self._set_state(State.ASK_QUAL_COLS)
                self._set_blocked(False)
            self._post_to_main(_fail)

    def _send_email_thread(self):
        try:
            send_report(self.ctx.email, self.ctx.user_name, self.ctx.pdf_path)
            try:
                db.update_report(self.ctx.report_id, self.ctx.pdf_path, True)
                db.close_session(self.ctx.session_id, "completed")
                db.save_message(self.ctx.session_id, "user", self.ctx.email)
            except Exception:
                pass
            def _done():
                self._add_assistant_message(
                    f"✅ Informe enviado a {self.ctx.email} correctamente. 📧")
                self._add_assistant_message(
                    f"Muchas gracias por usar nuestros servicios, {self.ctx.user_name}. 🙏\n\n"
                    "Escribe historial para ver tus sesiones, o salir para cerrar.")
                self._set_state(State.HISTORY_MENU)
                self._set_blocked(False)
            self._post_to_main(_done)
        except Exception as exc:
            err = str(exc)
            def _fail():
                self._add_assistant_message(f"❌ Error al enviar correo:\n{err}")
                self._set_state(State.ASK_EMAIL)
                self._set_blocked(False)
            self._post_to_main(_fail)

    # ── Historial ─────────────────────────────────────────────────────────────

    def _show_history(self):
        win = ctk.CTkToplevel(self)
        win.title("Historial de Sesiones")
        win.geometry("640x520")
        win.grab_set()
        ctk.CTkLabel(win, text="Historial de Conversaciones",
                     font=ctk.CTkFont("Helvetica", 16, weight="bold"),
                     text_color=ACCENT_DARK).pack(pady=(16, 4))
        tabs = ctk.CTkTabview(win, fg_color="#F8F9FA")
        tabs.pack(fill="both", expand=True, padx=12, pady=8)
        tabs.add("Sesiones")
        tabs.add("Reportes")
        self._populate_history_tab(tabs.tab("Sesiones"), "sessions")
        self._populate_history_tab(tabs.tab("Reportes"), "reports")

    def _populate_history_tab(self, parent, kind: str):
        try:
            if kind == "sessions":
                rows = db.get_sessions()
                headers = ["ID", "Usuario", "Inicio", "Estado"]
                col_widths = [40, 160, 150, 80]
                data = [[str(r["id"]), r["user_name"],
                         r["started_at"].strftime("%d/%m/%Y %H:%M") if r["started_at"] else "",
                         r["status"]] for r in rows]
            else:
                rows = db.get_reports()
                headers = ["ID", "Usuario", "Email", "Enviado", "Fecha"]
                col_widths = [40, 120, 190, 70, 130]
                data = [[str(r["id"]), r["user_name"], r["recipient_email"],
                         "✅" if r["email_sent"] else "❌",
                         r["created_at"].strftime("%d/%m/%Y %H:%M") if r["created_at"] else ""]
                        for r in rows]
            if not data:
                ctk.CTkLabel(parent, text="Sin registros aún.",
                             text_color=TYPING_COLOR).pack(pady=20)
                return
            scroll = ctk.CTkScrollableFrame(parent, fg_color="#FFFFFF")
            scroll.pack(fill="both", expand=True, padx=4, pady=4)
            for ci, h in enumerate(headers):
                ctk.CTkLabel(scroll, text=h,
                             font=ctk.CTkFont("Helvetica", 11, weight="bold"),
                             text_color=TEXT_LIGHT, fg_color=ACCENT_DARK,
                             width=col_widths[ci], height=28, corner_radius=0,
                             ).grid(row=0, column=ci, padx=1, pady=1, sticky="nsew")
            for ri, row in enumerate(data):
                bg = "#FFFFFF" if ri % 2 == 0 else "#F1F3F4"
                for ci, val in enumerate(row):
                    ctk.CTkLabel(scroll, text=val,
                                 font=ctk.CTkFont("Helvetica", 10),
                                 text_color=TEXT_DARK, fg_color=bg,
                                 width=col_widths[ci], height=26, corner_radius=0,
                                 ).grid(row=ri+1, column=ci, padx=1, pady=1, sticky="nsew")
        except Exception as exc:
            ctk.CTkLabel(parent, text=f"Error: {exc}", text_color="red").pack(pady=10)

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _scroll_bottom(self):
        self.after(60, lambda: self.msg_frame._parent_canvas.yview_moveto(1.0))

    def _is_blocked(self) -> bool:
        return self.ctx.state in BLOCKING_STATES

    def _set_blocked(self, blocked: bool):
        self.send_btn.configure(state="disabled" if blocked else "normal")
        self.text_input.configure(state=tk.DISABLED if blocked else tk.NORMAL)
        if not blocked:
            self.text_input.configure(fg=TEXT_DARK, bg="#FFFFFF",
                                       insertbackground=TEXT_DARK)
        self.status_label.configure(
            text="procesando..." if blocked else "en línea")

    def _set_state(self, state: State):
        self.ctx.state = state

    def _post_to_main(self, fn):
        self.after(0, fn)

    def _save_message(self, sender: str, content: str):
        if self.ctx.session_id:
            try:
                db.save_message(self.ctx.session_id, sender, content)
            except Exception:
                pass

    def _close_app(self):
        try:
            Database.close_all()
        except Exception:
            pass
        self.destroy()
        sys.exit(0)