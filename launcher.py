"""Starts Editora PDFEdit and shows it in its own window.

This is the entry point of the .exe  (you can also run it directly: python launcher.py).

On Windows the app opens in a dedicated Microsoft Edge "app window" (no tabs or address bar).
The window pings the server while it is open; when it has been gone for a few minutes the
program quits by itself, so nothing keeps running in the background.
"""
import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

if sys.stdout is None:                       # windowed .exe: there is no console
    sys.stdout = sys.stderr = open(os.devnull, "w")

os.environ.setdefault("SECRET_KEY", secrets.token_hex(16))   # random key for each run

import heartbeat                               # noqa: E402
from waitress import serve                     # noqa: E402

HOST = "127.0.0.1"                             # only this computer can connect
PREFERRED_PORT = 5000
TITLE = "Editora PDFEdit"
FROZEN = bool(getattr(sys, "frozen", False))
IDLE_TIMEOUT = int(os.environ.get("EDITORA_IDLE_TIMEOUT", "180"))   # seconds without a ping


# ---------- small helpers ----------
def data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, TITLE)
    os.makedirs(path, exist_ok=True)
    return path


def setup_logging():
    if FROZEN:
        logging.basicConfig(filename=os.path.join(data_dir(), "app.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO)


def message_box(text, error=False):
    """A simple Windows message box (blocks until OK). Does nothing on other systems."""
    if os.name != "nt":
        return
    import ctypes
    flags = 0x10 if error else 0x40            # stop / information icon
    ctypes.windll.user32.MessageBoxW(None, text, TITLE, flags | 0x40000)   # 0x40000 = topmost


def pick_port(preferred=PREFERRED_PORT):
    """Use port 5000 if it is free, otherwise let the system choose a free one."""
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Could not find a free port.")


def already_running(port=PREFERRED_PORT):
    """True if another copy of this app is already serving on the usual port."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/ping", timeout=1) as r:
            return b"Editora PDFEdit" in r.read()
    except Exception:
        return False


def wait_until_ready(port):
    for _ in range(100):                       # up to ~10 seconds
        try:
            with socket.create_connection((HOST, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


# ---------- the window ----------
def browser_candidates():
    roots = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
             os.environ.get("LOCALAPPDATA")]
    for root in filter(None, roots):
        yield os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe")
    for root in filter(None, roots):
        yield os.path.join(root, "Google", "Chrome", "Application", "chrome.exe")


def open_app_window(url):
    """Open `url` in a chromeless Edge (or Chrome) window. Returns the process, or None."""
    browser = next((p for p in browser_candidates() if os.path.isfile(p)), None)
    if browser is None:
        return None
    profile = os.path.join(data_dir(), "window-profile")     # keeps this window separate
    os.makedirs(profile, exist_ok=True)
    args = [browser, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
            "--no-default-browser-check", "--disable-background-mode", "--window-size=1240,860"]
    try:
        return subprocess.Popen(args)
    except OSError:
        logging.exception("could not start the app window")
        return None


# ---------- shutting down ----------
def watchdog():
    """Quit when the page has stopped pinging (window closed)."""
    last_tick = time.monotonic()
    while True:
        time.sleep(5)
        now = time.monotonic()
        if now - last_tick > 30:               # the computer was asleep: give the page time to ping again
            heartbeat.beat()
        last_tick = now
        if heartbeat.seconds_since_last() > IDLE_TIMEOUT:
            logging.info("no page has pinged for %s s - quitting", IDLE_TIMEOUT)
            os._exit(0)


# ---------- main ----------
def main():
    if already_running():                      # second launch: just open another window
        url = f"http://{HOST}:{PREFERRED_PORT}"
        if os.name != "nt" or open_app_window(url) is None:
            webbrowser.open(url)
        return

    from app import app                        # imported late so SECRET_KEY is set first

    port = pick_port()
    url = f"http://{HOST}:{port}"
    print("=" * 56)
    print("  Editora PDFEdit is running")
    print(f"  Address : {url}")
    print("  To QUIT: close the app window (or press Ctrl+C).")
    print("=" * 56, flush=True)

    threading.Thread(target=lambda: serve(app, host=HOST, port=port, threads=8), daemon=True).start()
    heartbeat.beat()
    if not wait_until_ready(port):
        raise RuntimeError("The local server did not start.")
    if FROZEN or os.environ.get("EDITORA_WATCHDOG") == "1":
        threading.Thread(target=watchdog, daemon=True).start()

    if os.name == "nt":
        process = open_app_window(url)
        if process is not None:
            started = time.monotonic()
            process.wait()
            if time.monotonic() - started > 5:         # the user closed the window
                return
            # it ended at once: the window was handed to an already-running browser, keep serving
        else:
            webbrowser.open(url)
        message_box("Editora PDFEdit is running in your web browser.\n\n"
                    "Click OK to quit the app.")
        return

    webbrowser.open(url)                       # other systems (development): serve until Ctrl+C
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    setup_logging()
    try:
        main()
    except Exception:
        logging.exception("Editora PDFEdit crashed")
        message_box(f"Editora PDFEdit could not start.\n\nDetails were saved to:\n"
                    f"{os.path.join(data_dir(), 'app.log')}", error=True)
        sys.exit(1)
    os._exit(0)                                # also stops the server threads
