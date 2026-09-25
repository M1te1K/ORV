"""
ORVI Simulator - шуточная программа, имитирующая симптомы простуды на компьютере.

Раз в 10-15 секунд случайно выполняется одно из трёх "действий" (по ~33.3% каждое):
  - чих: открывается случайное приложение (браузер, диспетчер задач, экранная клавиатура, проводник)
  - кашель: все видимые окна на экране на секунду начинают "трястись"
  - сморкание: системная громкость случайно немного повышается или понижается

Дополнительно, независимо от основного действия, есть небольшой шанс "поднятия температуры" -
экран на несколько секунд слегка подсвечивается красным.

При первом запуске программа добавляет себя в автозапуск текущего пользователя
(ключ реестра HKCU / Software / Microsoft / Windows / CurrentVersion / Run, без прав
администратора) - это видно и снимается стандартными средствами Windows: вкладка
"Автозагрузка" в Диспетчере задач, msconfig, regedit, Autoruns (Sysinternals).

Остановить запущенный сейчас процесс: горячая клавиша Ctrl+Alt+Shift+Q, либо завершение
процесса через Диспетчер задач (имя процесса - ORVISimulator.exe после сборки).

Убрать из автозапуска насовсем: запустить `ORVISimulator.exe --uninstall`
(удаляет только запись автозапуска, ничего больше не меняет и не удаляет).

ВАЖНО: предназначено только для запуска на собственном компьютере либо на компьютере
человека, который знает и согласен на розыгрыш. Программа не скрывает и не маскирует
запись автозапуска, не устанавливается как служба, не пытается противодействовать
удалению и не собирает никакие данные - только визуальные/звуковые эффекты и одна
обычная запись в пользовательском автозапуске.
"""

import ctypes
import ctypes.wintypes as wintypes
import itertools
import os
import random
import subprocess
import sys
import threading
import time
import webbrowser
import winreg

import win32api
import win32con
import win32event
import win32gui

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------

INTERVAL_MIN_SEC = 3.0
INTERVAL_MAX_SEC = 7.0

FEVER_CHANCE = 0.18          # шанс дополнительного эффекта "температуры" в каждом цикле
COUGH_SHAKE_DURATION = 1.2   # сколько секунд "трясётся" экран при кашле
COUGH_SHAKE_AMPLITUDE = 10   # амплитуда дрожания окон в пикселях

FEVER_MIN_DURATION = 2.5
FEVER_MAX_DURATION = 4.5
FEVER_MIN_ALPHA = 0.12
FEVER_MAX_ALPHA = 0.30

VOLUME_PRESSES_MIN = 4
VOLUME_PRESSES_MAX = 9

INTERNAL_WINDOW_MARK = "__orvi_internal__"

MUTEX_NAME = "Global\\ORVISimulator_SingleInstance_Mutex"

QUIT_HOTKEY_ID = 1
QUIT_MODIFIERS = win32con.MOD_CONTROL | win32con.MOD_ALT | win32con.MOD_SHIFT
QUIT_VK = ord("Q")

# Классы окон, которые нельзя трогать при "кашле" (таскбар, рабочий стол и т.п.)
SHAKE_CLASS_BLACKLIST = {
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Progman",
    "WorkerW",
    "Button",
    "NotifyIconOverflowWindow",
    "Windows.UI.Core.CoreWindow",
}

stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Автозапуск: HKCU\...\Run (только текущий пользователь, без прав администратора)
# ---------------------------------------------------------------------------

AUTOSTART_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = "ORVISimulator"


def _get_exe_path():
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(__file__)


def _autostart_command():
    return f'"{_get_exe_path()}"'


def is_autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
            return value == _autostart_command()
    except OSError:
        return False


def enable_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, _autostart_command())
    except OSError:
        pass


def disable_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Звук: проигрывание mp3 через MCI (winmm.dll), без сторонних библиотек
# ---------------------------------------------------------------------------

