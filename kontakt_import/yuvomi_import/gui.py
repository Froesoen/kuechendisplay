"""Einfache Tkinter-Oberflaeche: Tabelle waehlen, Dry-Run pruefen, importieren.

Start: python -m yuvomi_import   (ohne Argumente)   oder ./start_gui.sh
Benoetigt tkinter (Debian/Raspberry Pi OS: sudo apt install python3-tk).
Alle blockierenden Vorgaenge laufen in einem Hintergrund-Thread.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .credentials import DEFAULT_SECRETS_FILE, resolve_path
from .reader import sheet_names
from .service import ImportConfig, ImportOutcome, list_categories, run_import, test_connection

COLUMNS = (("line", "Zeile", 60), ("name", "Name", 200), ("category", "Kategorie", 110),
           ("action", "Aktion", 130), ("id", "yuvomi-ID", 80), ("detail", "Hinweis", 420))


class App(ttk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root, padding=10)
        self.root = root
        self.pack(fill="both", expand=True)
        self.q: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.dry_signature: tuple | None = None
        self.dry_outcome: ImportOutcome | None = None
        self.report_dir = Path("reports").resolve()

        self.v_table = tk.StringVar()
        self.v_sheet = tk.StringVar()
        self.v_secrets = tk.StringVar(value=str(DEFAULT_SECRETS_FILE))
        self.v_default_cat = tk.StringVar()
        self.v_update = tk.BooleanVar(value=True)
        self.v_create_cat = tk.BooleanVar(value=False)
        self.v_inh_last = tk.BooleanVar(value=True)
        self.v_inh_addr = tk.BooleanVar(value=False)
        self.v_offline = tk.BooleanVar(value=False)
        self._build()
        for v in (self.v_table, self.v_sheet, self.v_secrets, self.v_default_cat, self.v_update,
                  self.v_create_cat, self.v_inh_last, self.v_inh_addr, self.v_offline):
            v.trace_add("write", lambda *_: self._refresh_buttons())
        self._refresh_buttons()
        self.after(100, self._poll)

    # ---------- Aufbau ----------
    def _build(self) -> None:
        f = ttk.LabelFrame(self, text="Quelle", padding=8)
        f.pack(fill="x")
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Tabelle:").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.v_table).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(f, text="Durchsuchen …", command=self._choose_table).grid(row=0, column=2)
        ttk.Label(f, text="Blatt:").grid(row=1, column=0, sticky="w")
        self.cb_sheet = ttk.Combobox(f, textvariable=self.v_sheet, state="normal", width=30)
        self.cb_sheet.grid(row=1, column=1, sticky="w", padx=4, pady=2)
        ttk.Label(f, text="secrets.json:").grid(row=2, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.v_secrets).grid(row=2, column=1, sticky="ew", padx=4)
        ttk.Button(f, text="…", width=3, command=self._choose_secrets).grid(row=2, column=2)

        o = ttk.LabelFrame(self, text="Optionen", padding=8)
        o.pack(fill="x", pady=6)
        ttk.Label(o, text="Standardkategorie:").grid(row=0, column=0, sticky="w")
        ttk.Entry(o, textvariable=self.v_default_cat, width=24).grid(row=0, column=1, sticky="w", padx=4)
        for i, (var, text) in enumerate((
            (self.v_create_cat, "Fehlende Kategorien in yuvomi anlegen"),
            (self.v_update, "Vorhandene Kontakte (gleicher Name) überschreiben"),
            (self.v_inh_last, "Leeren Nachnamen aus Haushaltsblock übernehmen"),
            (self.v_inh_addr, "Leere Adresse aus Haushaltsblock übernehmen"),
            (self.v_offline, "Offline (nur Tabelle prüfen, kein Zugriff auf yuvomi)"),
        )):
            ttk.Checkbutton(o, text=text, variable=var).grid(row=1 + i // 2, column=i % 2, sticky="w", padx=4)

        b = ttk.Frame(self)
        b.pack(fill="x")
        self.btn_test = ttk.Button(b, text="Verbindung testen", command=self._on_test)
        self.btn_cats = ttk.Button(b, text="Kategorien anzeigen", command=self._on_categories)
        self.btn_dry = ttk.Button(b, text="1. Vorschau (Dry-Run)", command=lambda: self._on_run(False))
        self.btn_apply = ttk.Button(b, text="2. Importieren", command=self._on_apply)
        self.btn_report = ttk.Button(b, text="Report-Ordner öffnen", command=self._open_reports)
        for w in (self.btn_test, self.btn_cats, self.btn_dry, self.btn_apply, self.btn_report):
            w.pack(side="left", padx=3, pady=4)

        self.tree = ttk.Treeview(self, columns=[c[0] for c in COLUMNS], show="headings", height=14)
        for cid, title, width in COLUMNS:
            self.tree.heading(cid, text=title)
            self.tree.column(cid, width=width, anchor="w")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure("error", background="#ffd6d6")
        self.tree.tag_configure("create", background="#e3f6e3")
        self.tree.tag_configure("update", background="#fff4cc")
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self.status = tk.StringVar(value="Bereit.")
        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")
        self.log_box = tk.Text(self.root, height=6, state="disabled")
        self.log_box.pack(fill="x", side="bottom")

    # ---------- Zustand ----------
    def _cfg(self, apply: bool) -> ImportConfig:
        table = self.v_table.get().strip()
        if not table or not Path(table).is_file():
            raise ValueError("Bitte eine vorhandene Tabelle (.xlsx/.csv) auswählen.")
        return ImportConfig(
            table=Path(table), sheet=self.v_sheet.get().strip() or None, apply=apply,
            update=self.v_update.get(), default_category=self.v_default_cat.get().strip() or None,
            create_categories=self.v_create_cat.get(), inherit_last_name=self.v_inh_last.get(),
            inherit_address=self.v_inh_addr.get(),
            offline=self.v_offline.get(), secrets_file=Path(self.v_secrets.get().strip() or DEFAULT_SECRETS_FILE),
            report_dir=self.report_dir,
        )

    def _signature(self) -> tuple | None:
        try:
            c = self._cfg(False)
            mtime = c.table.stat().st_mtime
        except (ValueError, OSError):
            return None
        return (str(c.table), mtime, c.sheet, c.update, c.default_category, c.create_categories,
                c.inherit_last_name, c.inherit_address, c.offline, str(c.secrets_file))

    def _refresh_buttons(self) -> None:
        sig = self._signature()
        has_table = sig is not None
        online = not self.v_offline.get()
        st = lambda ok: "normal" if ok and not self.busy else "disabled"
        self.btn_test.config(state=st(online))
        self.btn_cats.config(state=st(online))
        self.btn_dry.config(state=st(has_table))
        ok_apply = (has_table and online and sig == self.dry_signature and self.dry_outcome is not None
                    and not self.dry_outcome.counts.get("error"))
        self.btn_apply.config(state=st(ok_apply))
        self.btn_report.config(state=st(True))

    # ---------- Aktionen ----------
    def _choose_table(self) -> None:
        p = filedialog.askopenfilename(title="Adresstabelle wählen", filetypes=[
            ("Tabellen", "*.xlsx *.xlsm *.csv"), ("Alle Dateien", "*.*")])
        if not p:
            return
        self.v_table.set(p)
        try:
            names = sheet_names(p)
        except Exception as e:  # defekte Datei -> Hinweis, kein Absturz
            names = []
            self._log(f"Blätter nicht lesbar: {e}")
        self.cb_sheet.config(values=names)
        self.v_sheet.set(names[0] if names else "")
        self.report_dir = Path(p).resolve().parent / "reports"

    def _choose_secrets(self) -> None:
        p = filedialog.askopenfilename(title="secrets.json wählen", filetypes=[("JSON", "*.json"), ("Alle", "*.*")])
        if p:
            self.v_secrets.set(p)

    def _secrets_path(self) -> Path:
        return resolve_path(self.v_secrets.get().strip() or None)

    def _on_test(self) -> None:
        self._background("Teste Verbindung …", lambda: test_connection(self._secrets_path(), self._qlog),
                         lambda msg: (self._log(msg), self.status.set(msg)))

    def _on_categories(self) -> None:
        def done(cats: list[dict]) -> None:
            self._log("Kategorien in yuvomi (Key = Name):")
            for c in cats:
                self._log(f"  {c['key']} = {c.get('name') or '(übersetzter Standardname)'}")
            self.status.set(f"{len(cats)} Kategorien geladen")
        self._background("Lade Kategorien …", lambda: list_categories(self._secrets_path(), self._qlog), done)

    def _on_run(self, apply: bool) -> None:
        try:
            cfg, sig = self._cfg(apply), self._signature()
        except ValueError as e:
            messagebox.showwarning("Eingabe", str(e))
            return
        self.tree.delete(*self.tree.get_children())

        def done(out: ImportOutcome) -> None:
            self._fill(out)
            if apply:
                self.dry_signature, self.dry_outcome = None, None
            else:
                self.dry_signature, self.dry_outcome = sig, out
            self.status.set(f"{'Import' if apply else 'Dry-Run'}: {out.counts} – Report: {out.report.name}")
        self._background("Import läuft …" if apply else "Dry-Run läuft …",
                         lambda: run_import(cfg, self._qlog), done)

    def _on_apply(self) -> None:
        if self.dry_outcome is None or self._signature() != self.dry_signature:
            messagebox.showinfo("Import", "Bitte zuerst eine Vorschau (Dry-Run) mit den aktuellen Einstellungen ausführen.")
            return
        c = self.dry_outcome.counts
        msg = (f"{c.get('create', 0)} Kontakte anlegen, {c.get('update', 0)} aktualisieren, "
               f"{c.get('skip-exists', 0)} bereits vorhanden (übersprungen).\n\n"
               "Vorher yuvomi-Backup erstellt? Jetzt wirklich importieren?")
        if messagebox.askyesno("Import bestätigen", msg, icon="warning"):
            self._on_run(True)

    def _open_reports(self) -> None:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(self.report_dir)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(self.report_dir)])

    # ---------- Hintergrundarbeit ----------
    def _background(self, status: str, fn: Callable[[], Any], on_done: Callable[[Any], None]) -> None:
        if self.busy:
            return
        self.busy = True
        self.status.set(status)
        self._refresh_buttons()

        def worker() -> None:
            try:
                self.q.put(("done", (on_done, fn())))
            except Exception as e:  # Fehler im GUI-Thread anzeigen
                self.q.put(("error", f"{e.__class__.__name__}: {e}"))
        threading.Thread(target=worker, daemon=True).start()

    def _qlog(self, text: str) -> None:
        self.q.put(("log", text))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self.busy = False
                    on_done, result = payload
                    on_done(result)
                    self._refresh_buttons()
                else:
                    self.busy = False
                    self._log("FEHLER: " + payload)
                    self.status.set("Fehler – Details im Log")
                    self._refresh_buttons()
                    messagebox.showerror("Fehler", payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _log(self, text: str) -> None:
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _fill(self, out: ImportOutcome) -> None:
        for r in out.results:
            tag = r.action if r.action in ("error", "create", "update") else ""
            self.tree.insert("", "end", values=(r.line, r.name, r.category, r.action, r.contact_id, r.detail),
                             tags=(tag,) if tag else ())


def main() -> int:
    root = tk.Tk()
    root.title("Kontakt-Import → yuvomi")
    root.geometry("1100x720")
    App(root)
    root.mainloop()
    return 0
