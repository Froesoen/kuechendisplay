"""gui_app.py
Einfache Tkinter-Oberflaeche fuer die produktive Verwaltung des
GROW R503 Fingerabdrucksensors. Alle sensorblockierenden Vorgaenge laufen
in einem Hintergrundthread, Rueckmeldungen kommen ueber eine Queue.

Zusaetzlich: Steuerung von kuechendisplay-supervisor.service, damit der
Supervisor waehrend der Sensorarbeit nicht parallel auf /dev/serial0 zugreift."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import queue
import threading

import backup_store
import config
import supervisor_control
from logging_setup import get_logger
from sensor_core import FingerprintSensor, SensorError

logger = get_logger(__name__)


class FingerprintApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fingerabdruck-Verwaltung - Kuechendisplay Familienplaner")
        self.geometry("900x680")
        self.minsize(760, 560)

        self.sensor = FingerprintSensor()
        self.msg_queue = queue.Queue()
        self.worker_thread = None
        self.cancel_event = threading.Event()

        self._build_layout()
        self.after(150, self._poll_queue)
        self.after(0, self._refresh_supervisor_status)
        self._connect_sensor()

    def _build_layout(self):
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        top = ttk.Frame(self, padding=8)
        top.grid(row=0, column=0, sticky="ew")

        self.status_var = tk.StringVar(value="Nicht verbunden.")
        ttk.Label(top, textvariable=self.status_var, font=("TkDefaultFont", 10, "bold")).pack(side="left")

        ttk.Button(top, text="Neu verbinden", command=self._connect_sensor).pack(side="right")
        ttk.Button(top, text="Aktualisieren", command=self._refresh_list).pack(side="right", padx=4)

        supervisor_frame = ttk.LabelFrame(self, text="Kuechendisplay-Supervisor", padding=8)
        supervisor_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

        self.supervisor_status_var = tk.StringVar(value="Status unbekannt.")
        ttk.Label(supervisor_frame, textvariable=self.supervisor_status_var).pack(side="left")

        ttk.Button(supervisor_frame, text="Supervisor stoppen",
                   command=self._on_stop_supervisor).pack(side="right", padx=2)
        ttk.Button(supervisor_frame, text="Supervisor starten",
                   command=self._on_start_supervisor).pack(side="right", padx=2)
        ttk.Button(supervisor_frame, text="Status pruefen",
                   command=self._refresh_supervisor_status).pack(side="right", padx=2)

        main = ttk.PanedWindow(self, orient="vertical")
        main.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)

        upper = ttk.Frame(main)
        main.add(upper, weight=3)

        lower = ttk.LabelFrame(main, text="Protokoll", padding=6)
        main.add(lower, weight=2)

        list_frame = ttk.LabelFrame(upper, text="Belegte Templates", padding=6)
        list_frame.pack(side="left", fill="both", expand=True)

        columns = ("id", "name")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=14)
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Name (aus Zuordnung)")
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("name", width=220)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_row)

        action_frame = ttk.LabelFrame(upper, text="Aktionen", padding=8)
        action_frame.pack(side="left", fill="y", padx=(8, 0))

        ttk.Label(action_frame, text="Template-ID:").grid(row=0, column=0, sticky="w")
        self.id_var = tk.StringVar()
        self.id_entry = ttk.Entry(action_frame, textvariable=self.id_var, width=10)
        self.id_entry.grid(row=0, column=1, sticky="w", pady=2)

        self.owner_var = tk.StringVar(value="")
        ttk.Label(action_frame, textvariable=self.owner_var, foreground="gray").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Button(action_frame, text="Finger einlernen",
                   command=self._on_enroll).grid(row=2, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Button(action_frame, text="Template loeschen",
                   command=self._on_delete).grid(row=3, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Button(action_frame, text="Finger testen (Identify)",
                   command=self._on_identify).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(2, 14))

        ttk.Separator(action_frame, orient="horizontal").grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Button(action_frame, text="Backup erstellen (alle)",
                   command=self._on_backup_all).grid(row=6, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Button(action_frame, text="Backup wiederherstellen",
                   command=self._on_restore).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(2, 14))

        ttk.Separator(action_frame, orient="horizontal").grid(row=8, column=0, columnspan=2, sticky="ew", pady=4)

        ttk.Button(action_frame, text="Sensor-Passwort aendern",
                   command=self._on_change_password).grid(row=9, column=0, columnspan=2, sticky="ew", pady=2)

        ttk.Separator(action_frame, orient="horizontal").grid(row=10, column=0, columnspan=2, sticky="ew", pady=4)
        self.cancel_btn = ttk.Button(action_frame, text="Vorgang abbrechen",
                                      command=self._on_cancel, state="disabled")
        self.cancel_btn.grid(row=11, column=0, columnspan=2, sticky="ew")

        lower.rowconfigure(0, weight=1)
        lower.columnconfigure(0, weight=1)
        self.log_text = tk.Text(lower, height=18, wrap="word", state="disabled")
        log_scroll = ttk.Scrollbar(lower, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "error":
                    self._log(f"FEHLER: {payload}")
                    messagebox.showerror("Fehler", payload)
                    self._set_busy(False)
                elif kind == "done":
                    self._log(payload)
                    self._set_busy(False)
                    self._refresh_list()
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _set_busy(self, busy: bool):
        self.cancel_btn.configure(state="normal" if busy else "disabled")

    def _run_in_background(self, target, *args):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Bitte warten", "Ein anderer Vorgang laeuft noch.")
            return
        self.cancel_event.clear()
        self.cancel_btn.configure(state="normal")
        self.worker_thread = threading.Thread(target=target, args=args, daemon=True)
        self.worker_thread.start()

    def _on_cancel(self):
        self.cancel_event.set()
        self._log("Abbruch angefordert...")

    def _refresh_supervisor_status(self):
        try:
            active = supervisor_control.is_active()
            self.supervisor_status_var.set(
                "Supervisor: AKTIV (laeuft)" if active else "Supervisor: gestoppt"
            )
        except supervisor_control.SupervisorControlError as exc:
            self.supervisor_status_var.set("Supervisor-Status nicht abrufbar.")
            self._log(f"Supervisor-Status: {exc}")

    def _on_stop_supervisor(self):
        if not messagebox.askyesno(
            "Supervisor stoppen",
            "kuechendisplay-supervisor.service stoppen?\n\n"
            "Waehrend der Supervisor gestoppt ist, geht die MQTT-Verbindung "
            "verloren (status/health -> offline) und Chromium reagiert nicht "
            "mehr auf Modus-/App-Wechsel-Kommandos, bis der Dienst wieder "
            "gestartet wird."
        ):
            return
        try:
            supervisor_control.stop_supervisor()
            self._log("Supervisor gestoppt.")
        except supervisor_control.SupervisorControlError as exc:
            messagebox.showerror("Fehler", str(exc))
        finally:
            self._refresh_supervisor_status()

    def _on_start_supervisor(self):
        try:
            supervisor_control.start_supervisor()
            self._log("Supervisor gestartet.")
        except supervisor_control.SupervisorControlError as exc:
            messagebox.showerror("Fehler", str(exc))
        finally:
            self._refresh_supervisor_status()

    def _connect_sensor(self):
        try:
            self.sensor.disconnect()
            self.sensor.connect()
            self.status_var.set("Verbunden mit Sensor.")
            self._log("Verbindung zum Sensor hergestellt.")
            self._refresh_list()
        except SensorError as exc:
            self.status_var.set("Verbindung fehlgeschlagen.")
            self._log(f"FEHLER: {exc}")
            messagebox.showerror("Verbindungsfehler", str(exc))

    def _refresh_list(self):
        try:
            ids = self.sensor.used_ids()
            status = self.sensor.status()
        except SensorError as exc:
            self._log(f"FEHLER beim Aktualisieren: {exc}")
            return

        self.status_var.set(
            f"Verbunden - belegt: {status['template_count']} / {status['library_size']}"
        )
        for row in self.tree.get_children():
            self.tree.delete(row)
        for template_id in sorted(ids):
            name = config.FINGERPRINT_MAPPING.get_user_for_id(template_id) or ""
            self.tree.insert("", "end", values=(template_id, name))

    def _on_select_row(self, _event):
        sel = self.tree.selection()
        if sel:
            values = self.tree.item(sel[0], "values")
            self.id_var.set(values[0])
            self._update_owner_label()

    def _update_owner_label(self):
        raw = self.id_var.get().strip()
        if not raw.isdigit():
            self.owner_var.set("")
            return
        owner = config.FINGERPRINT_MAPPING.get_user_for_id(int(raw))
        self.owner_var.set(f"Zugeordnet: {owner}" if owner else "Keinem Namen zugeordnet.")

    def _read_template_id(self):
        raw = self.id_var.get().strip()
        if not raw.isdigit():
            messagebox.showwarning("Ungueltige Eingabe", "Bitte eine Template-ID (Zahl) eingeben.")
            return None
        template_id = int(raw)
        if not (config.MIN_TEMPLATE_ID <= template_id <= config.MAX_TEMPLATE_ID):
            messagebox.showwarning(
                "Ungueltige ID",
                f"ID muss zwischen {config.MIN_TEMPLATE_ID} und {config.MAX_TEMPLATE_ID} liegen."
            )
            return None
        return template_id

    def _on_enroll(self):
        template_id = self._read_template_id()
        if template_id is None:
            return

        overwrite = False
        try:
            if self.sensor.is_occupied(template_id):
                owner = config.FINGERPRINT_MAPPING.get_user_for_id(template_id) or "unbenannt"
                overwrite = messagebox.askyesno(
                    "ID bereits belegt",
                    f"ID {template_id} ist bereits belegt (Zuordnung: {owner}).\n"
                    "Vorhandenes Template loeschen und mit neuem Finger ueberschreiben?"
                )
                if not overwrite:
                    self._log(f"Enrollment auf ID {template_id} abgebrochen (ID belegt).")
                    return
        except SensorError as exc:
            messagebox.showerror("Fehler", str(exc))
            return

        def task():
            try:
                self.sensor.enroll(
                    template_id,
                    overwrite=overwrite,
                    progress_cb=lambda m: self.msg_queue.put(("log", m)),
                    cancel_event=self.cancel_event,
                )
                self.msg_queue.put(("done", f"Enrollment ID {template_id} abgeschlossen."))
            except SensorError as exc:
                self.msg_queue.put(("error", str(exc)))

        self._run_in_background(task)

    def _on_delete(self):
        template_id = self._read_template_id()
        if template_id is None:
            return
        owner = config.FINGERPRINT_MAPPING.get_user_for_id(template_id) or "unbenannt"
        if not messagebox.askyesno("Loeschen bestaetigen", f"Template ID {template_id} ({owner}) wirklich loeschen?"):
            return
        try:
            self.sensor.delete(template_id)
            self._log(f"Template ID {template_id} geloescht.")
            self._refresh_list()
        except SensorError as exc:
            messagebox.showerror("Fehler", str(exc))

    def _on_identify(self):
        def task():
            try:
                result = self.sensor.identify(
                    timeout=15,
                    progress_cb=lambda m: self.msg_queue.put(("log", m)),
                    cancel_event=self.cancel_event,
                )
                if result is None:
                    self.msg_queue.put(("done", "Kein passender Finger in der Datenbank gefunden."))
                else:
                    owner = config.FINGERPRINT_MAPPING.get_user_for_id(result["id"]) or "kein Name zugeordnet"
                    self.msg_queue.put((
                        "done",
                        f"Finger erkannt! ID {result['id']} -> {owner} (Score {result['confidence']})."
                    ))
            except SensorError as exc:
                self.msg_queue.put(("error", str(exc)))

        self._run_in_background(task)

    def _on_backup_all(self):
        path = filedialog.asksaveasfilename(
            title="Backup speichern als",
            initialdir=config.BACKUP_DIR,
            defaultextension=".json",
            filetypes=[("Fingerprint-Backup", "*.json")],
        )
        if not path:
            return

        def task():
            try:
                self.msg_queue.put(("log", "Lese alle belegten Templates vom Sensor..."))
                backup_dict = backup_store.build_backup(self.sensor)
                backup_store.save_backup(path, backup_dict)
                self.msg_queue.put((
                    "done",
                    f"Backup mit {len(backup_dict['entries'])} Templates gespeichert: {path}"
                ))
            except (SensorError, OSError) as exc:
                self.msg_queue.put(("error", str(exc)))

        self._run_in_background(task)

    def _on_restore(self):
        path = filedialog.askopenfilename(
            title="Backup-Datei auswaehlen",
            initialdir=config.BACKUP_DIR,
            filetypes=[("Fingerprint-Backup", "*.json")],
        )
        if not path:
            return

        try:
            backup_dict = backup_store.load_backup(path)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Fehler", f"Backup konnte nicht gelesen werden: {exc}")
            return

        overwrite = messagebox.askyesno(
            "Vorhandene IDs ueberschreiben?",
            f"Backup enthaelt {len(backup_dict['entries'])} Templates.\n"
            "Sollen auf dem aktuell verbundenen Sensor bereits belegte IDs "
            "ueberschrieben werden? (Nein = nur freie IDs werden importiert)"
        )

        def task():
            results = backup_store.restore_backup(
                self.sensor, backup_dict, overwrite=overwrite,
                progress_cb=lambda m: self.msg_queue.put(("log", m)),
            )
            ok = sum(1 for _, success, _ in results if success)
            failed = [r for r in results if not r[1]]
            summary = f"Restore abgeschlossen: {ok}/{len(results)} erfolgreich."
            if failed:
                summary += f" Fehlgeschlagen: {[f'{i}' for i, _, _ in failed]}"
            self.msg_queue.put(("done", summary))

        self._run_in_background(task)

    def _on_change_password(self):
        current = simpledialog.askinteger(
            "Aktuelles Passwort",
            "Aktuelles Sensor-Passwort eingeben (Zahl, Standard ist 0):",
            parent=self,
        )
        if current is None:
            return
        if current != self.sensor.password:
            messagebox.showerror("Fehler", "Das eingegebene aktuelle Passwort stimmt nicht mit der Konfiguration ueberein.")
            return

        new_pw1 = simpledialog.askinteger("Neues Passwort", "Neues Passwort eingeben:", parent=self)
        if new_pw1 is None:
            return
        new_pw2 = simpledialog.askinteger("Neues Passwort bestaetigen", "Neues Passwort erneut eingeben:", parent=self)
        if new_pw2 is None:
            return
        if new_pw1 != new_pw2:
            messagebox.showerror("Fehler", "Die beiden Eingaben stimmen nicht ueberein. Vorgang abgebrochen.")
            return

        if not messagebox.askyesno(
            "Achtung",
            "Bei Verlust dieses Passworts ist der Sensor ohne Werksreset/"
            "Hersteller-Tool NICHT mehr ansprechbar.\n\n"
            "Neues Passwort jetzt sicher hinterlegen (z. B. Passwortmanager) "
            "und Aenderung wirklich durchfuehren?"
        ):
            return

        try:
            self.sensor.change_password(new_pw1)
            config.set_sensor_password(new_pw1)
            self._log("Sensor-Passwort erfolgreich geaendert und lokal gespeichert.")
            messagebox.showinfo("Erfolg", "Passwort wurde geaendert und lokal gespeichert.")
        except SensorError as exc:
            messagebox.showerror("Fehler", str(exc))


def main():
    app = FingerprintApp()
    app.mainloop()


if __name__ == "__main__":
    main()
