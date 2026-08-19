"""
Przykładowa aplikacja z systemem sprawdzania aktualizacji.

Jak to działa:
- Aplikacja ma wpisaną własną wersję (CURRENT_VERSION).
- Po uruchomieniu (i na żądanie przyciskiem) łączy się przez HTTPS
  z plikiem version.json, który Ty hostujesz (np. na GitHub, własnym
  serwerze, S3 itp.) i sprawdza, jaka jest najnowsza wersja.
- Jeśli najnowsza wersja jest wyższa niż wersja aplikacji, pokazuje
  okienko z informacją i przyciskiem do otwarcia strony pobierania.
- Aplikacja NIGDY nie pobiera i nie uruchamia automatycznie kodu
  z internetu - to celowe zabezpieczenie. Użytkownik sam pobiera
  i instaluje nową wersję.

Do testów lokalnych (bez własnego serwera) jest tryb TEST_MODE,
który czyta plik version.json z dysku zamiast z internetu.
"""

import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from urllib.request import urlopen
from urllib.error import URLError

# ---------------------------------------------------------------------------
# KONFIGURACJA - to zmieniasz pod swoją aplikację
# ---------------------------------------------------------------------------

CURRENT_VERSION = "1.8"

# Adres HTTPS do pliku version.json, który hostujesz Ty.
# Przykład dla GitHuba: umieść plik version.json w repozytorium
# i użyj linku do "raw" wersji pliku, np.:
# https://raw.githubusercontent.com/twoj_uzytkownik/twoje_repo/main/version.json
VERSION_CHECK_URL = "https://raw.githubusercontent.com/frostymeowz1605-sudo/game-updater/main/index.json"

# Tryb testowy: True = czyta lokalny plik version.json (do testów bez sieci)
#               False = łączy się naprawdę z VERSION_CHECK_URL przez internet
TEST_MODE = False
LOCAL_VERSION_FILE = "version.json"

REQUEST_TIMEOUT_SECONDS = 10

# Maksymalny dopuszczalny rozmiar pobieranego pliku ze skryptem (bajty).
# Zabezpieczenie przed pobraniem czegoś ogromnego/uszkodzonego przez pomyłkę.
MAX_SCRIPT_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# ---------------------------------------------------------------------------
# LOGIKA SPRAWDZANIA WERSJI
# ---------------------------------------------------------------------------


