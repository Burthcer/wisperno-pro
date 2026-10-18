"""
Live hardware telemetry (VRAM + RAM) for the System Usage tab.

Per-process VRAM does NOT come from pynvml's nvmlDeviceGetComputeRunningProcesses:
verified directly on this GeForce RTX 4070 Laptop that NVML finds our own PID in
the compute-process list but reports `usedGpuMemory=None` for it - a known NVML
limitation on consumer (non-Tesla/Quadro) GPUs under WDDM, not a bug in this code.
Instead this reads the same "GPU Process Memory\\Dedicated Usage" performance
counter Windows Task Manager itself uses, via the low-level PDH API (no pywin32
dependency - just ctypes + pdh.dll, both already present on every Windows box).
Whole-GPU total/used still comes from pynvml, which IS accurate at that level.
"""

import ctypes as ct
import os
import sys
from typing import List, Optional, Tuple

from loguru import logger
import psutil

try:
    import pynvml
    pynvml.nvmlInit()
    _NVML_OK = True
except Exception as e:
    logger.debug(f"pynvml unavailable, GPU total/used telemetry will report zero: {e}")
    _NVML_OK = False

PDH_FMT_LARGE = 0x00000400
PDH_MORE_DATA = 0x800007D2
PDH_CSTATUS_VALID_DATA = 0x0
PDH_CSTATUS_NEW_DATA = 0x1

_COUNTER_PATHS = {
    "dedicated": r"\GPU Process Memory(*)\Dedicated Usage",
    # Allocations WDDM has demoted out of VRAM into system RAM (e.g. while a
    # game needs the GPU) - they drop out of "Dedicated Usage" but are still
    # Wisperno's, so they're reported separately rather than silently lost.
    "shared": r"\GPU Process Memory(*)\Shared Usage",
}


class _PdhCounterValue(ct.Structure):
    class _U(ct.Union):
        _fields_ = [
            ("longValue", ct.c_long),
            ("doubleValue", ct.c_double),
            ("largeValue", ct.c_longlong),
            ("AnsiStringValue", ct.c_char_p),
            ("WideStringValue", ct.c_wchar_p),
        ]
    _fields_ = [("CStatus", ct.c_ulong), ("u", _U)]
    _anonymous_ = ("u",)


class _PdhCounterItem(ct.Structure):
    _fields_ = [("szName", ct.c_wchar_p), ("FmtValue", _PdhCounterValue)]


