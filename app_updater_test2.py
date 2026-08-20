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
from tkinter import messagebox, ttk
from urllib.request import urlopen
from urllib.error import URLError

# ---------------------------------------------------------------------------
# KONFIGURACJA - to zmieniasz pod swoją aplikację
# ---------------------------------------------------------------------------

CURRENT_VERSION = "1.9-test.2"
APP_NAME = "Moja Aplikacja PRO"

# ---------------------------------------------------------------------------
# MOTYW / KOLORY
# ---------------------------------------------------------------------------

COLOR_BG = "#1e1e2e"
COLOR_BG_CARD = "#252538"
COLOR_ACCENT = "#89b4fa"
COLOR_ACCENT_DARK = "#6c93d6"
COLOR_TEXT = "#f5f5f7"
COLOR_TEXT_MUTED = "#a6a6b8"
COLOR_SUCCESS = "#a6e3a1"
COLOR_ERROR = "#f38ba8"
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_SUBTITLE = ("Segoe UI", 11)
FONT_BODY = ("Segoe UI", 10)
FONT_BUTTON = ("Segoe UI", 11, "bold")

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
        "tab_updates": "Aktualizacje",
        "tab_game": "Gra: Klikacz",
        "game_score_label": "Punkty: {score}",
        "game_click_button": "KLIKNIJ!",
        "game_income_label": "Punktów/s: {income}",
        "game_shop_title": "Sklep ulepszeń",
        "game_buy_button": "Kup",
        "game_upgrade_click": "Silniejsze kliknięcie",
        "game_upgrade_auto": "Auto-klikacz",
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
        "tab_updates": "Updates",
        "tab_game": "Game: Clicker",
        "game_score_label": "Score: {score}",
        "game_click_button": "CLICK!",
        "game_income_label": "Points/s: {income}",
        "game_shop_title": "Upgrade shop",
        "game_buy_button": "Buy",
        "game_upgrade_click": "Stronger click",
        "game_upgrade_auto": "Auto-clicker",
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


# ---------------------------------------------------------------------------
# GRA: KLIKACZ (nowość w wersji 1.9-test.2)
# ---------------------------------------------------------------------------

GAME_SAVE_FILE = "clicker_save.json"

# Koszt i efekt każdego ulepszenia rośnie po zakupie
UPGRADE_CLICK_BASE_COST = 10
UPGRADE_AUTO_BASE_COST = 25


