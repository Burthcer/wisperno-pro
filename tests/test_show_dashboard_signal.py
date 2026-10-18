"""A second launch asks the running instance to open its dashboard (instead of silently doing nothing).

Run: python tests/test_show_dashboard_signal.py
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import single_instance  # noqa: E402


def main() -> None:
    single_instance.SHOW_EVENT_NAME = r"LocalWispernoProTest_ShowDashboard"  # never collide with a real running app
    assert single_instance._signal_existing_to_show_dashboard() is False, "nobody is listening yet"
    got = threading.Event()
    single_instance.listen_for_show_requests(got.set)
    assert single_instance._signal_existing_to_show_dashboard() is True
    assert got.wait(3), "the listener should run the callback"
    got.clear()
    assert single_instance._signal_existing_to_show_dashboard() is True and got.wait(3), "and again (auto-reset event)"
    print("PASS: a second launch reaches the running instance, every time.")


if __name__ == "__main__":
    main()
