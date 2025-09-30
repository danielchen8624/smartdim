# smartdim/lut.py
from __future__ import annotations

import array
from typing import Tuple, List
from Quartz import (
    CGGetActiveDisplayList,
    CGSetDisplayTransferByTable,
    CGDisplayRestoreColorSyncSettings,
    CGDisplayRegisterReconfigurationCallback,
    CGDisplayRemoveReconfigurationCallback,
)

# --------------------------------------------------------------------
# State + logging
# --------------------------------------------------------------------
CURRENT = {"enabled": False, "tau": 0.70, "alpha": 0.40, "beta": 1.0, "n": 256}
LOG = True  # flip False to silence prints

def _log(*a) -> None:
    if LOG:
        print("[smartdim]", *a)

# --------------------------------------------------------------------
# Tone curve (compress highlights)
# --------------------------------------------------------------------
def piecewise_highlight_compress(x: float, tau: float, alpha: float) -> float:
    """Piecewise linear curve: compress highlights above tau."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if x <= tau:
        return x
    return tau + (x - tau) * (1.0 - alpha)

def build_lut(
    n: int, tau: float, alpha: float, beta: float = 1.0
) -> Tuple[array.array, array.array, array.array]:
    xs = [i / (n - 1) for i in range(n)]
    ys = [piecewise_highlight_compress(x, tau, alpha) for x in xs]
    if beta != 1.0:
        ys = [min(1.0, max(0.0, y * beta)) for y in ys]  # scale brightness
    # enforce monotonicity
    for i in range(1, n):
        if ys[i] < ys[i - 1]:
            ys[i] = ys[i - 1]
    arr = array.array("f", ys)
    return arr, arr, arr

# --------------------------------------------------------------------
# Display enumeration (active displays only)
# --------------------------------------------------------------------
def _active_displays(max_count: int = 16) -> List[int]:
    err, displays, count = CGGetActiveDisplayList(max_count, None, None)
    if err != 0 or count == 0:
        _log("CGGetActiveDisplayList err or empty:", err, count)
        return []
    ids = list(displays)[:count]
    _log(f"🖥️ Active displays ({count}):", ids)
    return ids

# --------------------------------------------------------------------
# LUT application
# --------------------------------------------------------------------
def apply_lut_all_displays(
    tau: float, alpha: float, n: int = 256, beta: float = 1.0
) -> None:
    r, g, b = build_lut(n, tau, alpha, beta)
    applied = False
    for d in _active_displays():
        CGSetDisplayTransferByTable(d, len(r), r, g, b)
        applied = True
    if applied:
        _log(f"✅ Applied LUT: tau={tau:.2f}, alpha={alpha:.2f}, beta={beta:.2f}, n={n}")
    else:
        _log("⚠️ No active displays — LUT not applied")

# --------------------------------------------------------------------
# Enable / disable / toggle
# --------------------------------------------------------------------
def enable(
    tau: float = 0.70, alpha: float = 0.40, n: int = 256, beta: float = 1.0
) -> None:
    CURRENT.update({"enabled": True, "tau": tau, "alpha": alpha, "beta": beta, "n": n})
    apply_lut_all_displays(tau, alpha, n, beta)
    _log("Enabled")

def disable() -> None:
    CURRENT["enabled"] = False
    CGDisplayRestoreColorSyncSettings()
    _log("Disabled (restored original colors)")

def toggle() -> None:
    if CURRENT["enabled"]:
        disable()
    else:
        enable(CURRENT["tau"], CURRENT["alpha"], CURRENT["n"], CURRENT["beta"])

def reapply_if_enabled(*_args) -> None:
    if CURRENT["enabled"]:
        apply_lut_all_displays(
            CURRENT["tau"], CURRENT["alpha"], CURRENT["n"], CURRENT["beta"]
        )

# --------------------------------------------------------------------
# Callbacks (reapply after display changes)
# --------------------------------------------------------------------
def _display_reconfig_callback(display, flags, userInfo) -> None:
    _log("Display reconfig:", display, flags)
    reapply_if_enabled()

def register_display_callbacks():
    CGDisplayRegisterReconfigurationCallback(_display_reconfig_callback, None)
    _log("Registered display callbacks")

def unregister_display_callbacks():
    CGDisplayRemoveReconfigurationCallback(_display_reconfig_callback, None)
    _log("Unregistered display callbacks")

# --------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------
def enable_aggressive() -> None:
    enable(tau=0.50, alpha=0.90, n=512, beta=0.75)

def enable_extra_aggressive() -> None:
    enable(tau=0.45, alpha=0.95, n=512, beta=0.65)

def enable_nuclear() -> None:
    enable(tau=0.35, alpha=0.98, n=512, beta=0.55)

# --------------------------------------------------------------------
# Flat LUT (test whether gamma changes are honored)
# --------------------------------------------------------------------
def enable_flat(level: float = 0.20, n: int = 256) -> None:
    """
    Apply a uniform flat LUT across all channels.
    Use to test if CoreGraphics LUTs affect your display.
    """
    level = max(0.0, min(1.0, level))
    arr = array.array("f", [level] * n)
    changed = False
    for d in _active_displays():
        CGSetDisplayTransferByTable(d, n, arr, arr, arr)
        changed = True
    if changed:
        _log(f"🧪 Flat LUT applied at {level:.2f}")
        CURRENT.update(
            {"enabled": True, "tau": 1.0, "alpha": 0.0, "beta": level, "n": n}
        )
    else:
        _log("⚠️ No active displays — flat LUT not applied")
