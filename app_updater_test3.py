"""
Aplikacja z systemem sprawdzania aktualizacji + gra "Kot-Klikacz".

Jak działa aktualizacja:
- Aplikacja ma wpisaną własną wersję (CURRENT_VERSION).
- Po uruchomieniu łączy się przez HTTPS z plikiem index.json (hostowanym
  na GitHubie) i sprawdza najnowszą wersję.
- Okienko aktualizacji pokazuje się TYLKO wtedy, gdy dostępna jest
  wersja nowsza niż obecna.
- Po kliknięciu "AKTUALIZUJ" aplikacja pobiera nowy kod, robi kopię
  zapasową starego pliku, nadpisuje się i uruchamia ponownie.
"""

import ast
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
from urllib.request import urlopen
from urllib.error import URLError

CURRENT_VERSION = "1.9-test.3"
APP_NAME = "Kot-Klikacz"

# ---------------------------------------------------------------------------
# KONFIGURACJA AKTUALIZACJI
# ---------------------------------------------------------------------------

VERSION_CHECK_URL = "https://raw.githubusercontent.com/frostymeowz1605-sudo/game-updater/main/index.json"
TEST_MODE = False
LOCAL_VERSION_FILE = "version.json"
REQUEST_TIMEOUT_SECONDS = 10
MAX_SCRIPT_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

# ---------------------------------------------------------------------------
# KOLORY / MOTYW (styl "cute mobile game")
# ---------------------------------------------------------------------------

BG_APP = "#151515"
LEFT_PANEL_BG = "#2e2e2e"
RIGHT_PANEL_BG = "#e9caa0"
HEADER_WOOD = "#8a5a2e"
CARD_BG = "#f2ddb8"
CARD_BORDER = "#c9a26a"
STAT_BG = "#232323"
TEXT_LIGHT = "#ffffff"
TEXT_DARK = "#4a3520"
ACCENT_YELLOW = "#ffd54f"
BTN_GREEN = "#5cb860"
BTN_GREEN_DARK = "#4a9a4e"
BTN_GRAY = "#9e9e9e"
BTN_GRAY_DARK = "#828282"

FONT_STAT = ("Segoe UI", 13, "bold")
FONT_CARD_TITLE = ("Segoe UI", 12, "bold")
FONT_CARD_SUB = ("Segoe UI", 9)
FONT_HEADER = ("Segoe UI", 16, "bold")
FONT_POPUP_TITLE = ("Segoe UI", 18, "bold")
FONT_POPUP_BODY = ("Segoe UI", 10)

TRANSLATIONS = {
    "pl": {
        "upgrades_title": "ULEPSZENIA",
        "stat_clicks": "kliknięcia",
        "stat_autolevel": "poziom auto-klikacza",
        "upgrade_click_name": "lepszy klik",
        "upgrade_click_desc": "+1 klik",
        "upgrade_auto_name": "szybszy klik",
        "upgrade_auto_desc": "+1 klik/s",
        "upgrade_mega_name": "mega klik",
        "upgrade_mega_desc": "+5 klik/s",
        "update_title": "AKTUALIZACJA DOSTĘPNA!",
        "update_subtitle": "Dostępna jest nowa aktualizacja!",
        "update_body": "Nowe ulepszenia, poprawki i więcej zabawy!",
        "update_button": "AKTUALIZUJ",
        "update_later": "PÓŹNIEJ",
        "update_downloading": "Pobieranie aktualizacji...",
        "update_failed": "Aktualizacja nie powiodła się:\n{error}",
        "update_success": "Zaktualizowano! Aplikacja uruchomi się ponownie.",
        "menu_check_updates": "Sprawdź aktualizacje",
        "menu_language": "Język",
        "menu_exit": "Wyjście",
        "checking": "Sprawdzanie aktualizacji...",
        "up_to_date": "Masz najnowszą wersję.",
        "check_failed": "Brak połączenia z serwerem aktualizacji.",
    },
    "en": {
        "upgrades_title": "UPGRADES",
        "stat_clicks": "clicks",
        "stat_autolevel": "autoclicker level",
        "upgrade_click_name": "better click",
        "upgrade_click_desc": "+1 click",
        "upgrade_auto_name": "faster click",
        "upgrade_auto_desc": "+1 click/s",
        "upgrade_mega_name": "mega click",
        "upgrade_mega_desc": "+5 click/s",
        "update_title": "UPDATE AVAILABLE!",
        "update_subtitle": "A new update is available!",
        "update_body": "New upgrades, fixes and more fun!",
        "update_button": "UPDATE",
        "update_later": "LATER",
        "update_downloading": "Downloading update...",
        "update_failed": "Update failed:\n{error}",
        "update_success": "Updated! The app will restart.",
        "menu_check_updates": "Check for updates",
        "menu_language": "Language",
        "menu_exit": "Exit",
        "checking": "Checking for updates...",
        "up_to_date": "You have the latest version.",
        "check_failed": "No connection to the update server.",
    },
}