class _ProcessVramReader:
    """
    Per-process GPU memory from the "GPU Process Memory" counter set, the
    same source Task Manager's per-process "Dedicated GPU memory" column
    uses. Instance names look like "pid_1234_luid_0x..._phys_0", one per
    (process, GPU adapter) pair; every instance for our PID is summed.

    The query and its wildcard counters are rebuilt every REOPEN_EVERY reads
    so the instance list can never go stale for the life of the app (the old
    reader opened it once, when the dashboard was built - before the models
    had finished loading).
    """

    REOPEN_EVERY = 15  # reads; ~30s at the System Usage tab's 2s poll

    def __init__(self):
        self._pdh = None
        self._h_query = None
        self._h_counters: dict = {}
        self._reads_since_open = 0
        if sys.platform != "win32":
            return
        try:
            pdh = ct.WinDLL("pdh.dll")
            # PDH_STATUS is declared as unsigned here so status comparisons
            # against the unsigned hex constants above work without masking.
            for name, argtypes in (
                ("PdhOpenQueryW", [ct.c_wchar_p, ct.c_void_p, ct.POINTER(ct.c_void_p)]),
                ("PdhAddEnglishCounterW", [ct.c_void_p, ct.c_wchar_p, ct.c_void_p, ct.POINTER(ct.c_void_p)]),
                ("PdhCollectQueryData", [ct.c_void_p]),
                ("PdhGetFormattedCounterArrayW",
                 [ct.c_void_p, ct.c_ulong, ct.POINTER(ct.c_ulong), ct.POINTER(ct.c_ulong), ct.c_void_p]),
                ("PdhCloseQuery", [ct.c_void_p]),
            ):
                fn = getattr(pdh, name)
                fn.argtypes = argtypes
                fn.restype = ct.c_ulong
            self._pdh = pdh
        except Exception as e:
            logger.debug(f"PDH GPU Process Memory counters unavailable: {e}")

    def _open(self) -> bool:
        self._close_query()
        h_query = ct.c_void_p()
        if self._pdh.PdhOpenQueryW(None, None, ct.byref(h_query)) != 0:
            return False
        counters = {}
        for key, path in _COUNTER_PATHS.items():
            h_counter = ct.c_void_p()
            if self._pdh.PdhAddEnglishCounterW(h_query, path, None, ct.byref(h_counter)) == 0:
                counters[key] = h_counter
        if not counters:
            self._pdh.PdhCloseQuery(h_query)
            return False
        self._h_query, self._h_counters = h_query, counters
        self._reads_since_open = 0
        return True

    def _sum_for_pid(self, h_counter, prefix: str) -> Tuple[float, List[str]]:
        """Sum every valid instance starting with `prefix`; returns (MB, per-instance breakdown)."""
        get = self._pdh.PdhGetFormattedCounterArrayW
        for _ in range(3):  # the instance list can grow between the size probe and the real read
            buf_size, item_count = ct.c_ulong(0), ct.c_ulong(0)
            status = get(h_counter, PDH_FMT_LARGE, ct.byref(buf_size), ct.byref(item_count), None)
            if status != PDH_MORE_DATA or buf_size.value == 0:
                return 0.0, []
            buf = ct.create_string_buffer(buf_size.value)
            status = get(h_counter, PDH_FMT_LARGE, ct.byref(buf_size), ct.byref(item_count), buf)
            if status == PDH_MORE_DATA:
                continue
            if status != 0:
                return 0.0, []
            items = ct.cast(buf, ct.POINTER(_PdhCounterItem))
            total_bytes, breakdown = 0, []
            for i in range(item_count.value):
                item = items[i]
                if not item.szName or not item.szName.startswith(prefix):
                    continue
                if item.FmtValue.CStatus not in (PDH_CSTATUS_VALID_DATA, PDH_CSTATUS_NEW_DATA):
                    continue
                total_bytes += item.FmtValue.largeValue
                breakdown.append(f"{item.szName}={item.FmtValue.largeValue / 1024 / 1024:.0f}MB")
            return total_bytes / 1024 / 1024, breakdown
        return 0.0, []

    def read(self, pid: int) -> Tuple[float, float, List[str]]:
        """Returns (dedicated_mb, shared_mb, breakdown). Zeros if unavailable."""
        if self._pdh is None:
            return 0.0, 0.0, []
        try:
            if self._h_query is None or self._reads_since_open >= self.REOPEN_EVERY:
                if not self._open():
                    return 0.0, 0.0, []
            self._reads_since_open += 1
            if self._pdh.PdhCollectQueryData(self._h_query) != 0:
                return 0.0, 0.0, []
            prefix = f"pid_{pid}_"
            dedicated, breakdown = (
                self._sum_for_pid(self._h_counters["dedicated"], prefix)
                if "dedicated" in self._h_counters else (0.0, [])
            )
            shared, _ = (
                self._sum_for_pid(self._h_counters["shared"], prefix)
                if "shared" in self._h_counters else (0.0, [])
            )
            return dedicated, shared, breakdown
        except Exception as e:
            logger.debug(f"PDH GPU Process Memory read failed: {e}")
            return 0.0, 0.0, []

    def _close_query(self) -> None:
        if self._pdh is not None and self._h_query is not None:
            try:
                self._pdh.PdhCloseQuery(self._h_query)
            except Exception:
                pass
        self._h_query, self._h_counters = None, {}

    def close(self) -> None:
        self._close_query()


