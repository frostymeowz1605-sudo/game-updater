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

CURRENT_VERSION = "1.9-test.1"
APP_NAME = "Moja Aplikacja PRO"

# ---------------------------------------------------------------------------
# TŁUMACZENIA (nowość w tej wersji: wybór języka)
# ---------------------------------------------------------------------------

SETTINGS_FILE = "app_settings.json"

TRANSLATIONS = {
    "pl": {
        "version_label": "Wersja: {version}",
        "check_button": "Sprawdź aktualizacje",
        "checking": "Sprawdzanie aktualizacji...",
        "up_to_date": "Masz najnowszą wersję.",
        "update_found": "Dostępna nowa wersja: {version}",
        "check_failed": "Nie udało się sprawdzić aktualizacji (brak połączenia?).",
        "menu_file": "Plik",
        "menu_exit": "Wyjście",
        "menu_settings": "Ustawienia",
        "menu_language": "Język",
        "menu_help": "Pomoc",
        "menu_about": "O programie",
        "about_title": "O programie",
        "about_text": f"{APP_NAME}\nWersja {{version}}\n\nProsta aplikacja z systemem automatycznych aktualizacji.",
        "update_dialog_title": "Dostępna aktualizacja",
        "update_dialog_body": "Dostępna jest nowa wersja: {latest}\n(Twoja wersja: {current})",
        "update_dialog_notes": "\n\nCo nowego:\n{notes}",
        "update_dialog_no_url": "\n\n(Brak skonfigurowanego adresu aktualizacji automatycznej.)",
        "update_dialog_confirm": "\n\nZaktualizować teraz automatycznie? Aplikacja uruchomi się ponownie.",
        "update_downloading": "Pobieranie aktualizacji...",
        "update_failed_title": "Błąd aktualizacji",
        "update_failed_body": "Nie udało się zaktualizować aplikacji:\n{error}\n\nAplikacja nie została zmieniona.",
        "update_failed_status": "Aktualizacja nie powiodła się.",
        "update_success_title": "Zaktualizowano",
        "update_success_body": "Aplikacja została zaktualizowana i zaraz uruchomi się ponownie.\n(Kopia poprzedniej wersji: {backup})",
    },
    "en": {
        "version_label": "Version: {version}",
        "check_button": "Check for updates",
        "checking": "Checking for updates...",
        "up_to_date": "You have the latest version.",
        "update_found": "New version available: {version}",
        "check_failed": "Could not check for updates (no connection?).",
        "menu_file": "File",
        "menu_exit": "Exit",
        "menu_settings": "Settings",
        "menu_language": "Language",
        "menu_help": "Help",
        "menu_about": "About",
        "about_title": "About",
        "about_text": f"{APP_NAME}\nVersion {{version}}\n\nA simple app with an automatic update system.",
        "update_dialog_title": "Update available",
        "update_dialog_body": "A new version is available: {latest}\n(Your version: {current})",
        "update_dialog_notes": "\n\nWhat's new:\n{notes}",
        "update_dialog_no_url": "\n\n(No automatic update address configured.)",
        "update_dialog_confirm": "\n\nUpdate automatically now? The app will restart.",
        "update_downloading": "Downloading update...",
        "update_failed_title": "Update failed",
        "update_failed_body": "Failed to update the application:\n{error}\n\nThe application was not changed.",
        "update_failed_status": "Update failed.",
        "update_success_title": "Updated",
        "update_success_body": "The application has been updated and will restart shortly.\n(Previous version backup: {backup})",
    },
}


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"language": "pl"}