SETTINGS_FILE = "app_settings.json"
GAME_SAVE_FILE = "clicker_save.json"

UPGRADE_CLICK_BASE_COST = 10
UPGRADE_AUTO_BASE_COST = 50
UPGRADE_MEGA_BASE_COST = 250

# ---------------------------------------------------------------------------
# ZAPIS / ODCZYT DANYCH
# ---------------------------------------------------------------------------


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
        pass


def load_game_state() -> dict:
    default = {
        "clicks": 0, "coins": 0, "click_power": 1, "auto_income": 0,
        "click_upgrade_level": 0, "auto_upgrade_level": 0, "mega_upgrade_level": 0,
    }
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


# ---------------------------------------------------------------------------
# LOGIKA AKTUALIZACJI (bez zmian od poprzednich wersji)
# ---------------------------------------------------------------------------


def parse_version(version_str: str):
    import re
    numbers = re.findall(r"\d+", version_str)
    return tuple(int(n) for n in numbers) if numbers else (0,)


def fetch_latest_version_info() -> dict:
    if TEST_MODE:
        with open(LOCAL_VERSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    if not VERSION_CHECK_URL.startswith("https://"):
        raise ValueError("Ze względów bezpieczeństwa dozwolone jest tylko HTTPS.")

    context = ssl.create_default_context()
    with urlopen(VERSION_CHECK_URL, timeout=REQUEST_TIMEOUT_SECONDS, context=context) as response:
        data = response.read().decode("utf-8")
        return json.loads(data)


def is_update_available(latest_version: str) -> bool:
    return parse_version(latest_version) > parse_version(CURRENT_VERSION)


def download_new_script(script_url: str) -> str:
    if not script_url.startswith("https://"):
        raise ValueError("Ze względów bezpieczeństwa dozwolone jest tylko HTTPS.")

    context = ssl.create_default_context()
    with urlopen(script_url, timeout=REQUEST_TIMEOUT_SECONDS, context=context) as response:
        raw = response.read(MAX_SCRIPT_SIZE_BYTES + 1)

    if len(raw) > MAX_SCRIPT_SIZE_BYTES:
        raise ValueError("Pobrany plik jest podejrzanie duży - przerwano aktualizację.")

    text = raw.decode("utf-8")
    ast.parse(text)  # walidacja, że to poprawny kod Pythona
    return text


def apply_update(new_source_code: str) -> str:
    current_file = os.path.abspath(__file__)
    backup_file = current_file + ".backup"
    shutil.copy2(current_file, backup_file)
    try:
        with open(current_file, "w", encoding="utf-8") as f:
            f.write(new_source_code)
    except Exception:
        shutil.copy2(backup_file, current_file)
        raise
    return backup_file


def restart_application():
    subprocess.Popen([sys.executable, os.path.abspath(__file__)])
    sys.exit(0)


# ---------------------------------------------------------------------------
# POMOCNICZE: zaokrąglone prostokąty na Canvas
# ---------------------------------------------------------------------------


def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius=18, **kwargs):
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# ---------------------------------------------------------------------------
# OKIENKO AKTUALIZACJI (styl kartonowo-drewniany, jak w grach mobilnych)
# ---------------------------------------------------------------------------


