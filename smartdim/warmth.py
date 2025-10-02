# smartdim/warmth.py
from __future__ import annotations

import math
import array
from typing import List, Tuple, Optional
from Quartz import (
    CGGetActiveDisplayList,
    CGSetDisplayTransferByTable,
    CGDisplayRestoreColorSyncSettings,
    CGDisplayRegisterReconfigurationCallback,
    CGDisplayRemoveReconfigurationCallback,
)

# --------------------------------------------------------------------
# Module state
# --------------------------------------------------------------------
CURRENT = {
    "enabled": False,
    "kelvin": 6500.0,    # last applied white-point
    "beta": 1.0,         # optional global dim
    "n": 512,
}
LOG = True

def _log(*a) -> None:
    if LOG:
        print("[warmth]", *a)

# --------------------------------------------------------------------
# Display enumeration helpers
# --------------------------------------------------------------------
def _active_displays(max_count: int = 16) -> List[int]:
    err, displays, count = CGGetActiveDisplayList(max_count, None, None)
    if err != 0 or count == 0:
        _log("CGGetActiveDisplayList err or empty:", err, count)
        return []
    return list(displays)[:count]

def _apply_rgb_tables(r: array.array, g: array.array, b: array.array) -> bool:
    changed = False
    for d in _active_displays():
        CGSetDisplayTransferByTable(d, len(r), r, g, b)
        changed = True
    return changed

# --------------------------------------------------------------------
# Math utilities
# --------------------------------------------------------------------
def _monotone_clip(xs: List[float]) -> List[float]:
    xs = [0.0 if v < 0.0 else 1.0 if v > 1.0 else v for v in xs]
    for i in range(1, len(xs)):
        if xs[i] < xs[i-1]:
            xs[i] = xs[i-1]
    return xs

def _smoothstep(a: float, b: float, x: float) -> float:
    if x <= a: return 0.0
    if x >= b: return 1.0
    t = (x - a) / (b - a)
    return t * t * (3 - 2 * t)

def _remap_slider(s_raw: float) -> float:
    """Perceptual remap so the slider feels even."""
    s = 0.0 if s_raw < 0.0 else 1.0 if s_raw > 1.0 else float(s_raw)
    # Gamma-ish pre-emphasis for early response
    s = s ** 0.75
    # Gentle S curve around mid
    k = 0.35
    s = 0.5 + (s - 0.5) * (1 + k - k * 4.0 * abs(s - 0.5))
    return 0.0 if s < 0 else 1.0 if s > 1 else s

# --------------------------------------------------------------------
# Kelvin ↔︎ RGB (approximate blackbody; sRGB-ish)
# Based on common temperature → RGB approximations (Tanner Helland/ImgTec-style),
# adapted to produce [0..1] channel gains.
# --------------------------------------------------------------------
def _kelvin_to_rgb_channels(k: float) -> Tuple[float, float, float]:
    """Return (R,G,B) in 0..1 for a given white point in Kelvin."""
    k = max(1000.0, min(40000.0, k)) / 100.0
    # Red
    if k <= 66:
        r = 255.0
    else:
        r = 329.698727446 * ((k - 60.0) ** -0.1332047592)
        r = max(0.0, min(255.0, r))
    # Green
    if k <= 66:
        g = 99.4708025861 * math.log(k) - 161.1195681661
    else:
        g = 288.1221695283 * ((k - 60.0) ** -0.0755148492)
    g = max(0.0, min(255.0, g))
    # Blue
    if k >= 66:
        b = 255.0
    elif k <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(k - 10.0) - 305.0447927307
        b = max(0.0, min(255.0, b))
    return (r/255.0, g/255.0, b/255.0)

def _kelvin_to_gains(k: float, preserve_peak: bool = True) -> Tuple[float, float, float]:
    """
    Convert target Kelvin to per-channel gains relative to D65 (~6500K).
    If preserve_peak=True, normalize so the maximum gain is 1.0 to avoid highlight clipping.
    """
    ref = _kelvin_to_rgb_channels(6500.0)
    tgt = _kelvin_to_rgb_channels(k)

    # Gains to move D65 white → target white
    gains = (tgt[0] / max(1e-6, ref[0]),
             tgt[1] / max(1e-6, ref[1]),
             tgt[2] / max(1e-6, ref[2]))

    if preserve_peak:
        m = max(gains)
        if m > 1.0:
            gains = (gains[0]/m, gains[1]/m, gains[2]/m)
    return gains

