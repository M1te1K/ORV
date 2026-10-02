#!/usr/bin/env python3
"""
ORVI Simulator (macOS) - шуточная программа, имитирующая симптомы простуды на компьютере.

Каждые 3-7 секунд случайно (по ~33.3%) выполняется одно из трёх действий:
  - чих: проигрывается звук и открывается случайное приложение (браузер по умолчанию,
    Мониторинг системы, Универсальный доступ > Экранная клавиатура, Finder)
  - кашель: все видимые окна на экране примерно на 1.2 секунды "трясутся"
  - сморкание: системная громкость случайно немного повышается или понижается

Дополнительно, независимо от основного действия, с шансом ~18% в каждом цикле включается
эффект "температуры" - экран на несколько секунд слегка подсвечивается красным.

ТРЕБОВАНИЯ:
  - macOS, Python 3 (встроен в систему, либо python.org/Homebrew)
  - для "кашля" (дрожание окон через System Events) нужно один раз выдать разрешение
    Accessibility тому процессу, который запускает скрипт (обычно Terminal/iTerm,
    либо интерпретатору python3) в System Settings -> Privacy & Security -> Accessibility.
    Без этого разрешения кашель просто не подвигает окна (тихо игнорируется).
  - звук воспроизводится через встроенную утилиту afplay - ничего ставить не нужно.

ЗАПУСК:  python3 orvi_mac.py   (или дважды кликнуть Start_ORVI.command)

ОСТАНОВКА (любой вариант):
  - дважды кликнуть Stop_ORVI.command
  - в терминале: pkill -f orvi_mac.py
  - Ctrl+C, если скрипт запущен в терминале на переднем плане

ВАЖНО: предназначено только для запуска на собственном компьютере либо на компьютере
человека, который знает и согласен на розыгрыш. Эта версия не добавляет себя в
автозапуск - запускается только вручную.
"""

import fcntl
import os
import random
import subprocess
import sys
import threading
import time

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------

INTERVAL_MIN_SEC = 3.0
INTERVAL_MAX_SEC = 7.0

FEVER_CHANCE = 0.18
COUGH_SHAKE_DURATION = 1.2
COUGH_SHAKE_AMPLITUDE = 10  # пикселей

FEVER_MIN_DURATION = 2.5
FEVER_MAX_DURATION = 4.5
FEVER_MIN_ALPHA = 0.12
FEVER_MAX_ALPHA = 0.30

VOLUME_DELTA_MIN = 8
VOLUME_DELTA_MAX = 20

APP_SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/ORVISimulator")
LOCK_PATH = os.path.join(APP_SUPPORT_DIR, "orvi.lock")
STOP_FLAG_PATH = os.path.join(APP_SUPPORT_DIR, "orvi.stop")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOUNDS_DIR = os.path.join(SCRIPT_DIR, "sounds")

stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Звук: afplay (встроенная утилита macOS, понимает mp3/wav и т.д.)
# ---------------------------------------------------------------------------

def _play_sound_async(filename):
    path = os.path.join(SOUNDS_DIR, filename)
    if not os.path.isfile(path):
        return
    try:
        subprocess.Popen(
            ["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Чих: открыть случайное приложение
# ---------------------------------------------------------------------------

def _open_default_browser():
    subprocess.Popen(["open", "about:blank"])


def _open_activity_monitor():
    subprocess.Popen(["open", "-a", "Activity Monitor"])


def _open_accessibility_keyboard():
    subprocess.Popen(["open", "-a", "Accessibility Keyboard"])


def _open_finder():
    subprocess.Popen(["open", "-a", "Finder", os.path.expanduser("~")])


SNEEZE_ACTIONS = [
    _open_default_browser,
    _open_activity_monitor,
    _open_accessibility_keyboard,
    _open_finder,
]


def do_sneeze():
    _play_sound_async("sneeze.mp3")
    action = random.choice(SNEEZE_ACTIONS)
    try:
        action()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Кашель: дрожание окон через System Events (AppleScript / UI scripting)
# ---------------------------------------------------------------------------

_COUGH_APPLESCRIPT = """
on run
    set stepCount to 18
    set amp to %d
    tell application "System Events"
        set targetWins to {}
        set origPos to {}
        repeat with proc in (every process whose background only is false)
            try
                set w to window 1 of proc
                set end of targetWins to w
                set end of origPos to (position of w)
            end try
        end repeat
        repeat stepCount times
            repeat with i from 1 to count of targetWins
                try
                    set w to item i of targetWins
                    set {ox, oy} to item i of origPos
                    set dx to (random number from -amp to amp)
                    set dy to (random number from -amp to amp)
                    set position of w to {ox + dx, oy + dy}
                end try
            end repeat
            delay 0.06
        end repeat
        repeat with i from 1 to count of targetWins
            try
                set w to item i of targetWins
                set position of w to (item i of origPos)
            end try
        end repeat
    end tell
end run
"""


def do_cough():
    _play_sound_async("cough.mp3")
    script = _COUGH_APPLESCRIPT % COUGH_SHAKE_AMPLITUDE
    try:
        subprocess.run(
            ["osascript", "-e", script],
            timeout=COUGH_SHAKE_DURATION + 5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Сморкание: изменить громкость
# ---------------------------------------------------------------------------

def _get_volume():
    try:
        out = subprocess.run(
            ["osascript", "-e", "output volume of (get volume settings)"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return int(out.stdout.strip())
    except Exception:
        return 50


def do_blow_nose():
    _play_sound_async("blow_nose.mp3")
    current = _get_volume()
    delta = random.randint(VOLUME_DELTA_MIN, VOLUME_DELTA_MAX)
    if random.random() < 0.5:
        delta = -delta
    new_volume = max(0, min(100, current + delta))
    try:
        subprocess.run(
            ["osascript", "-e", f"set volume output volume {new_volume}"],
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# "Температура": лёгкая красная подсветка экрана (tkinter)
# ---------------------------------------------------------------------------

def do_fever():
    try:
        import tkinter as tk
    except ImportError:
        return

    duration = random.uniform(FEVER_MIN_DURATION, FEVER_MAX_DURATION)
    max_alpha = random.uniform(FEVER_MIN_ALPHA, FEVER_MAX_ALPHA)

    root = tk.Tk()
    try:
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        root.geometry(f"{screen_w}x{screen_h}+0+0")
        root.configure(bg="red")
        root.attributes("-alpha", 0.0)

        steps = 20
        half = max(duration / 2.0, 0.1)

        for i in range(steps + 1):
            if stop_event.is_set():
                break
            root.attributes("-alpha", max_alpha * (i / steps))
            root.update()
            time.sleep(half / steps)

        if not stop_event.is_set():
            time.sleep(0.2)

        for i in range(steps, -1, -1):
            if stop_event.is_set():
                break
            root.attributes("-alpha", max_alpha * (i / steps))
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
# Остановка по стоп-файлу (см. Stop_ORVI.command)
# ---------------------------------------------------------------------------

def stop_flag_watcher():
    while not stop_event.is_set():
        if os.path.isfile(STOP_FLAG_PATH):
            try:
                os.remove(STOP_FLAG_PATH)
            except OSError:
                pass
            stop_event.set()
            break
        time.sleep(0.5)


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
    os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
    lock_file = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return lock_file  # держим файл открытым, чтобы лок не снимался


def main():
    lock = acquire_single_instance_lock()
    if lock is None:
        sys.exit(0)

    watcher = threading.Thread(target=stop_flag_watcher, daemon=True)
    watcher.start()

    scheduler_loop()


if __name__ == "__main__":
    main()
