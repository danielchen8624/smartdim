from __future__ import annotations

import array
from typing import Tuple, List

from Quartz import (
    CGGetActiveDisplayList,
    CGSetDisplayTransferByTable,
    CGDisplayRestoreColorSyncSettings,
)

# Import helpers from your existing modules (ok to import underscored)
from smartdim.lut import _remap_slider as _remap_brightness_slider
from smartdim.lut import build_lut_subtractive_guarded as _build_brightness_lut

from smartdim.warmth import _remap_slider as _remap_warmth_slider
from smartdim.warmth import _kelvin_to_gains as _kelvin_to_gains
from smartdim.warmth import _build_lut_color_tint as _build_warmth_luts

LOG = True
def _log(*a): 
    if LOG: print("[compose]", *a)

def _active_displays(max_count: int = 16) -> List[int]:
    err, displays, count = CGGetActiveDisplayList(max_count, None, None)
    if err != 0 or count == 0:
        _log("CGGetActiveDisplayList err or empty:", err, count)
        return []
    return list(displays)[:count]

def restore_colors() -> None:
    CGDisplayRestoreColorSyncSettings()
    _log("Restored original display colors")

# --- Recreate the brightness parameter mapping without applying ---
def _brightness_params_from_slider(s_user: float):
    """Reproduce smartdim.lut.set_intensity's parameter mapping, but do not apply."""
    s_user = 0.0 if s_user < 0.0 else 1.0 if s_user > 1.0 else float(s_user)
    if s_user <= 1e-3:
        return None  # means 'identity'

    s = _remap_brightness_slider(s_user)

    splitA = 1.0 / 3.0
    splitB = 2.0 / 3.0
    guard_width = 0.050

    if s <= splitA:
        u = s / splitA
        guard  = 0.94 - 0.10 * u
        offset = 0.00 + 0.14 * u
        beta   = 1.00 - 0.03 * u

    elif s <= splitB:
        u = (s - splitA) / (splitB - splitA)
        guard  = 0.84 - 0.24 * u
        offset = 0.14 + 0.12 * u
        beta   = 0.97 - 0.07 * u

    else:
        u = (s - splitB) / (1.0 - splitB)
        guard  = 0.60 - 0.22 * u
        offset = 0.26 + 0.18 * u
        beta_floor = 0.55
        beta_start = 0.90
        beta       = beta_start - (beta_start - beta_floor) * (u ** 1.0)

    return guard, guard_width, offset, beta

def _build_brightness_only_lut(intensity: float, n: int) -> Tuple[array.array, array.array, array.array]:
    params = _brightness_params_from_slider(intensity)
    if params is None:
        # Identity LUT
        xs = [i / (n - 1) for i in range(n)]
        arr = array.array("f", xs)
        return arr, arr, arr

    guard, guard_width, offset, beta = params
    return _build_brightness_lut(n=n, guard=guard, guard_width=guard_width, offset=offset, beta=beta)

def _build_warmth_only_luts(strength: float, n: int) -> Tuple[array.array, array.array, array.array]:
    s_user = 0.0 if strength < 0.0 else 1.0 if strength > 1.0 else float(strength)
    if s_user <= 1e-3:
        xs = [i / (n - 1) for i in range(n)]
        arr = array.array("f", xs)
        return arr, arr, arr

    s = _remap_warmth_slider(s_user)
    kelvin_min, kelvin_max = 1900.0, 6500.0
    # mired interpolation
    m_max = 1e6 / kelvin_max
    m_min = 1e6 / kelvin_min
    m = m_max + (m_min - m_max) * s
    kelvin = max(kelvin_min, min(kelvin_max, 1e6 / m))

    # gentle beta curve (same logic as warmth.set_warmth)
    if s < 0.4:
        beta = 1.0 - 0.02 * (s / 0.4)
    else:
        u = (s - 0.4) / 0.6
        beta = 0.98 - 0.08 * (u ** 1.2)

    r_gain, g_gain, b_gain = _kelvin_to_gains(kelvin, preserve_peak=True)
    return _build_warmth_luts(n, r_gain, g_gain, b_gain, beta=beta)

def _compose_luts(
    base_r: array.array, base_g: array.array, base_b: array.array,
    tint_r: array.array, tint_g: array.array, tint_b: array.array
) -> Tuple[array.array, array.array, array.array]:
    """
    Compose LUTs as functions: out(x) = Tint(Base(x))
    Implemented by resampling Tint at Base(x).
    """
    n = len(base_r)
    def sample(arr: array.array, y: float) -> float:
        j = int(round(max(0.0, min(1.0, y)) * (n - 1)))
        return float(arr[j])

    out_r = array.array("f", [0.0]*n)
    out_g = array.array("f", [0.0]*n)
    out_b = array.array("f", [0.0]*n)

    for i in range(n):
        y_r = float(base_r[i])
        y_g = float(base_g[i])
        y_b = float(base_b[i])
        out_r[i] = sample(tint_r, y_r)
        out_g[i] = sample(tint_g, y_g)
        out_b[i] = sample(tint_b, y_b)

    return out_r, out_g, out_b

def apply_combined(intensity: float, warmth_strength: float, n: int = 512) -> None:
    """
    Build brightness + warmth LUTs, compose them, and apply once.
    Either control may be 0.0 (treated as identity).
    """
    # If both are ~zero, restore system colors
    if (intensity <= 1e-3) and (warmth_strength <= 1e-3):
        restore_colors()
        return

    b_r, b_g, b_b = _build_brightness_only_lut(intensity, n)
    w_r, w_g, w_b = _build_warmth_only_luts(warmth_strength, n)
    r, g, b = _compose_luts(b_r, b_g, b_b, w_r, w_g, w_b)

    changed = False
    for d in _active_displays():
        CGSetDisplayTransferByTable(d, n, r, g, b)
        changed = True
    if changed:
        _log(f"Applied combined LUT: intensity={intensity:.3f}, warmth={warmth_strength:.3f}, n={n}")
    else:
        _log("No active displays — combined LUT not applied")
