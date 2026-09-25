"""
App identity for Wisperno Pro - every name Windows uses to tell apps apart,
in one place, all different from the original Wisperno so the two install
and run side by side without either one touching the other:

  - installer AppId (installer/setup.iss): a different GUID, so installing
    Wisperno Pro never "upgrades" or replaces an installed Wisperno
  - executable, install folder, Start Menu entry, and uninstaller
  - %APPDATA% folder: its own settings, history, dictionary and recordings
  - single-instance mutex, overlay window title, taskbar AppUserModelID
  - Run-at-startup registry value

Change these only together with installer/setup.iss (which can't import
Python) - tests/test_branding.py checks the two stay in sync.
"""

APP_NAME = "Wisperno Pro"
APP_SLUG = "WispernoPro"                      # file/folder-safe form
EXE_NAME = f"{APP_SLUG}.exe"
APP_DATA_DIR_NAME = APP_SLUG                   # %APPDATA%\WispernoPro
APP_USER_MODEL_ID = "WispernoPro.Desktop.1"
MUTEX_NAME = r"Local\WispernoPro_SingleInstance_Mutex_4417"
OVERLAY_WINDOW_TITLE = f"{APP_NAME} Overlay"
AUTOSTART_VALUE_NAME = APP_NAME
INSTALLER_APP_ID = "C6D1A7E3-5B24-4F8E-A1D9-73E2B0F4C518"

# The original Wisperno's single-instance mutex. If it's running too, both
# apps would answer the same hotkeys and type every dictation twice.
ORIGINAL_EDITION_NAME = "Wisperno"
ORIGINAL_EDITION_MUTEX = r"Local\Wisperno_SingleInstance_Mutex_9921"
