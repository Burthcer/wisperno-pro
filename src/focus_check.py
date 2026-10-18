"""
"Is there a text box to paste into?" - asked right after a dictation, via Windows UI Automation.

The paste itself always happens (a keystroke can't tell us whether it landed). This only decides whether to ALSO show
the "no text field found" card. It leans hard towards "yes, there is a target": the card appears only when the focused
element is POSITIVELY something you can't type into (a button, a list, an image, the desktop...). Anything unknown,
any error and any missing library says "text box", so it never pops up over a paste that probably worked.
"""

from loguru import logger

_UIA_CLSID = "{ff48dba4-60ef-4201-aa87-54103eef594e}"
_VALUE_PATTERN, _TEXT_PATTERN = 10002, 10014

# UI Automation control types that are never typed into.
_NEVER_TEXT = {
    50000,  # Button
    50002,  # CheckBox
    50005,  # Hyperlink
    50006,  # Image
    50007,  # ListItem
    50008,  # List
    50009,  # Menu
    50010,  # MenuBar
    50011,  # MenuItem
    50013,  # RadioButton
    50015,  # Slider
    50019,  # TabItem
    50021,  # ToolBar
    50023,  # Tree
    50024,  # TreeItem
    50031,  # SplitButton
    50035,  # HeaderItem
    50036,  # Table
    50037,  # TitleBar
    50038,  # Separator
}
_PANE, _WINDOW = 50033, 50032
# A bare pane / window only counts as "no text box" in the desktop shell (explorer.exe: the desktop, the taskbar, a
# folder). In other programs a pane can be a terminal or a custom editor, so it stays "text box".
_SHELL_PROCESSES = {"explorer.exe", "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe"}


def is_text_target(control_type: int, has_text_pattern: bool, has_value_pattern: bool, process: str = "") -> bool:
    """Pure decision (testable): can the focused element receive typed text?"""
    if has_text_pattern or has_value_pattern:
        return True
    if control_type in _NEVER_TEXT:
        return False
    if control_type in (_PANE, _WINDOW) and process.lower() in _SHELL_PROCESSES:
        return False
    return True


def _inspect_focus() -> bool:
    # Built per call: COM objects belong to the thread that made them, and each dictation runs in a fresh worker thread.
    import comtypes.client as cc

    cc.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as U

    element = cc.CreateObject(_UIA_CLSID, interface=U.IUIAutomation).GetFocusedElement()
    kind = element.CurrentControlType

    def has(pattern: int) -> bool:
        try:
            return bool(element.GetCurrentPattern(pattern))
        except Exception:
            return False

    process = ""
    if kind in (_PANE, _WINDOW):
        try:
            import psutil

            process = psutil.Process(element.CurrentProcessId).name()
        except Exception:
            process = ""
    result = is_text_target(kind, has(_TEXT_PATTERN), has(_VALUE_PATTERN), process)
    if not result:
        logger.info(f"[PASTE CHECK] focused element (type {kind}, process '{process or '?'}') is not a text box.")
    return result


def has_text_target() -> bool:
    """False only when the focused element is positively NOT something you can type into."""
    try:
        import comtypes

        comtypes.CoInitialize()
    except Exception as e:
        logger.warning(f"[PASTE CHECK] UI Automation is not available ({e}); the 'no text box' card is off.")
        return True
    try:
        return _inspect_focus()
    except Exception as e:
        logger.warning(f"[PASTE CHECK] could not inspect the focused element ({e}); assuming a text box.")
        return True
    finally:
        comtypes.CoUninitialize()