# Independent cross-check for the per-process counter: whole-GPU usage
# (pynvml, accurate at that level) sampled right before and right after the
# engine loads Whisper + the LLM. The difference is what the models took.
# Other apps can shift GPU usage during those few seconds, so it's an
# estimate - used as a floor when the per-process counter reads implausibly
# low, never on its own when the counter looks right.
_load_baseline_mb: Optional[float] = None
_models_load_delta_mb: float = 0.0


def _gpu_used_mb() -> Optional[float]:
    if not _NVML_OK:
        return None
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        return pynvml.nvmlDeviceGetMemoryInfo(handle).used / 1024 / 1024
    except Exception:
        return None


def mark_models_loading() -> None:
    """Call right before the engine starts loading Whisper/the LLM."""
    global _load_baseline_mb
    _load_baseline_mb = _gpu_used_mb()


def mark_models_loaded() -> None:
    """Call right after Whisper and the LLM finished loading."""
    global _models_load_delta_mb
    after = _gpu_used_mb()
    if _load_baseline_mb is None or after is None:
        return
    _models_load_delta_mb = max(0.0, after - _load_baseline_mb)
    logger.info(
        f"[VRAM] Whole-GPU usage went {_load_baseline_mb:.0f}MB -> {after:.0f}MB while loading models "
        f"(~{_models_load_delta_mb:.0f}MB for Whisper + LLM)."
    )


