# smartdim/lut.py
from __future__ import annotations

import array
from typing import Tuple, List, Optional
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

# Optional: cap the very top of the curve (pure white) to a maximum output.
# Set to None to disable. Example: 0.90 forces x=1.0 to map to <= 0.90.
WHITE_CAP: Optional[float] = None

def _log(*a) -> None:
    if LOG:
        print("[smartdim]", *a)

# --------------------------------------------------------------------
# Tone curves
# --------------------------------------------------------------------
def piecewise_highlight_compress(x: float, tau: float, alpha: float) -> float:
    """
    Piecewise, constant-strength highlight compression:
    - For x <= tau: pass-through (preserve shadows/mids).
    - For x  > tau: compress toward tau with slope (1 - alpha).
    NOTE: we do NOT early-return 1.0 for x>=1, so pure white is compressed too.
    """
    if x <= 0.0:
        return 0.0
    if x <= tau:
        return x
    return tau + (x - tau) * (1.0 - alpha)

def piecewise_variable_compress(x: float, tau: float,
                                alpha_lo: float, alpha_hi: float,
                                p: float = 2.0) -> float:
    """
    Variable-strength highlight compression:
    - Strength increases with brightness above tau (whites dim the most).
    - alpha ramps from alpha_lo (just above tau) to alpha_hi (near white).
    - p (>1) biases stronger compression toward the very top end.
    """
    if x <= 0.0:
        return 0.0
    if x <= tau:
        return x
    t = (x - tau) / (1.0 - tau)             # normalize [tau..1] -> [0..1]
    alpha_eff = alpha_lo + (alpha_hi - alpha_lo) * (t ** p)
    return tau + (x - tau) * (1.0 - alpha_eff)

# --------------------------------------------------------------------
# LUT builders
# --------------------------------------------------------------------
def _monotone_clip(ys: List[float]) -> List[float]:
    # keep within [0,1] and enforce monotonic non-decreasing
    ys = [0.0 if y < 0.0 else 1.0 if y > 1.0 else y for y in ys]
    for i in range(1, len(ys)):
        if ys[i] < ys[i - 1]:
            ys[i] = ys[i - 1]
    return ys

def build_lut(n: int, tau: float, alpha: float, beta: float = 1.0,
              white_cap: Optional[float] = WHITE_CAP
             ) -> Tuple[array.array, array.array, array.array]:
    xs = [i / (n - 1) for i in range(n)]
    ys = [piecewise_highlight_compress(x, tau, alpha) for x in xs]
    if beta != 1.0:
        ys = [y * beta for y in ys]  # global scale (dims everything, including shadows)
    if white_cap is not None:
        # force the very top to never exceed white_cap
        ys[-1] = min(ys[-1], white_cap)
    ys = _monotone_clip(ys)
    arr = array.array("f", ys)
    return arr, arr, arr

def build_lut_variable(n: int, tau: float,
                       alpha_lo: float, alpha_hi: float,
                       p: float = 2.0, beta: float = 1.0,
                       white_cap: Optional[float] = WHITE_CAP
                      ) -> Tuple[array.array, array.array, array.array]:
    xs = [i / (n - 1) for i in range(n)]
    ys = [piecewise_variable_compress(x, tau, alpha_lo, alpha_hi, p) for x in xs]
    if beta != 1.0:
        ys = [y * beta for y in ys]
    if white_cap is not None:
        ys[-1] = min(ys[-1], white_cap)
    ys = _monotone_clip(ys)
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
# Apply LUT
# --------------------------------------------------------------------
def _apply_rgb_tables(r: array.array, g: array.array, b: array.array) -> bool:
    applied = False
    for d in _active_displays():
        CGSetDisplayTransferByTable(d, len(r), r, g, b)
        applied = True
    return applied

def apply_lut_all_displays(tau: float, alpha: float, n: int = 256, beta: float = 1.0,
                           white_cap: Optional[float] = WHITE_CAP) -> None:
    r, g, b = build_lut(n, tau, alpha, beta, white_cap)
    if _apply_rgb_tables(r, g, b):
        _log(f"Applied LUT: tau={tau:.2f}, alpha={alpha:.2f}, beta={beta:.2f}, "
             f"n={n}, white_cap={white_cap}")
    else:
        _log("No active displays — LUT not applied")