def load_game_state() -> dict:
    default = {"score": 0, "click_power": 1, "auto_income": 0,
               "click_upgrade_level": 0, "auto_upgrade_level": 0}
    try:
        with open(GAME_SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            default.update(data)
            return default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_game_state(state: dict):
    try:
        with open(GAME_SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

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
        self.game = load_game_state()

        self.root.geometry("520x420")
        self.root.resizable(False, False)
        self.root.configure(bg=COLOR_BG)

        self._setup_style()
        self._build_menu()

        self.notebook = ttk.Notebook(self.root, style="Dark.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=14, pady=14)

        self.updates_tab = tk.Frame(self.notebook, bg=COLOR_BG_CARD)
        self.game_tab = tk.Frame(self.notebook, bg=COLOR_BG_CARD)
        self.notebook.add(self.updates_tab, text="")
        self.notebook.add(self.game_tab, text="")

        self._build_updates_tab()
        self._build_game_tab()

        self.refresh_texts()
        self.root.after(500, self.check_for_updates)
        self._game_tick()

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Dark.TNotebook", background=COLOR_BG, borderwidth=0)
        style.configure(
            "Dark.TNotebook.Tab",
            background=COLOR_BG_CARD,
            foreground=COLOR_TEXT_MUTED,
            padding=(16, 8),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Dark.TNotebook.Tab",
            background=[("selected", COLOR_ACCENT)],
            foreground=[("selected", "#1e1e2e")],
        )

    def _build_updates_tab(self):
        inner = tk.Frame(self.updates_tab, bg=COLOR_BG_CARD)
        inner.pack(expand=True, pady=20)

        self.title_label = tk.Label(inner, text=APP_NAME, font=FONT_TITLE, bg=COLOR_BG_CARD, fg=COLOR_TEXT)
        self.title_label.pack(pady=(10, 4))

        self.version_badge = tk.Label(
            inner, font=("Segoe UI", 10, "bold"), bg=COLOR_ACCENT, fg="#1e1e2e", padx=12, pady=3,
        )
        self.version_badge.pack(pady=(0, 18))

        self.status_label = tk.Label(
            inner, text="", font=FONT_BODY, bg=COLOR_BG_CARD, fg=COLOR_TEXT_MUTED,
            wraplength=420, justify="center",
        )
        self.status_label.pack(pady=(0, 16))

        self.check_button = tk.Button(
            inner, command=self.check_for_updates, font=FONT_BUTTON, bg=COLOR_ACCENT, fg="#1e1e2e",
            activebackground=COLOR_ACCENT_DARK, activeforeground="#1e1e2e",
            relief="flat", bd=0, padx=22, pady=10, cursor="hand2",
        )
        self.check_button.pack()

    def _build_game_tab(self):
        inner = tk.Frame(self.game_tab, bg=COLOR_BG_CARD)
        inner.pack(expand=True, fill="both", pady=16, padx=16)

        self.game_score_label = tk.Label(
            inner, font=("Segoe UI", 18, "bold"), bg=COLOR_BG_CARD, fg=COLOR_TEXT,
        )
        self.game_score_label.pack(pady=(4, 0))

        self.game_income_label = tk.Label(
            inner, font=FONT_BODY, bg=COLOR_BG_CARD, fg=COLOR_TEXT_MUTED,
        )
        self.game_income_label.pack(pady=(0, 14))

        self.game_click_button = tk.Button(
            inner, command=self._on_click, font=("Segoe UI", 16, "bold"),
            bg=COLOR_SUCCESS, fg="#1e1e2e", activebackground="#8fd68b", activeforeground="#1e1e2e",
            relief="flat", bd=0, width=16, height=3, cursor="hand2",
        )
        self.game_click_button.pack(pady=(0, 18))

        self.game_shop_label = tk.Label(
            inner, font=("Segoe UI", 11, "bold"), bg=COLOR_BG_CARD, fg=COLOR_TEXT,
        )
        self.game_shop_label.pack(pady=(0, 8))

        shop_frame = tk.Frame(inner, bg=COLOR_BG_CARD)
        shop_frame.pack(fill="x")

        self.buy_click_button = tk.Button(
            shop_frame, command=self._buy_click_upgrade, font=FONT_BODY,
            bg=COLOR_BG, fg=COLOR_TEXT, activebackground=COLOR_ACCENT_DARK,
            relief="flat", bd=0, padx=10, pady=8, cursor="hand2", justify="left", anchor="w",
        )
        self.buy_click_button.pack(fill="x", pady=4)

        self.buy_auto_button = tk.Button(
            shop_frame, command=self._buy_auto_upgrade, font=FONT_BODY,
            bg=COLOR_BG, fg=COLOR_TEXT, activebackground=COLOR_ACCENT_DARK,
            relief="flat", bd=0, padx=10, pady=8, cursor="hand2", justify="left", anchor="w",
        )
        self.buy_auto_button.pack(fill="x", pady=4)

        self._refresh_game_labels()

    def t(self, key: str) -> str:
        return TRANSLATIONS[self.lang][key]

    # --- Logika gry (Klikacz) ---

    def _click_upgrade_cost(self) -> int:
        return UPGRADE_CLICK_BASE_COST * (self.game["click_upgrade_level"] + 1)

    def _auto_upgrade_cost(self) -> int:
        return UPGRADE_AUTO_BASE_COST * (self.game["auto_upgrade_level"] + 1)

    def _on_click(self):
        self.game["score"] += self.game["click_power"]
        self._refresh_game_labels()

    def _buy_click_upgrade(self):
        cost = self._click_upgrade_cost()
        if self.game["score"] >= cost:
            self.game["score"] -= cost
            self.game["click_power"] += 1
            self.game["click_upgrade_level"] += 1
            self._refresh_game_labels()

    def _buy_auto_upgrade(self):
        cost = self._auto_upgrade_cost()
        if self.game["score"] >= cost:
            self.game["score"] -= cost
            self.game["auto_income"] += 1
            self.game["auto_upgrade_level"] += 1
            self._refresh_game_labels()

    def _refresh_game_labels(self):
        self.game_score_label.config(text=self.t("game_score_label").format(score=self.game["score"]))
        self.game_income_label.config(text=self.t("game_income_label").format(income=self.game["auto_income"]))
        self.game_shop_label.config(text=self.t("game_shop_title"))
        self.game_click_button.config(text=self.t("game_click_button"))
        self.buy_click_button.config(
            text=f"{self.t('game_upgrade_click')} (+1)  —  {self.t('game_buy_button')}: {self._click_upgrade_cost()}"
        )
        self.buy_auto_button.config(
            text=f"{self.t('game_upgrade_auto')} (+1/s)  —  {self.t('game_buy_button')}: {self._auto_upgrade_cost()}"
        )

    def _game_tick(self):
        if self.game["auto_income"] > 0:
            self.game["score"] += self.game["auto_income"]
            self._refresh_game_labels()
        save_game_state(self.game)
        self.root.after(1000, self._game_tick)

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
        self.version_badge.config(text=self.t("version_label").format(version=CURRENT_VERSION))
        self.check_button.config(text=self.t("check_button"))

        self.menubar.entryconfig(1, label=self.t("menu_file"))
        self.file_menu.entryconfig(0, label=self.t("menu_exit"))

        self.menubar.entryconfig(2, label=self.t("menu_settings"))
        self.settings_menu.entryconfig(0, label=self.t("menu_language"))

        self.menubar.entryconfig(3, label=self.t("menu_help"))
        self.help_menu.entryconfig(0, label=self.t("menu_about"))

        self.notebook.tab(0, text=self.t("tab_updates"))
        self.notebook.tab(1, text=self.t("tab_game"))
        self._refresh_game_labels()

    def show_about(self):
        text = self.t("about_text").format(version=CURRENT_VERSION)
        messagebox.showinfo(self.t("about_title"), text)

    def check_for_updates(self):
        self.check_button.config(state="disabled")
        self.status_label.config(text=self.t("checking"), fg=COLOR_TEXT_MUTED)
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
        self.status_label.config(text=self.t("check_failed"), fg=COLOR_ERROR)

    def _on_check_finished(self, latest_version: str, info: dict):
        self.check_button.config(state="normal")

        if is_update_available(latest_version):
            self.status_label.config(text=self.t("update_found").format(version=latest_version), fg=COLOR_SUCCESS)
            self.show_update_dialog(latest_version, info)
        else:
            self.status_label.config(text=self.t("up_to_date"), fg=COLOR_TEXT_MUTED)

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
        self.status_label.config(text=self.t("update_downloading"), fg=COLOR_TEXT_MUTED)
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
        self.status_label.config(text=self.t("update_failed_status"), fg=COLOR_ERROR)
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