def _resource_path(relative_path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


SNEEZE_SOUND = _resource_path(os.path.join("sounds", "sneeze.mp3"))
COUGH_SOUND = _resource_path(os.path.join("sounds", "cough.mp3"))
BLOW_NOSE_SOUND = _resource_path(os.path.join("sounds", "blow_nose.mp3"))

_sound_alias_counter = itertools.count()
_MAX_SOUND_LIFETIME_SEC = 8.0  # с запасом дольше самого длинного звука


def _play_sound_async(path):
    if not os.path.isfile(path):
        return

    alias = f"orvisound{next(_sound_alias_counter)}"
    winmm = ctypes.windll.winmm

    try:
        winmm.mciSendStringW(f'open "{path}" type mpegvideo alias {alias}', None, 0, None)
        winmm.mciSendStringW(f"play {alias}", None, 0, None)
    except Exception:
        return

    def _cleanup():
        time.sleep(_MAX_SOUND_LIFETIME_SEC)
        try:
            winmm.mciSendStringW(f"close {alias}", None, 0, None)
        except Exception:
            pass

    threading.Thread(target=_cleanup, daemon=True).start()


# ---------------------------------------------------------------------------
# Чих: открыть случайное приложение
# ---------------------------------------------------------------------------

def _open_default_browser():
    webbrowser.open("about:blank")


def _open_task_manager():
    subprocess.Popen(["taskmgr.exe"], shell=False)


def _open_onscreen_keyboard():
    subprocess.Popen(["osk.exe"], shell=False)


def _open_explorer():
    subprocess.Popen(["explorer.exe"], shell=False)


SNEEZE_ACTIONS = [
    _open_default_browser,
    _open_task_manager,
    _open_onscreen_keyboard,
    _open_explorer,
]


def do_sneeze():
    _play_sound_async(SNEEZE_SOUND)
    action = random.choice(SNEEZE_ACTIONS)
    try:
        action()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Кашель: дрожание экрана (дрожат все видимые окна)
# ---------------------------------------------------------------------------

def _enum_shakeable_windows():
    windows = []

    def callback(hwnd, _extra):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if win32gui.IsIconic(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title or title.startswith(INTERNAL_WINDOW_MARK):
            return True
        try:
            cls = win32gui.GetClassName(hwnd)
        except Exception:
            return True
        if cls in SHAKE_CLASS_BLACKLIST:
            return True
        windows.append(hwnd)
        return True

    win32gui.EnumWindows(callback, None)
    return windows


def do_cough():
    _play_sound_async(COUGH_SOUND)
    windows = _enum_shakeable_windows()
    if not windows:
        return

    originals = {}
    for hwnd in windows:
        try:
            originals[hwnd] = win32gui.GetWindowRect(hwnd)
        except Exception:
            pass

    if not originals:
        return

    end_time = time.time() + COUGH_SHAKE_DURATION
    while time.time() < end_time and not stop_event.is_set():
        for hwnd, (left, top, _right, _bottom) in originals.items():
            try:
                dx = random.randint(-COUGH_SHAKE_AMPLITUDE, COUGH_SHAKE_AMPLITUDE)
                dy = random.randint(-COUGH_SHAKE_AMPLITUDE, COUGH_SHAKE_AMPLITUDE)
                win32gui.SetWindowPos(
                    hwnd, None, left + dx, top + dy, 0, 0,
                    win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
                )
            except Exception:
                pass
        time.sleep(0.03)

    for hwnd, (left, top, _right, _bottom) in originals.items():
        try:
            win32gui.SetWindowPos(
                hwnd, None, left, top, 0, 0,
                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Сморкание: изменить громкость
# ---------------------------------------------------------------------------

VK_VOLUME_UP = 0xAF
VK_VOLUME_DOWN = 0xAE


def do_blow_nose():
    _play_sound_async(BLOW_NOSE_SOUND)
    key = random.choice([VK_VOLUME_UP, VK_VOLUME_DOWN])
    presses = random.randint(VOLUME_PRESSES_MIN, VOLUME_PRESSES_MAX)
    for _ in range(presses):
        if stop_event.is_set():
            return
        win32api.keybd_event(key, 0, 0, 0)
        win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# "Температура": лёгкая красная подсветка экрана
# ---------------------------------------------------------------------------

def do_fever():
    import tkinter as tk

    duration = random.uniform(FEVER_MIN_DURATION, FEVER_MAX_DURATION)
    max_alpha = random.uniform(FEVER_MIN_ALPHA, FEVER_MAX_ALPHA)

    root = tk.Tk()
    root.title(INTERNAL_WINDOW_MARK + "fever")
    try:
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        root.geometry(f"{screen_w}x{screen_h}+0+0")
        root.configure(bg="red")
        root.attributes("-alpha", 0.0)

        # Клики не должны мешать работе - окно не активируется и не получает фокус.
        steps = 20
        half = max(duration / 2.0, 0.1)

        for i in range(steps + 1):
            if stop_event.is_set():
                break
            alpha = max_alpha * (i / steps)
            root.attributes("-alpha", alpha)
            root.update()
            time.sleep(half / steps)

        if not stop_event.is_set():
            time.sleep(0.2)

        for i in range(steps, -1, -1):
            if stop_event.is_set():
                break
            alpha = max_alpha * (i / steps)
            root.attributes("-alpha", alpha)
            root.update()
            time.sleep(half / steps)
    except Exception:
        pass
    finally:
        try:
            root.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Горячая клавиша для выхода: Ctrl+Alt+Shift+Q
# ---------------------------------------------------------------------------

def hotkey_listener():
    user32 = ctypes.windll.user32

    if not user32.RegisterHotKey(None, QUIT_HOTKEY_ID, QUIT_MODIFIERS, QUIT_VK):
        return

    try:
        msg = wintypes.MSG()
        while not stop_event.is_set():
            result = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)  # PM_REMOVE
            if result:
                if msg.message == win32con.WM_HOTKEY:
                    stop_event.set()
                    break
            time.sleep(0.1)
    finally:
        user32.UnregisterHotKey(None, QUIT_HOTKEY_ID)


# ---------------------------------------------------------------------------
# Основной цикл
# ---------------------------------------------------------------------------

def scheduler_loop():
    actions = [do_sneeze, do_cough, do_blow_nose]

    while not stop_event.is_set():
        wait_time = random.uniform(INTERVAL_MIN_SEC, INTERVAL_MAX_SEC)
        if stop_event.wait(wait_time):
            break

        action = random.choice(actions)
        try:
            action()
        except Exception:
            pass

        if stop_event.is_set():
            break

        if random.random() < FEVER_CHANCE:
            try:
                do_fever()
            except Exception:
                pass


def acquire_single_instance_lock():
    mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    last_error = win32api.GetLastError()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        return None
    return mutex


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("--uninstall", "/uninstall", "-u"):
        disable_autostart()
        sys.exit(0)

    mutex = acquire_single_instance_lock()
    if mutex is None:
        sys.exit(0)

    if not is_autostart_enabled():
        enable_autostart()

    listener = threading.Thread(target=hotkey_listener, daemon=True)
    listener.start()

    scheduler_loop()


if __name__ == "__main__":
    main()