def apply_lut_variable(tau: float,
                       alpha_lo: float, alpha_hi: float,
                       p: float = 2.0, n: int = 256, beta: float = 1.0,
                       white_cap: Optional[float] = WHITE_CAP) -> None:
    r, g, b = build_lut_variable(n, tau, alpha_lo, alpha_hi, p, beta, white_cap)
    if _apply_rgb_tables(r, g, b):
        _log(f"Applied variable LUT: tau={tau:.2f}, "
             f"alpha_lo={alpha_lo:.2f}, alpha_hi={alpha_hi:.2f}, p={p:.2f}, "
             f"beta={beta:.2f}, n={n}, white_cap={white_cap}")
    else:
        _log("No active displays — variable LUT not applied")

# --------------------------------------------------------------------
# Enable / disable / toggle
# --------------------------------------------------------------------
def enable(tau: float = 0.70, alpha: float = 0.40, n: int = 256, beta: float = 1.0,
           white_cap: Optional[float] = WHITE_CAP) -> None:
    CURRENT.update({"enabled": True, "tau": tau, "alpha": alpha, "beta": beta, "n": n})
    apply_lut_all_displays(tau, alpha, n, beta, white_cap)
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
        apply_lut_all_displays(CURRENT["tau"], CURRENT["alpha"], CURRENT["n"], CURRENT["beta"])

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
    """
    Aggressive preset using variable highlight compression:
    - starts at upper mids (tau ~0.60)
    - mild compression just above tau, very strong near white
    - beta=1.0 preserves shadows (no global darkening)
    """
    tau = 0.60
    alpha_lo = 0.65
    alpha_hi = 0.98
    p = 2.4
    n = 512
    beta = 1.0
    CURRENT.update({"enabled": True, "tau": tau, "alpha": alpha_hi, "beta": beta, "n": n})
    apply_lut_variable(tau, alpha_lo, alpha_hi, p, n, beta, WHITE_CAP)
    _log("Enabled (aggressive variable compression)")

def enable_extra_aggressive() -> None:
    """
    Even stronger variable compression; still keeps beta=1.0 to protect shadows.
    """
    tau = 0.58
    alpha_lo = 0.70
    alpha_hi = 0.995
    p = 3.0
    n = 512
    beta = 1.0
    CURRENT.update({"enabled": True, "tau": tau, "alpha": alpha_hi, "beta": beta, "n": n})
    apply_lut_variable(tau, alpha_lo, alpha_hi, p, n, beta, WHITE_CAP)
    _log("Enabled (extra aggressive variable compression)")

def enable_nuclear() -> None:
    """
    Legacy 'nuclear' preset (constant-strength compression + global dim).
    This will darken shadows too because beta < 1.0.
    """
    enable(tau=0.35, alpha=0.98, n=512, beta=0.55, white_cap=WHITE_CAP)

def enable_aggressive_legacy() -> None:
    """
    Old aggressive preset (constant-strength + some global dim).
    """
    enable(tau=0.50, alpha=0.90, n=512, beta=0.75, white_cap=WHITE_CAP)

# --------------------------------------------------------------------
# Flat LUT (diagnostic)
# --------------------------------------------------------------------
def enable_flat(level: float = 0.20, n: int = 256) -> None:
    """
    Apply a uniform flat LUT across all channels.
    Use to test whether CoreGraphics LUTs affect your display path.
    """
    level = 0.0 if level < 0.0 else 1.0 if level > 1.0 else level
    arr = array.array("f", [level] * n)
    changed = False
    for d in _active_displays():
        CGSetDisplayTransferByTable(d, n, arr, arr, arr)
        changed = True
    if changed:
        _log(f"Flat LUT applied at {level:.2f}")
        CURRENT.update({"enabled": True, "tau": 1.0, "alpha": 0.0, "beta": level, "n": n})
    else:
        _log("No active displays — flat LUT not applied")
