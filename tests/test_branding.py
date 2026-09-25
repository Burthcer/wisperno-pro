"""
Wisperno Pro installs and runs as a separate app from the original Wisperno:
every identity Windows uses to tell apps apart differs from the original's,
and installer/setup.iss (which can't import Python) matches src/branding.py.

Run: python tests/test_branding.py
"""

import os
import re
import sys
import tempfile
from pathlib import Path
from unittest import mock

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

ORIGINAL = {
    "app_id": "8F2B1C94-67A1-4E82-9B03-1D764A981E22",
    "name": "Wisperno",
    "exe": "Wisperno.exe",
    "mutex": r"Local\Wisperno_SingleInstance_Mutex_9921",
    "aumid": "Wisperno.Desktop.1.0",
    "data_dir": "Wisperno",
}


def _iss() -> str:
    return (BASE_DIR / "installer" / "setup.iss").read_text(encoding="utf-8")


def test_installer_matches_branding_and_differs_from_original() -> None:
    from src import branding

    logger.info("--- Testing installer identity vs src/branding.py and the original app ---")
    iss = _iss()
    define = lambda name: re.search(rf'#define {name} "([^"]+)"', iss).group(1)  # noqa: E731
    setting = lambda name: re.search(rf"^{name}=(.+)$", iss, re.M).group(1).strip()  # noqa: E731

    assert define("MyAppName") == branding.APP_NAME
    assert define("MyAppExeName") == branding.EXE_NAME
    assert setting("AppId") == "{{" + branding.INSTALLER_APP_ID + "}"
    assert setting("AppMutex") == branding.MUTEX_NAME
    assert setting("DefaultDirName") == r"{localappdata}\Programs\{#MyAppName}"
    assert setting("OutputBaseFilename").startswith("WispernoPro-Setup-")

    assert branding.INSTALLER_APP_ID != ORIGINAL["app_id"], "same AppId = Windows treats Pro as an upgrade"
    assert ORIGINAL["app_id"] not in iss.replace("8F2B1C94-...", "")
    assert branding.APP_NAME != ORIGINAL["name"] and branding.EXE_NAME != ORIGINAL["exe"]
    assert branding.MUTEX_NAME != ORIGINAL["mutex"] and branding.APP_USER_MODEL_ID != ORIGINAL["aumid"]
    assert branding.APP_DATA_DIR_NAME != ORIGINAL["data_dir"]
    assert branding.ORIGINAL_EDITION_MUTEX == ORIGINAL["mutex"], "must detect the original app correctly"
    logger.success("PASS: installer AppId/name/exe/mutex/folder all Pro-specific and in sync with branding.py.")


def test_build_outputs_use_the_pro_names() -> None:
    logger.info("--- Testing PyInstaller spec and build scripts produce WispernoPro.exe ---")
    spec = (BASE_DIR / "wisperno.spec").read_text(encoding="utf-8")
    assert spec.count('name="WispernoPro"') == 2 and 'name="Wisperno"' not in spec
    build = (BASE_DIR / "build_exe.py").read_text(encoding="utf-8")
    assert '"dist" / "WispernoPro"' in build and '"/IM", "WispernoPro.exe"' in build
    assert '"/IM", "Wisperno.exe"' not in build, "rebuilding must never kill the original app"
    installer = (BASE_DIR / "scripts" / "build_installer.py").read_text(encoding="utf-8")
    assert "WispernoPro-Setup-v" in installer and 'f"Wisperno-Setup-v' not in installer
    logger.success("PASS: spec/build/installer scripts all use WispernoPro.")


def test_app_data_is_separate() -> None:
    from src import config

    logger.info("--- Testing settings/history live in their own %APPDATA% folder ---")
    with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"APPDATA": tmp}):
        assert config.get_app_data_dir() == Path(tmp) / "WispernoPro"
        assert config.get_db_path() == Path(tmp) / "WispernoPro" / "wisperno.db"
        original_db = Path(tmp) / "Wisperno" / "wisperno.db"
        original_db.parent.mkdir()
        original_db.write_text("original app's history")
        config.get_db_path()
        assert original_db.read_text() == "original app's history", "the original's data must be left alone"
    logger.success("PASS: %APPDATA%\\WispernoPro, never %APPDATA%\\Wisperno.")


def test_icon_is_the_pro_icon() -> None:
    logger.info("--- Testing the icon assets are the Pro variant ---")
    svg = (BASE_DIR / "assets" / "icon.svg").read_text(encoding="utf-8")
    assert ">PRO</text>" in svg
    ico = (BASE_DIR / "assets" / "icons" / "wisperno.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00" and int.from_bytes(ico[4:6], "little") == 6  # 6 sizes
    logger.success("PASS: .ico has 6 sizes, generated from the PRO-badged source.")


def run_all_tests() -> None:
    test_installer_matches_branding_and_differs_from_original()
    test_build_outputs_use_the_pro_names()
    test_app_data_is_separate()
    test_icon_is_the_pro_icon()
    logger.success("ALL BRANDING TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