# --------------------------------------------------------------------
# LUT builder: apply per-channel gain, optionally mild global dim (beta)
# --------------------------------------------------------------------
def _build_lut_color_tint(
    n: int,
    r_gain: float,
    g_gain: float,
    b_gain: float,
    beta: float = 1.0,
    rolloff: float = 0.08
) -> Tuple[array.array, array.array, array.array]:
    """
    Build three 1D LUTs with per-channel gains and a highlight-rolloff to
    avoid harsh clipping when a gain > 1 (rare if preserve_peak=True).
    """
    xs = [i / (n - 1) for i in range(n)]
    rr: List[float] = []
    gg: List[float] = []
    bb: List[float] = []

    for x in xs:
        # Optional very soft shoulder near 1.0 to hide clipping
        t = _smoothstep(1.0 - rolloff, 1.0, x)
        shoulder = 1.0 - 0.07 * t  # gently pull highlights by up to 7%

        r = min(1.0, x * r_gain) * shoulder
        g = min(1.0, x * g_gain) * shoulder
        b = min(1.0, x * b_gain) * shoulder

        if beta != 1.0:
            r *= beta; g *= beta; b *= beta

        rr.append(r); gg.append(g); bb.append(b)

    rr = _monotone_clip(rr)
    gg = _monotone_clip(gg)
    bb = _monotone_clip(bb)

    return array.array("f", rr), array.array("f", gg), array.array("f", bb)

# --------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------
def set_warmth(
    strength: float,
    *,
    n: int = 512,
    kelvin_min: float = 1900.0,
    kelvin_max: float = 6500.0,
    beta_curve: bool = True
) -> None:
    """
    strength ∈ [0,1]: 0 → neutral (≈6500K), 1 → very warm (≈1900K).
    beta_curve: when True, apply a gentle global dim as it gets very warm
                (closer to f.lux feel at night).
    """
    s_user = 0.0 if strength < 0.0 else 1.0 if strength > 1.0 else float(strength)
    if s_user <= 1e-3:
        CGDisplayRestoreColorSyncSettings()
        CURRENT.update({"enabled": False})
        _log("Warmth 0 → restored system colors")
        return

    s = _remap_slider(s_user)

    # Interpolate in mired space (linear perceived steps across color temp)
    m_max = 1e6 / kelvin_max
    m_min = 1e6 / kelvin_min
    m = m_max + (m_min - m_max) * s
    kelvin = max(kelvin_min, min(kelvin_max, 1e6 / m))

    # Optional dim curve that increases slightly as it gets warmer
    if beta_curve:
        # keep near 1.0 until ~40%, then gently to ~0.90 at max warmth
        if s < 0.4:
            beta = 1.0 - 0.02 * (s / 0.4)  # 1.00 → 0.98
        else:
            u = (s - 0.4) / 0.6
            beta = 0.98 - 0.08 * (u ** 1.2)  # 0.98 → ~0.90
    else:
        beta = 1.0

    r_gain, g_gain, b_gain = _kelvin_to_gains(kelvin, preserve_peak=True)
    r, g, b = _build_lut_color_tint(n, r_gain, g_gain, b_gain, beta=beta)

    if _apply_rgb_tables(r, g, b):
        CURRENT.update({"enabled": True, "kelvin": kelvin, "beta": beta, "n": n})
        _log(f"Applied warmth: strength={s_user:.3f} remap={s:.3f} → {kelvin:.0f}K, "
             f"gains=({r_gain:.3f},{g_gain:.3f},{b_gain:.3f}), beta={beta:.3f}, n={n}")
    else:
        _log("No active displays — warmth LUT not applied")

def disable() -> None:
    CURRENT["enabled"] = False
    CGDisplayRestoreColorSyncSettings()
    _log("Disabled (restored original colors)")

def reapply_if_enabled(*_args) -> None:
    if not CURRENT.get("enabled", False):
        return
    k = CURRENT.get("kelvin", 6500.0)
    beta = CURRENT.get("beta", 1.0)
    n = CURRENT.get("n", 512)
    r_gain, g_gain, b_gain = _kelvin_to_gains(k, preserve_peak=True)
    r, g, b = _build_lut_color_tint(n, r_gain, g_gain, b_gain, beta=beta)
    if _apply_rgb_tables(r, g, b):
        _log(f"Reapplied warmth at {k:.0f}K, beta={beta:.3f}")

# --------------------------------------------------------------------
# Display change callbacks
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
# Convenience: set by target kelvin (bypassing slider mapping)
# --------------------------------------------------------------------
def set_kelvin(kelvin: float, *, n: int = 512, beta: float = 1.0) -> None:
    k = max(1000.0, min(6500.0 if kelvin >= 6500 else 10000.0, kelvin))
    r_gain, g_gain, b_gain = _kelvin_to_gains(k, preserve_peak=True)
    r, g, b = _build_lut_color_tint(n, r_gain, g_gain, b_gain, beta=beta)
    if _apply_rgb_tables(r, g, b):
        CURRENT.update({"enabled": True, "kelvin": k, "beta": beta, "n": n})
        _log(f"Applied kelvin={k:.0f}, beta={beta:.3f}, n={n}")
    else:
        _log("No active displays — kelvin LUT not applied")
