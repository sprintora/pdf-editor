"""The open page pings the server every few seconds. When the pings stop (window closed)
the packaged app shuts itself down - see launcher.py."""
import time

_last = time.monotonic()


def beat():
    global _last
    _last = time.monotonic()


def seconds_since_last():
    return time.monotonic() - _last