class SystemMonitor:
    def __init__(self):
        self._pid = os.getpid()
        self._gpu_handle = None
        if _NVML_OK:
            try:
                self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as e:
                logger.debug(f"No NVIDIA GPU found for telemetry: {e}")
        self._proc_vram = _ProcessVramReader()
        self._mismatch_logged = False
        self._first_reading_logged = False
        self._low_used_logged = False

    def _read_gpu_memory(self) -> tuple:
        """(total_mb, used_mb) of the whole GPU. NVML sometimes answers 0 / an error on a laptop GPU that was idle, so a
        zero or failure is retried with the older struct and then after re-opening NVML."""
        if self._gpu_handle is None:
            return 0.0, 0.0

        def attempt(version_two: bool):
            mem = (pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle, pynvml.nvmlMemory_v2) if version_two
                   else pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle))
            return mem.total / 1024 / 1024, mem.used / 1024 / 1024

        best = (0.0, 0.0)
        for reopen in (False, True):
            if reopen:
                try:
                    pynvml.nvmlShutdown()
                    pynvml.nvmlInit()
                    self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                except Exception as e:
                    logger.debug(f"NVML re-open failed: {e}")
                    break
            # v2 reports the driver's own reserved memory separately; v1's "used" includes it (~0.25 GB more than Task
            # Manager's "Dedicated GPU memory"). v2 is what Task Manager shows, so it goes first.
            for version_two in (True, False):
                try:
                    total, used = attempt(version_two)
                except Exception as e:
                    logger.debug(f"GPU memory read failed ({'v2' if version_two else 'v1'}): {e}")
                    continue
                best = (max(best[0], total), max(best[1], used))
                if used > 0:
                    return total, used
        return best

    def snapshot(self) -> dict:
        """Returns MB-denominated gpu_total/gpu_used/app_vram and ram_total/ram_used/app_ram."""
        ram = psutil.virtual_memory()
        app_ram_mb = psutil.Process(self._pid).memory_info().rss / 1024 / 1024

        gpu_total_mb, gpu_used_mb = self._read_gpu_memory()

        pdh_dedicated_mb, app_shared_mb, breakdown = self._proc_vram.read(self._pid)
        app_vram_mb, app_vram_source = pdh_dedicated_mb, "per-process counter"
        if _models_load_delta_mb and not self._first_reading_logged:
            self._first_reading_logged = True
            logger.info(
                f"[VRAM] Per-process counter after model load: {pdh_dedicated_mb:.0f}MB dedicated, "
                f"{app_shared_mb:.0f}MB shared ({', '.join(breakdown) or 'no instances for this PID'})."
            )
        # Counter reads well under what loading the models demonstrably took
        # (reported: ~1.5GB shown vs ~3.6GB in Task Manager) - trust the
        # load delta instead, and log both once so the mismatch is visible.
        if _models_load_delta_mb and pdh_dedicated_mb + app_shared_mb < 0.75 * _models_load_delta_mb:
            app_vram_mb, app_vram_source = _models_load_delta_mb, "load-time estimate"
            if not self._mismatch_logged:
                self._mismatch_logged = True
                logger.warning(
                    f"[VRAM] Per-process counter reads {pdh_dedicated_mb:.0f}MB dedicated + "
                    f"{app_shared_mb:.0f}MB shared, but loading the models took ~{_models_load_delta_mb:.0f}MB "
                    f"- showing the load-time figure instead. Counter instances for this PID: "
                    f"{', '.join(breakdown) or 'none'}"
                )

        if gpu_total_mb and gpu_used_mb < app_vram_mb:
            # NVML says the whole GPU uses LESS than this app alone holds, which can't be true (it read 0 while Task
            # Manager showed 3.3 GB). Trust the larger figure so the gauge never falls to 0% with models loaded.
            if not self._low_used_logged:
                self._low_used_logged = True
                logger.warning(f"[VRAM] NVML reports {gpu_used_mb:.0f}MB used in total but this app holds ~{app_vram_mb:.0f}MB - "
                               f"using the app's figure as the floor.")
            gpu_used_mb = app_vram_mb
        if gpu_used_mb:
            app_vram_mb = min(app_vram_mb, gpu_used_mb)  # the app can't hold more than the whole GPU has in use

        gpu_util_pct = 0
        gpu_temp_c = None
        if self._gpu_handle is not None:
            try:
                gpu_util_pct = pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle).gpu
            except Exception as e:
                logger.debug(f"GPU utilization read failed: {e}")
            try:
                gpu_temp_c = pynvml.nvmlDeviceGetTemperature(self._gpu_handle, pynvml.NVML_TEMPERATURE_GPU)
            except Exception as e:
                logger.debug(f"GPU temperature read failed: {e}")

        # cpu_percent(interval=None) reports the delta since the LAST call on
        # this process - meaningless (always 0.0) on the very first call ever
        # made, which is fine here since this is polled every 2s for the life
        # of the app (system_usage_tab.py's QTimer), not read once.
        cpu_util_pct = psutil.cpu_percent(interval=None)
        try:
            thread_count = psutil.Process(self._pid).num_threads()
        except Exception as e:
            logger.debug(f"Thread count read failed: {e}")
            thread_count = 0

        return {
            "gpu_total_mb": gpu_total_mb,
            "gpu_used_mb": gpu_used_mb,
            "app_vram_mb": app_vram_mb,
            "app_vram_source": app_vram_source,
            "app_shared_mb": app_shared_mb,
            "gpu_util_pct": gpu_util_pct,
            "gpu_temp_c": gpu_temp_c,
            "ram_total_mb": ram.total / 1024 / 1024,
            "ram_used_mb": ram.used / 1024 / 1024,
            "app_ram_mb": app_ram_mb,
            "cpu_util_pct": cpu_util_pct,
            "thread_count": thread_count,
        }

    def close(self) -> None:
        self._proc_vram.close()


def _demo():
    m = SystemMonitor()
    snap = m.snapshot()
    assert snap["ram_total_mb"] > 0, "RAM total should always be reportable"
    assert snap["app_ram_mb"] > 0, "This process should show nonzero RSS"
    assert "gpu_util_pct" in snap and "gpu_temp_c" in snap
    print("system_monitor self-check OK:", snap)
    m.close()


if __name__ == "__main__":
    _demo()