def save_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # brak zapisu ustawień nie powinien wywalać aplikacji

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
    """
    Zamienia string wersji na krotkę liczb do porównywania.
    Obsługuje zarówno proste wersje ('1.10' -> (1, 10)),
    jak i wersje z dopiskami typu 'test' ('1.9-test.1' -> (1, 9, 1)).
    Wyciąga po prostu wszystkie liczby występujące w tekście, w kolejności.
    """
    import re
    numbers = re.findall(r"\d+", version_str)
    return tuple(int(n) for n in numbers) if numbers else (0,)


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
        self.settings = load_settings()
        self.lang = self.settings.get("language", "pl")

        self.root.geometry("460x260")
        self.root.resizable(False, False)

        self._build_menu()

        self.title_label = tk.Label(self.root, text=APP_NAME, font=("Segoe UI", 16, "bold"))
        self.title_label.pack(pady=(20, 5))

        self.version_label = tk.Label(self.root, font=("Segoe UI", 11))
        self.version_label.pack()

        self.status_label = tk.Label(
            self.root, text="", font=("Segoe UI", 10), fg="gray", wraplength=420, justify="center"
        )
        self.status_label.pack(pady=15)

        self.check_button = tk.Button(self.root, command=self.check_for_updates, width=25)
        self.check_button.pack(pady=5)

        self.refresh_texts()
        self.root.after(500, self.check_for_updates)

    def t(self, key: str) -> str:
        return TRANSLATIONS[self.lang][key]

    def _build_menu(self):
        self.menubar = tk.Menu(self.root)

        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.file_menu.add_command(command=self.root.quit)
        self.menubar.add_cascade(menu=self.file_menu)

        self.settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.language_menu = tk.Menu(self.settings_menu, tearoff=0)
        self.language_menu.add_command(label="Polski", command=lambda: self.set_language("pl"))
        self.language_menu.add_command(label="English", command=lambda: self.set_language("en"))
        self.settings_menu.add_cascade(menu=self.language_menu)
        self.menubar.add_cascade(menu=self.settings_menu)

        self.help_menu = tk.Menu(self.menubar, tearoff=0)
        self.help_menu.add_command(command=self.show_about)
        self.menubar.add_cascade(menu=self.help_menu)

        self.root.config(menu=self.menubar)

    def set_language(self, lang_code: str):
        self.lang = lang_code
        self.settings["language"] = lang_code
        save_settings(self.settings)
        self.refresh_texts()

    def refresh_texts(self):
        self.root.title(APP_NAME)
        self.version_label.config(text=self.t("version_label").format(version=CURRENT_VERSION))
        self.check_button.config(text=self.t("check_button"))

        self.menubar.entryconfig(1, label=self.t("menu_file"))
        self.file_menu.entryconfig(0, label=self.t("menu_exit"))

        self.menubar.entryconfig(2, label=self.t("menu_settings"))
        self.settings_menu.entryconfig(0, label=self.t("menu_language"))

        self.menubar.entryconfig(3, label=self.t("menu_help"))
        self.help_menu.entryconfig(0, label=self.t("menu_about"))

    def show_about(self):
        text = self.t("about_text").format(version=CURRENT_VERSION)
        messagebox.showinfo(self.t("about_title"), text)

    def check_for_updates(self):
        self.check_button.config(state="disabled")
        self.status_label.config(text=self.t("checking"), fg="gray")
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
        self.status_label.config(text=self.t("check_failed"), fg="red")

    def _on_check_finished(self, latest_version: str, info: dict):
        self.check_button.config(state="normal")

        if is_update_available(latest_version):
            self.status_label.config(text=self.t("update_found").format(version=latest_version), fg="green")
            self.show_update_dialog(latest_version, info)
        else:
            self.status_label.config(text=self.t("up_to_date"), fg="gray")

    def show_update_dialog(self, latest_version: str, info: dict):
        notes = info.get("notes", "")
        script_url = info.get("script_url", "")

        message = self.t("update_dialog_body").format(latest=latest_version, current=CURRENT_VERSION)
        if notes:
            message += self.t("update_dialog_notes").format(notes=notes)

        if not script_url:
            message += self.t("update_dialog_no_url")
            messagebox.showinfo(self.t("update_dialog_title"), message)
            return

        message += self.t("update_dialog_confirm")

        if messagebox.askyesno(self.t("update_dialog_title"), message):
            self.perform_update(script_url)

    def perform_update(self, script_url: str):
        self.status_label.config(text=self.t("update_downloading"), fg="gray")
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
        self.status_label.config(text=self.t("update_failed_status"), fg="red")
        messagebox.showerror(self.t("update_failed_title"), self.t("update_failed_body").format(error=error_message))

    def _on_update_succeeded(self, backup_path: str):
        messagebox.showinfo(
            self.t("update_success_title"),
            self.t("update_success_body").format(backup=os.path.basename(backup_path)),
        )
        restart_application()


def main():
    root = tk.Tk()
    UpdaterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