class UpdateDialog(tk.Toplevel):
    def __init__(self, parent, lang: str, notes: str, on_update, on_later):
        super().__init__(parent)
        self.t = TRANSLATIONS[lang]
        self.on_update = on_update
        self.on_later = on_later

        self.overrideredirect(True)
        self.configure(bg=BG_APP)
        width, height = 460, 420
        parent.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + (pw - width) // 2
        y = py + (ph - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.grab_set()

        canvas = tk.Canvas(self, width=width, height=height, bg=BG_APP, highlightthickness=0)
        canvas.pack()

        rounded_rect(canvas, 10, 10, width - 10, height - 10, radius=26, fill=CARD_BG, outline=CARD_BORDER, width=3)
        rounded_rect(canvas, 10, 10, width - 10, 90, radius=26, fill=HEADER_WOOD, outline=CARD_BORDER, width=3)
        canvas.create_rectangle(10, 70, width - 10, 90, fill=HEADER_WOOD, outline=HEADER_WOOD)

        canvas.create_text(width // 2, 50, text=self.t["update_title"], font=FONT_POPUP_TITLE, fill=TEXT_LIGHT)

        close_btn = canvas.create_oval(width - 46, 16, width - 16, 46, fill="#e05656", outline="")
        close_txt = canvas.create_text(width - 31, 31, text="✕", font=("Segoe UI", 12, "bold"), fill=TEXT_LIGHT)
        canvas.tag_bind(close_btn, "<Button-1>", lambda e: self._close())
        canvas.tag_bind(close_txt, "<Button-1>", lambda e: self._close())

        canvas.create_text(width // 2, 150, text="🐱", font=("Segoe UI Emoji", 70))

        canvas.create_text(
            width // 2, 235, text=self.t["update_subtitle"], font=("Segoe UI", 12, "bold"), fill=TEXT_DARK
        )
        body = notes.replace("\\n", "\n") if notes else self.t["update_body"]
        canvas.create_text(
            width // 2, 265, text=body, font=FONT_POPUP_BODY, fill=TEXT_DARK, width=380, justify="center"
        )

        self.status_text_id = canvas.create_text(
            width // 2, 320, text="", font=("Segoe UI", 9), fill=TEXT_DARK
        )
        self.canvas = canvas

        update_btn = rounded_rect(canvas, 60, 350, 260, 396, radius=18, fill=BTN_GREEN, outline="")
        update_txt = canvas.create_text(160, 373, text=f"{self.t['update_button']}  ⬇", font=("Segoe UI", 12, "bold"), fill=TEXT_LIGHT)
        for item in (update_btn, update_txt):
            canvas.tag_bind(item, "<Button-1>", lambda e: self._do_update())
            canvas.tag_bind(item, "<Enter>", lambda e: canvas.itemconfig(update_btn, fill=BTN_GREEN_DARK))
            canvas.tag_bind(item, "<Leave>", lambda e: canvas.itemconfig(update_btn, fill=BTN_GREEN))

        later_btn = rounded_rect(canvas, 280, 350, 400, 396, radius=18, fill=BTN_GRAY, outline="")
        later_txt = canvas.create_text(340, 373, text=self.t["update_later"], font=("Segoe UI", 12, "bold"), fill=TEXT_LIGHT)
        for item in (later_btn, later_txt):
            canvas.tag_bind(item, "<Button-1>", lambda e: self._close())
            canvas.tag_bind(item, "<Enter>", lambda e: canvas.itemconfig(later_btn, fill=BTN_GRAY_DARK))
            canvas.tag_bind(item, "<Leave>", lambda e: canvas.itemconfig(later_btn, fill=BTN_GRAY))

        self.update_btn_items = (update_btn, update_txt)

    def set_status(self, text: str):
        self.canvas.itemconfig(self.status_text_id, text=text)

    def _do_update(self):
        self.set_status(self.t["update_downloading"])
        for item in self.update_btn_items:
            self.canvas.itemconfig(item, state="disabled")
        self.on_update(self)

    def _close(self):
        self.on_later()
        self.destroy()


# ---------------------------------------------------------------------------
# GŁÓWNE OKNO GRY
# ---------------------------------------------------------------------------


class ClickerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = load_settings()
        self.lang = self.settings.get("language", "pl")
        self.game = load_game_state()
        self.update_dialog = None
        self.latest_info = {}

        self.root.title(APP_NAME)
        self.root.geometry("760x520")
        self.root.resizable(False, False)
        self.root.configure(bg=BG_APP)

        self.canvas = tk.Canvas(self.root, width=760, height=520, bg=BG_APP, highlightthickness=0)
        self.canvas.pack()

        self._draw_static_layout()
        self._draw_upgrade_cards()
        self._draw_stats()
        self._draw_cat()
        self._draw_gear()

        self.root.after(700, self.check_for_updates)
        self._game_tick()

    def t(self, key):
        return TRANSLATIONS[self.lang][key]

    # --- Statyczny układ (panele) ---

    def _draw_static_layout(self):
        rounded_rect(self.canvas, 14, 14, 500, 506, radius=28, fill=LEFT_PANEL_BG, outline="")
        rounded_rect(self.canvas, 516, 14, 746, 506, radius=22, fill=RIGHT_PANEL_BG, outline="")
        rounded_rect(self.canvas, 516, 20, 746, 76, radius=20, fill=HEADER_WOOD, outline="")
        self.canvas.create_text(631, 48, text=self.t("upgrades_title"), font=FONT_HEADER, fill=TEXT_LIGHT)
        self.header_text_id = None  # przypisane wyżej pośrednio

    def _draw_gear(self):
        gear = self.canvas.create_oval(28, 28, 74, 74, fill=STAT_BG, outline="")
        gear_txt = self.canvas.create_text(51, 51, text="⚙", font=("Segoe UI", 20), fill=ACCENT_YELLOW)
        for item in (gear, gear_txt):
            self.canvas.tag_bind(item, "<Button-1>", self._open_settings_menu)

    def _open_settings_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=self.t("menu_check_updates"), command=self.check_for_updates)
        lang_menu = tk.Menu(menu, tearoff=0)
        lang_menu.add_command(label="Polski", command=lambda: self.set_language("pl"))
        lang_menu.add_command(label="English", command=lambda: self.set_language("en"))
        menu.add_cascade(label=self.t("menu_language"), menu=lang_menu)
        menu.add_separator()
        menu.add_command(label=self.t("menu_exit"), command=self.root.quit)
        menu.tk_popup(event.x_root, event.y_root)

    def set_language(self, lang_code):
        self.lang = lang_code
        self.settings["language"] = lang_code
        save_settings(self.settings)
        self.canvas.delete("all")
        self._draw_static_layout()
        self._draw_upgrade_cards()
        self._draw_stats()
        self._draw_cat()
        self._draw_gear()

    # --- Kot (klikalna postać) ---

    def _draw_cat(self):
        self.cat_glow = self.canvas.create_oval(150, 130, 370, 350, fill="", outline="")
        self.cat = self.canvas.create_text(260, 240, text="🐱", font=("Segoe UI Emoji", 130))
        self.canvas.tag_bind(self.cat, "<Button-1>", self._on_click)
        self.canvas.tag_bind(self.cat, "<Enter>", lambda e: self.canvas.config(cursor="hand2"))
        self.canvas.tag_bind(self.cat, "<Leave>", lambda e: self.canvas.config(cursor=""))

    def _on_click(self, event):
        self.game["clicks"] += 1
        self.game["coins"] += self.game["click_power"]
        # mała animacja "podskoku"
        self.canvas.move(self.cat, 0, -6)
        self.root.after(70, lambda: self.canvas.move(self.cat, 0, 6))
        self._refresh_stats()
        self._refresh_upgrade_cards()

    # --- Statystyki dolne (lewy panel) ---

    def _draw_stats(self):
        rounded_rect(self.canvas, 30, 400, 250, 450, radius=16, fill=STAT_BG, outline="")
        self.clicks_icon = self.canvas.create_text(55, 425, text="👆", font=("Segoe UI Emoji", 16))
        self.clicks_text = self.canvas.create_text(150, 425, text="", font=FONT_STAT, fill=TEXT_LIGHT, anchor="w")

        rounded_rect(self.canvas, 30, 458, 300, 494, radius=14, fill=STAT_BG, outline="")
        self.autolvl_icon = self.canvas.create_text(50, 476, text="🖱️", font=("Segoe UI Emoji", 13))
        self.autolvl_text = self.canvas.create_text(150, 476, text="", font=("Segoe UI", 11, "bold"), fill=TEXT_LIGHT, anchor="w")

        rounded_rect(self.canvas, 620, 458, 730, 494, radius=14, fill=STAT_BG, outline="")
        self.coin_icon = self.canvas.create_text(640, 476, text="🪙", font=("Segoe UI Emoji", 13))
        self.coin_text = self.canvas.create_text(660, 476, text="", font=("Segoe UI", 12, "bold"), fill=ACCENT_YELLOW, anchor="w")

        self._refresh_stats()

    def _refresh_stats(self):
        self.canvas.itemconfig(self.clicks_text, text=f"{self.t('stat_clicks')}: {self.game['clicks']}")
        self.canvas.itemconfig(self.autolvl_text, text=f"{self.t('stat_autolevel')}: {self.game['auto_upgrade_level'] + self.game['mega_upgrade_level']}")
        self.canvas.itemconfig(self.coin_text, text=f"{self.game['coins']}")

    # --- Karty ulepszeń (prawy panel) ---

    def _upgrade_defs(self):
        return [
            ("click", self.t("upgrade_click_name"), self.t("upgrade_click_desc"),
             UPGRADE_CLICK_BASE_COST * (self.game["click_upgrade_level"] + 1), "🖱️"),
            ("auto", self.t("upgrade_auto_name"), self.t("upgrade_auto_desc"),
             UPGRADE_AUTO_BASE_COST * (self.game["auto_upgrade_level"] + 1), "🖱️"),
            ("mega", self.t("upgrade_mega_name"), self.t("upgrade_mega_desc"),
             UPGRADE_MEGA_BASE_COST * (self.game["mega_upgrade_level"] + 1), "✨"),
        ]

    def _draw_upgrade_cards(self):
        self.upgrade_items = []
        y = 96
        for key, name, desc, cost, icon in self._upgrade_defs():
            card_bg = rounded_rect(self.canvas, 528, y, 734, y + 76, radius=16, fill=CARD_BG, outline=CARD_BORDER, width=2)
            icon_id = self.canvas.create_text(552, y + 38, text=icon, font=("Segoe UI Emoji", 22))
            name_id = self.canvas.create_text(578, y + 24, text=name, font=FONT_CARD_TITLE, fill=TEXT_DARK, anchor="w")
            desc_id = self.canvas.create_text(578, y + 48, text=desc, font=FONT_CARD_SUB, fill=TEXT_DARK, anchor="w")

            btn_bg = rounded_rect(self.canvas, 650, y + 20, 718, y + 56, radius=14, fill=BTN_GREEN, outline="")
            btn_txt = self.canvas.create_text(684, y + 38, text=str(cost), font=("Segoe UI", 11, "bold"), fill=TEXT_LIGHT)

            for item in (btn_bg, btn_txt):
                self.canvas.tag_bind(item, "<Button-1>", lambda e, k=key: self._buy_upgrade(k))
                self.canvas.tag_bind(item, "<Enter>", lambda e, b=btn_bg: self.canvas.itemconfig(b, fill=BTN_GREEN_DARK))
                self.canvas.tag_bind(item, "<Leave>", lambda e, b=btn_bg: self.canvas.itemconfig(b, fill=BTN_GREEN))

            self.upgrade_items.append({"key": key, "btn_txt": btn_txt, "btn_bg": btn_bg})
            y += 92

    def _refresh_upgrade_cards(self):
        defs = {d[0]: d for d in self._upgrade_defs()}
        for item in self.upgrade_items:
            cost = defs[item["key"]][3]
            self.canvas.itemconfig(item["btn_txt"], text=str(cost))
            can_afford = self.game["coins"] >= cost
            fill = BTN_GREEN if can_afford else BTN_GRAY
            self.canvas.itemconfig(item["btn_bg"], fill=fill)
        self._refresh_stats()

    def _buy_upgrade(self, key):
        defs = {d[0]: d for d in self._upgrade_defs()}
        cost = defs[key][3]
        if self.game["coins"] < cost:
            return
        self.game["coins"] -= cost
        if key == "click":
            self.game["click_power"] += 1
            self.game["click_upgrade_level"] += 1
        elif key == "auto":
            self.game["auto_income"] += 1
            self.game["auto_upgrade_level"] += 1
        elif key == "mega":
            self.game["auto_income"] += 5
            self.game["mega_upgrade_level"] += 1
        self._refresh_upgrade_cards()

    def _game_tick(self):
        if self.game["auto_income"] > 0:
            self.game["coins"] += self.game["auto_income"]
            self._refresh_upgrade_cards()
        save_game_state(self.game)
        self.root.after(1000, self._game_tick)

    # --- Sprawdzanie / stosowanie aktualizacji ---

    def check_for_updates(self):
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        try:
            info = fetch_latest_version_info()
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            return
        latest_version = str(info.get("version", CURRENT_VERSION))
        if is_update_available(latest_version):
            self.latest_info = info
            self.root.after(0, self._show_update_dialog, info)

    def _show_update_dialog(self, info: dict):
        if self.update_dialog is not None:
            return
        notes = info.get("notes", "")
        self.update_dialog = UpdateDialog(
            self.root, self.lang, notes,
            on_update=self._start_update,
            on_later=self._dismiss_update_dialog,
        )

    def _dismiss_update_dialog(self):
        self.update_dialog = None

    def _start_update(self, dialog: UpdateDialog):
        script_url = self.latest_info.get("script_url", "")
        threading.Thread(target=self._update_worker, args=(dialog, script_url), daemon=True).start()

    def _update_worker(self, dialog: UpdateDialog, script_url: str):
        try:
            new_code = download_new_script(script_url)
            apply_update(new_code)
        except Exception as e:
            self.root.after(0, dialog.set_status, self.t("update_failed").format(error=str(e)))
            return
        self.root.after(0, dialog.set_status, self.t("update_success"))
        self.root.after(1200, restart_application)


def main():
    root = tk.Tk()
    ClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
