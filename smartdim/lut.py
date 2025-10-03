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

# State + logs
CURRENT = {"enabled": False, "tau": 0.0, "alpha": 0.0, "beta": 1.0, "n": 512}
LOG = True  # SET LATER TO FALSE TO DISABLE LOGS
WHITE_CAP: Optional[float] = None  # for whites

def _log(*a) -> None:
    if LOG:
        print("[smartdim]", *a)


# --------------------------------------------------------------------
def _monotone_clip(ys: List[float]) -> List[float]:
    ys = [0.0 if y < 0.0 else 1.0 if y > 1.0 else y for y in ys]
    for i in range(1, len(ys)):
        if ys[i] < ys[i - 1]:
            ys[i] = ys[i - 1]
    return ys

def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Hermite smoothstep (0→1) between edge0 and edge1."""
    if x <= edge0: return 0.0
    if x >= edge1: return 1.0
    t = (x - edge0) / (edge1 - edge0)
    return t * t * (3 - 2 * t)

def _remap_slider(s_raw: float) -> float:
    """
    Perceptual remap: makes the slider feel linear to the eye.
    - Gamma-like boost (exp < 1) to increase early response.
    - Mild S-curve to avoid a cliff near the end.
    """
    s = 0.0 if s_raw < 0.0 else 1.0 if s_raw > 1.0 else float(s_raw)

    # gamma pre-emphasis (lower => punchier early response)
    g = 0.65  #.55..0.75 works best so far ive tested
    s = s ** g

    # gentle S-curve around the middle
    k = 0.35
    y = 0.5 + (s - 0.5) * (1 + k - k * 4.0 * abs(s - 0.5))

    # clamp
    if y < 0.0: y = 0.0
    if y > 1.0: y = 1.0
    return y

# --------------------------------------------------------------------
def build_lut_subtractive_guarded(
    n: int,
    guard: float,          # luminance where dimming starts
    guard_width: float,    # soft ramp width
    offset: float,         # subtractive amount
    beta: float = 1.0,     # global dim multiplier
    white_cap: Optional[float] = WHITE_CAP,
) -> Tuple[array.array, array.array, array.array]:
    g0 = max(0.0, min(1.0, guard))
    g1 = max(g0, min(0.999, g0 + max(0.002, guard_width)))
    off = max(0.0, min(1.0, offset))
    b = 1.0 if beta is None else max(0.0, min(1.0, beta))

    xs = [i / (n - 1) for i in range(n)]
    ys: List[float] = []
    for x in xs:
        y_sub = max(0.0, x - off)   # subtractive (constant-difference above guard, prevents blending but doesnt darken everything at once
        w = _smoothstep(g0, g1, x)  # 0..1 blend across the guard band
        y = (1.0 - w) * x + w * y_sub
        ys.append(y)

#global dim
    if b != 1.0:
        ys = [y * b for y in ys]

    if white_cap is not None:
        ys[-1] = min(ys[-1], white_cap)

    ys = _monotone_clip(ys)
    arr = array.array("f", ys)
    return arr, arr, arr

#--------------------------------------------------------------------
def _active_displays(max_count: int = 16) -> List[int]:
    err, displays, count = CGGetActiveDisplayList(max_count, None, None)
    if err != 0 or count == 0:
        _log("CGGetActiveDisplayList err or empty:", err, count)
        return []
    ids = list(displays)[:count]
    _log(f"🖥️ Active displays ({count}):", ids)
    return ids

# helpers
def _apply_rgb_tables(r: array.array, g: array.array, b: array.array) -> bool:
    applied = False
    for d in _active_displays():
        CGSetDisplayTransferByTable(d, len(r), r, g, b)
        applied = True
    return applied

def apply_lut_subtractive_guarded(
    guard: float,
    guard_width: float,
    offset: float,
    n: int = 512,
    beta: float = 1.0,
    white_cap: Optional[float] = WHITE_CAP,
) -> None:
    r, g, b = build_lut_subtractive_guarded(n, guard, guard_width, offset, beta, white_cap)
    if _apply_rgb_tables(r, g, b):
        _log(f" Applied subtractive-guarded LUT: guard={guard:.3f}±{guard_width:.3f}, "
             f"offset={offset:.3f}, beta={beta:.3f}, n={n}")
    else:
        _log(" No active displays — LUT not applied")

# --------------------------------------------------------------------
def enable_demo_whites_first() -> None:
    apply_lut_subtractive_guarded(guard=0.90, guard_width=0.05, offset=0.12, n=512, beta=1.0)
    CURRENT.update({"enabled": True, "beta": 1.0, "n": 512})
    _log("Enabled (demo whites-first subtractive)")

def enable(*_args, **_kwargs): enable_demo_whites_first()
def enable_aggressive(): set_intensity(0.70)
def enable_extra_aggressive(): set_intensity(0.85)
def enable_nuclear(): set_intensity(1.00)

# --------------------------------------------------------------------
def disable() -> None:
    CURRENT["enabled"] = False
    CGDisplayRestoreColorSyncSettings()
    _log("Disabled (restored original colors)")

def toggle() -> None:
    if CURRENT["enabled"]:
        disable()
    else:
        set_intensity(0.4)

def reapply_if_enabled(*_args) -> None:
    pass

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
# Flat LUT for debugging
def enable_flat(level: float = 0.20, n: int = 256) -> None:
    level = 0.0 if level < 0.0 else 1.0 if level > 1.0 else level
    arr = array.array("f", [level] * n)
    changed = False
    for d in _active_displays():
        CGSetDisplayTransferByTable(d, n, arr, arr, arr)
        changed = True
    if changed:
        _log(f" Flat LUT applied at {level:.2f}")
        CURRENT.update({"enabled": True, "n": n})
    else:
        _log(" No active displays — flat LUT not applied")

# --------------------------------------------------------------------
def set_intensity(intensity: float, n: int = 512) -> None:
    """
    Perceptually-linear slider (to human eyes).
    0.0 -> EXACTLY no effect (restores system colors).
    """
    s_user = 0.0 if intensity < 0.0 else 1.0 if intensity > 1.0 else float(intensity)

    if s_user <= 1e-3:
        CGDisplayRestoreColorSyncSettings()
        CURRENT.update({"enabled": False})
        _log("Intensity 0 → restored original colors (no effect)")
        return

    s = _remap_slider(s_user)

    # Even thirds: A/B/C each get ~1/3 of travel for steadier feel, splits to prevent blending of similar brightnesses while ensuring not all goes dark at once
    splitA = 1.0 / 3.0   # ~0.333
    splitB = 2.0 / 3.0   # ~0.666
    guard_width = 0.050  # widen slightly for softer band edge

    if s <= splitA:
        # ---------- Phase A: whites-first; protect greys ----------
        u = s / splitA  # 0..1 inside phase
        guard  = 0.94 - 0.10 * u   # 0.94 -> 0.84
        offset = 0.00 + 0.14 * u   # 0.00 -> 0.14
        beta   = 1.0 - 0.03 * u    # 1.00 _> 0.97

    elif s <= splitB:
        # ---------- Phase B: expand subtractive band ----------
        u = (s - splitA) / (splitB - splitA)  # 0..1
        guard  = 0.84 - 0.24 * u   # 0.84 -> 0.60
        offset = 0.14 + 0.12 * u   # 0.14 -> 0.26
        beta   = 0.97 - 0.07 * u   # 0.97 -> 0.90

    else:
        # ---------- Phase C: subtractive + global dim -> nuclear ----------
        u = (s - splitB) / (1.0 - splitB)  # 0..1
        guard  = 0.60 - 0.22 * u   # 0.60 -> 0.38 (pull mids in)
        offset = 0.26 + 0.18 * u   # 0.26 -> 0.44 (heavy subtractive)

        # Make beta continuous at B->C:
        beta_floor = 0.55            # endpoint darkness; 0.50 is spicier
        beta_start = 0.97 - 0.07*1.0 # = 0.90 (Phase-B end value)
        beta       = beta_start - (beta_start - beta_floor) * (u ** 1.0)
        # so: u=0 -> 0.90, u=1 -> 0.55 (no brightening step)

    apply_lut_subtractive_guarded(
        guard=guard,
        guard_width=guard_width,
        offset=offset,
        n=n,
        beta=beta,
        white_cap=WHITE_CAP,
    )
    CURRENT.update({"enabled": True, "beta": beta, "n": n})
    _log(
        f"Intensity user={s_user:.3f} → comp={s:.3f} | "
        f"guard={guard:.3f}±{guard_width:.3f}, offset={offset:.3f}, beta={beta:.3f}"
    )
