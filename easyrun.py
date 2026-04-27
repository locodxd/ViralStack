"""
EasyRun — Visual launcher for the ViralStack short-form automation pipeline.

Run:  python easyrun.py
"""
import asyncio
import logging
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
from pathlib import Path

# ── ensure project root is on sys.path ──────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Colors ──────────────────────────────────────────────────
BG           = "#1a1a2e"
BG_CARD      = "#16213e"
BG_LOG       = "#0f0f1a"
FG           = "#e0e0e0"
FG_DIM       = "#888899"
FG_SUCCESS   = "#00e676"
FG_WARNING   = "#ffab00"
FG_ERROR     = "#ff5252"
FG_INFO      = "#40c4ff"
ACCENT_TERROR   = "#b71c1c"
ACCENT_HISTORIA = "#1565c0"
ACCENT_DINERO   = "#2e7d32"
ACCENT_HOVER_T  = "#d32f2f"
ACCENT_HOVER_H  = "#1e88e5"
ACCENT_HOVER_D  = "#388e3c"
BTN_FG          = "#ffffff"

ACCOUNT_COLORS = [
    (ACCENT_TERROR, ACCENT_HOVER_T),
    (ACCENT_HISTORIA, ACCENT_HOVER_H),
    (ACCENT_DINERO, ACCENT_HOVER_D),
    ("#6a4c93", "#7b5faf"),
    ("#006d77", "#168994"),
]


def _load_accounts():
    from config.settings import ACCOUNTS as CONFIG_ACCOUNTS, list_account_ids

    accounts = []
    for index, account in enumerate(list_account_ids()):
        color, hover = ACCOUNT_COLORS[index % len(ACCOUNT_COLORS)]
        label = CONFIG_ACCOUNTS.get(account, {}).get("display_name", account.title())
        accounts.append((account, label, color, hover))
    return accounts


ACCOUNTS = _load_accounts()

