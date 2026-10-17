"""
"Is there a text box to paste into?" - asked right after a dictation, via Windows UI Automation.

The paste itself always happens (a keystroke can't tell us whether it landed). This only decides whether to ALSO show
the "couldn't find a text box - copied" card. It fails open: any doubt, error or missing library says "yes, there is a
target", so the card never appears for a paste that probably worked.
"""

from loguru import logger

_UIA_CLSID = "{ff48dba4-60ef-4201-aa87-54103eef594e}"
_EDITABLE_TYPES = {50003, 50004, 50030}  # ComboBox, Edit, Document
_WEB_INPUT_TYPES = {50025, 50026}        # Custom, Group: how some web chat boxes appear
_VALUE_PATTERN, _TEXT_PATTERN = 10002, 10014


def _focused_element_is_text_box() -> bool:
    # Built per call: COM objects belong to the thread that made them, and each dictation runs in a fresh worker thread.
    import comtypes.client as cc

    cc.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as U

    element = cc.CreateObject(_UIA_CLSID, interface=U.IUIAutomation).GetFocusedElement()
    kind = element.CurrentControlType
    if kind in _EDITABLE_TYPES:
        return True
    for pattern in (_TEXT_PATTERN, _VALUE_PATTERN):
        try:
            if element.GetCurrentPattern(pattern):
                return True  # exposes text / a value: treat as a field (read-only ones too, to stay safe)
        except Exception:
            continue
    if element.CurrentIsKeyboardFocusable and kind in _WEB_INPUT_TYPES:
        return True
    logger.info(f"[PASTE CHECK] focused element type {kind} is not a text box.")
    return False


def has_text_target() -> bool:
    """False only when the focused element is positively NOT something you can type into."""
    try:
        import comtypes

        comtypes.CoInitialize()
    except Exception:
        return True
    try:
        return _focused_element_is_text_box()
    except Exception as e:
        logger.debug(f"[PASTE CHECK] could not inspect the focused element ({e}); assuming a text box.")
        return True
    finally:
        comtypes.CoUninitialize()
