"""PyInstaller runtime hook — captures startup crashes into crash.log.

PyInstaller onedir builds may leave __file__ as None for the entry-point
script, which crashes app.py's module-level BASE_DIR computation. This
hook patches __file__ early and installs a top-level exception handler
that writes the traceback next to the executable.
"""
import os
import sys
import traceback

_EXE_DIR = os.path.dirname(sys.executable)

# ── Patch __file__ for the main module ───────────────────────────────────
# app.py line 30: BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Without this, os.path.abspath(None) raises TypeError on import.
import __main__

if getattr(sys, 'frozen', False):
    if not getattr(__main__, '__file__', None):
        __main__.__file__ = os.path.join(_EXE_DIR, 'app.py')

# ── Crash logger ─────────────────────────────────────────────────────────
def _crash_log(exc_type, exc_value, exc_tb):
    log_path = os.path.join(_EXE_DIR, 'crash.log')
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(f"Mortgage Work — startup crash\n")
        f.write(f"sys.executable = {sys.executable}\n")
        f.write(f"sys._MEIPASS   = {getattr(sys, '_MEIPASS', 'N/A')}\n")
        f.write(f"cwd            = {os.getcwd()}\n")
        f.write(f"\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)

sys.excepthook = _crash_log