# ── Queue-based log handler ────────────────────────────────
class QueueHandler(logging.Handler):
    """Send log records to a queue so the GUI thread can display them."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put((record.levelno, msg))
        except Exception:
            self.handleError(record)


# ── Pipeline runner (background thread) ────────────────────
def _run_pipeline(account: str, log_queue: queue.Queue, done_event: threading.Event):
    """Run produce_video in a background thread with its own event loop."""
    try:
        log_queue.put((logging.INFO, f"{'='*50}"))
        log_queue.put((logging.INFO, f"  Iniciando pipeline: {account.upper()}"))
        log_queue.put((logging.INFO, f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"))
        log_queue.put((logging.INFO, f"{'='*50}"))

        from core.db import init_db
        from core.key_rotation import seed_keys_from_settings
        init_db()
        seed_keys_from_settings()

        from pipeline.orchestrator import produce_video

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(produce_video(account))
        finally:
            loop.close()

        log_queue.put((logging.INFO, ""))
        log_queue.put((logging.INFO, f"  Pipeline {account.upper()} completado"))
        log_queue.put((logging.INFO, f"{'='*50}"))
    except Exception as exc:
        log_queue.put((logging.ERROR, f"  PIPELINE ERROR: {exc}"))
    finally:
        done_event.set()


# ── Main GUI ───────────────────────────────────────────────
class EasyRunApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EasyRun — ViralStack Automation")
        self.root.configure(bg=BG)
        self.root.geometry("920x660")
        self.root.minsize(720, 500)

        self.log_queue: queue.Queue = queue.Queue()
        self.running_account: str | None = None
        self.buttons: dict[str, tk.Button] = {}

        self._install_log_handler()
        self._build_ui()
        self._poll_log_queue()

    # ── logging ────────────────────────────────────────────
    def _install_log_handler(self):
        fmt = logging.Formatter("%(asctime)s  %(name)s  %(levelname)s  %(message)s",
                                datefmt="%H:%M:%S")
        qh = QueueHandler(self.log_queue)
        qh.setFormatter(fmt)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(qh)
        # Also capture stdout prints (some libs use print)
        # Keep stderr for uncaught tracebacks

    # ── UI construction ────────────────────────────────────
    def _build_ui(self):
        # ── Header ──
        header = tk.Frame(self.root, bg=BG, pady=12)
        header.pack(fill="x")
        tk.Label(
            header, text="EasyRun", font=("Segoe UI", 22, "bold"),
            fg=FG, bg=BG,
        ).pack()
        tk.Label(
            header, text="Short-form Automation",
            font=("Segoe UI", 10), fg=FG_DIM, bg=BG,
        ).pack()

        # ── Buttons row ──
        btn_frame = tk.Frame(self.root, bg=BG, pady=8)
        btn_frame.pack(fill="x", padx=24)

        for account, label, color, hover_color in ACCOUNTS:
            btn = tk.Button(
                btn_frame,
                text=f"  Subir {label}  ",
                font=("Segoe UI", 13, "bold"),
                bg=color, fg=BTN_FG,
                activebackground=hover_color, activeforeground=BTN_FG,
                relief="flat", cursor="hand2", bd=0,
                padx=18, pady=10,
                command=lambda a=account: self._on_run(a),
            )
            btn.pack(side="left", expand=True, fill="x", padx=6)
            btn.bind("<Enter>", lambda e, b=btn, c=hover_color: b.config(bg=c))
            btn.bind("<Leave>", lambda e, b=btn, c=color: b.config(bg=c) if not b["state"] == "disabled" else None)
            self.buttons[account] = btn

        # ── Status bar ──
        self.status_var = tk.StringVar(value="Listo — selecciona una cuenta para generar y subir video")
        status_bar = tk.Frame(self.root, bg=BG_CARD, pady=6)
        status_bar.pack(fill="x", padx=24, pady=(8, 0))
        self.status_dot = tk.Label(status_bar, text="●", fg=FG_SUCCESS, bg=BG_CARD,
                                    font=("Segoe UI", 12))
        self.status_dot.pack(side="left", padx=(12, 6))
        tk.Label(status_bar, textvariable=self.status_var,
                 font=("Segoe UI", 10), fg=FG, bg=BG_CARD, anchor="w").pack(side="left", fill="x")

        # ── Log viewer ──
        log_frame = tk.Frame(self.root, bg=BG, padx=24, pady=8)
        log_frame.pack(fill="both", expand=True)

        tk.Label(log_frame, text="Logs", font=("Segoe UI", 11, "bold"),
                 fg=FG_DIM, bg=BG, anchor="w").pack(fill="x", pady=(0, 4))

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            bg=BG_LOG, fg=FG,
            font=("Consolas", 9),
            wrap="word",
            insertbackground=FG,
            relief="flat", bd=0,
            state="disabled",
            padx=10, pady=8,
        )
        self.log_text.pack(fill="both", expand=True)

        # Tag colors for log levels
        self.log_text.tag_configure("INFO",    foreground=FG)
        self.log_text.tag_configure("WARNING", foreground=FG_WARNING)
        self.log_text.tag_configure("ERROR",   foreground=FG_ERROR)
        self.log_text.tag_configure("DEBUG",   foreground=FG_DIM)
        self.log_text.tag_configure("SUCCESS", foreground=FG_SUCCESS)
        self.log_text.tag_configure("HEADER",  foreground=FG_INFO, font=("Consolas", 9, "bold"))

        # ── Footer ──
        footer = tk.Frame(self.root, bg=BG, pady=6)
        footer.pack(fill="x")

        self.clear_btn = tk.Button(
            footer, text="Limpiar Logs", font=("Segoe UI", 9),
            bg=BG_CARD, fg=FG_DIM, relief="flat", cursor="hand2",
            command=self._clear_logs,
        )
        self.clear_btn.pack(side="right", padx=24)

    # ── Actions ────────────────────────────────────────────
    def _on_run(self, account: str):
        if self.running_account:
            return  # Already running

        self.running_account = account
        self._set_buttons_enabled(False)
        self._update_status(f"Generando y subiendo video de {account.upper()}...", "running")
        self._append_log("", "INFO")

        done_event = threading.Event()

        thread = threading.Thread(
            target=_run_pipeline,
            args=(account, self.log_queue, done_event),
            daemon=True,
        )
        thread.start()
        self._watch_done(done_event, account)

    def _watch_done(self, done_event: threading.Event, account: str):
        if done_event.is_set():
            self.running_account = None
            self._set_buttons_enabled(True)
            self._update_status(f"Pipeline {account.upper()} terminado — listo para otro", "idle")
        else:
            self.root.after(300, self._watch_done, done_event, account)

    def _set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for account, btn in self.buttons.items():
            btn.config(state=state)
            if not enabled:
                btn.config(bg="#444455")
            else:
                for a, _, color, _ in ACCOUNTS:
                    if a == account:
                        btn.config(bg=color)

    def _update_status(self, text: str, mode: str):
        self.status_var.set(text)
        if mode == "running":
            self.status_dot.config(fg=FG_WARNING)
        else:
            self.status_dot.config(fg=FG_SUCCESS)

    def _clear_logs(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    # ── Log polling ────────────────────────────────────────
    def _poll_log_queue(self):
        batch = 0
        while batch < 100:  # process up to 100 lines per tick
            try:
                level, msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            batch += 1
            self._append_log(msg, self._level_tag(level))

        self.root.after(80, self._poll_log_queue)

    def _level_tag(self, level: int) -> str:
        if level >= logging.ERROR:
            return "ERROR"
        if level >= logging.WARNING:
            return "WARNING"
        if level <= logging.DEBUG:
            return "DEBUG"
        return "INFO"

    def _append_log(self, msg: str, tag: str = "INFO"):
        # Detect header / success lines
        if "====" in msg or "Iniciando pipeline" in msg or "completado" in msg:
            tag = "HEADER"
        if "success" in msg.lower() or "OK" in msg or "published" in msg.lower():
            tag = "SUCCESS"

        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ── Run ────────────────────────────────────────────────
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = EasyRunApp()
    app.run()