def parse_version(version_str: str):
    """Zamienia '1.10' na (1, 10) do poprawnego porównywania liczb."""
    parts = []
    for chunk in version_str.strip().split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def fetch_latest_version_info() -> dict:
    """
    Pobiera informacje o najnowszej wersji.
    Zwraca słownik np. {"version": "1.8", "download_url": "...", "notes": "..."}
    Rzuca wyjątek, jeśli coś pójdzie nie tak (brak sieci, zły JSON itd.).
    """
    if TEST_MODE:
        with open(LOCAL_VERSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    if not VERSION_CHECK_URL.startswith("https://"):
        raise ValueError("Ze względów bezpieczeństwa dozwolone jest tylko HTTPS.")

    context = ssl.create_default_context()  # pełna weryfikacja certyfikatu SSL
    with urlopen(VERSION_CHECK_URL, timeout=REQUEST_TIMEOUT_SECONDS, context=context) as response:
        data = response.read().decode("utf-8")
        return json.loads(data)


def is_update_available(latest_version: str) -> bool:
    return parse_version(latest_version) > parse_version(CURRENT_VERSION)


def download_new_script(script_url: str) -> str:
    """
    Pobiera treść nowej wersji skryptu z podanego adresu HTTPS.
    Zwraca zawartość pliku jako tekst. Rzuca wyjątek przy problemach.
    """
    if not script_url.startswith("https://"):
        raise ValueError("Ze względów bezpieczeństwa dozwolone jest tylko HTTPS.")

    context = ssl.create_default_context()
    with urlopen(script_url, timeout=REQUEST_TIMEOUT_SECONDS, context=context) as response:
        raw = response.read(MAX_SCRIPT_SIZE_BYTES + 1)

    if len(raw) > MAX_SCRIPT_SIZE_BYTES:
        raise ValueError("Pobrany plik jest podejrzanie duży - przerwano aktualizację.")

    text = raw.decode("utf-8")

    # Sprawdzenie, że to poprawny kod Pythona, zanim cokolwiek nadpiszemy
    import ast
    ast.parse(text)

    return text


def apply_update(new_source_code: str) -> str:
    """
    Podmienia bieżący plik aplikacji na nową wersję.
    Robi kopię zapasową starego pliku na wypadek problemów.
    Zwraca ścieżkę do pliku kopii zapasowej.
    """
    current_file = os.path.abspath(__file__)
    backup_file = current_file + ".backup"

    shutil.copy2(current_file, backup_file)

    try:
        with open(current_file, "w", encoding="utf-8") as f:
            f.write(new_source_code)
    except Exception:
        # W razie błędu przywracamy starą wersję z kopii zapasowej
        shutil.copy2(backup_file, current_file)
        raise

    return backup_file


def restart_application():
    """Uruchamia świeżo zaktualizowany plik i zamyka bieżący proces."""
    python_executable = sys.executable
    script_path = os.path.abspath(__file__)
    subprocess.Popen([python_executable, script_path])
    sys.exit(0)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class UpdaterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Moja Aplikacja")
        self.root.geometry("420x220")
        self.root.resizable(False, False)

        tk.Label(
            self.root,
            text="Moja Aplikacja",
            font=("Segoe UI", 16, "bold"),
        ).pack(pady=(20, 5))

        tk.Label(
            self.root,
            text=f"Wersja: {CURRENT_VERSION}",
            font=("Segoe UI", 11),
        ).pack()

        self.status_label = tk.Label(
            self.root,
            text="",
            font=("Segoe UI", 10),
            fg="gray",
            wraplength=380,
            justify="center",
        )
        self.status_label.pack(pady=15)

        self.check_button = tk.Button(
            self.root,
            text="Sprawdź aktualizacje",
            command=self.check_for_updates,
            width=25,
        )
        self.check_button.pack(pady=5)

        # Automatyczne sprawdzenie przy starcie aplikacji
        self.root.after(500, self.check_for_updates)

    def check_for_updates(self):
        self.check_button.config(state="disabled")
        self.status_label.config(text="Sprawdzanie aktualizacji...", fg="gray")
        # Sprawdzanie w osobnym wątku, żeby okno się nie zawieszało
        threading.Thread(target=self._check_for_updates_worker, daemon=True).start()

    def _check_for_updates_worker(self):
        try:
            info = fetch_latest_version_info()
            latest_version = str(info.get("version", CURRENT_VERSION))
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as e:
            self.root.after(0, self._on_check_failed, str(e))
            return

        self.root.after(0, self._on_check_finished, latest_version, info)

    def _on_check_failed(self, error_message: str):
        self.check_button.config(state="normal")
        self.status_label.config(
            text="Nie udało się sprawdzić aktualizacji (brak połączenia?).",
            fg="red",
        )

    def _on_check_finished(self, latest_version: str, info: dict):
        self.check_button.config(state="normal")

        if is_update_available(latest_version):
            self.status_label.config(
                text=f"Dostępna nowa wersja: {latest_version}",
                fg="green",
            )
            self.show_update_dialog(latest_version, info)
        else:
            self.status_label.config(text="Masz najnowszą wersję.", fg="gray")

    def show_update_dialog(self, latest_version: str, info: dict):
        notes = info.get("notes", "")
        script_url = info.get("script_url", "")

        message = f"Dostępna jest nowa wersja: {latest_version}\n(Twoja wersja: {CURRENT_VERSION})"
        if notes:
            message += f"\n\nCo nowego:\n{notes}"

        if not script_url:
            message += "\n\n(Brak skonfigurowanego adresu aktualizacji automatycznej.)"
            messagebox.showinfo("Dostępna aktualizacja", message)
            return

        message += "\n\nZaktualizować teraz automatycznie? Aplikacja uruchomi się ponownie."

        if messagebox.askyesno("Dostępna aktualizacja", message):
            self.perform_update(script_url)

    def perform_update(self, script_url: str):
        self.status_label.config(text="Pobieranie aktualizacji...", fg="gray")
        self.check_button.config(state="disabled")
        threading.Thread(target=self._perform_update_worker, args=(script_url,), daemon=True).start()

    def _perform_update_worker(self, script_url: str):
        try:
            new_code = download_new_script(script_url)
            backup_path = apply_update(new_code)
        except Exception as e:
            self.root.after(0, self._on_update_failed, str(e))
            return

        self.root.after(0, self._on_update_succeeded, backup_path)

    def _on_update_failed(self, error_message: str):
        self.check_button.config(state="normal")
        self.status_label.config(text="Aktualizacja nie powiodła się.", fg="red")
        messagebox.showerror(
            "Błąd aktualizacji",
            f"Nie udało się zaktualizować aplikacji:\n{error_message}\n\n"
            "Aplikacja nie została zmieniona.",
        )

    def _on_update_succeeded(self, backup_path: str):
        messagebox.showinfo(
            "Zaktualizowano",
            "Aplikacja została zaktualizowana i zaraz uruchomi się ponownie.\n"
            f"(Kopia poprzedniej wersji: {os.path.basename(backup_path)})",
        )
        restart_application()


def main():
    root = tk.Tk()
    UpdaterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
