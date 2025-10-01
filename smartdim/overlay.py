# smartdim/overlay.py
from __future__ import annotations
from typing import Dict
from AppKit import (
    NSApp, NSScreen, NSPanel,
    NSBorderlessWindowMask, NSApplication,
    NSBackingStoreBuffered, NSColor, NSView,
    NSNotificationCenter, NSBezierPath,
    NSScreenSaverWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
)
from Foundation import NSObject

# ------------------------------------------------------------
# Custom dim view (draws dual-layer overlay)
# ------------------------------------------------------------
class _DimView(NSView):
    def initWithAlpha_(self, a: float):
        self = super().initWithFrame_(((0, 0), (10, 10)))
        if self is None:
            return None
        self._alpha = max(0.0, min(1.0, a))
        return self

    def setAlpha_(self, a: float):
        self._alpha = max(0.0, min(1.0, a))
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        # Draw dark layer to dim highlights
        path = NSBezierPath.bezierPathWithRect_(rect)
        NSColor.colorWithCalibratedWhite_alpha_(0.0, self._alpha).set()
        path.fill()
        # Add faint white layer to lift shadows (avoid crushing blacks)
        lift_alpha = self._alpha * 0.15
        if lift_alpha > 0.0:
            NSColor.colorWithCalibratedWhite_alpha_(1.0, lift_alpha).set()
            path.fill()

# ------------------------------------------------------------
# Manager
# ------------------------------------------------------------
class DimOverlayManager(NSObject):
    def init(self):
        self = super().init()
        if self is None:
            return None
        self.windows: Dict[str, NSPanel] = {}
        self.alpha: float = 0.0
        center = NSNotificationCenter.defaultCenter()
        center.addObserver_selector_name_object_(
            self,
            "screensChanged:",
            "NSApplicationDidChangeScreenParametersNotification",
            None,
        )
        return self

    # Public API
    def enable_(self, alpha: float = 0.35):
        self.alpha = max(0.0, min(1.0, alpha))
        self._build_all()

    def setAlpha_(self, alpha: float):
        self.alpha = max(0.0, min(1.0, alpha))
        for w in self.windows.values():
            view = w.contentView()
            if hasattr(view, "setAlpha_"):
                view.setAlpha_(self.alpha)

    def disable(self):
        for w in self.windows.values():
            w.orderOut_(None)
        self.windows.clear()
        self.alpha = 0.0

    # Notification handler
    def screensChanged_(self, _note):
        if self.alpha > 0:
            self._build_all()

    # Build overlay windows for all screens
    def _build_all(self):
        self.disable()
        for screen in NSScreen.screens():
            frame = screen.frame()
            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                frame, NSBorderlessWindowMask, NSBackingStoreBuffered, False
            )
            panel.setLevel_(NSScreenSaverWindowLevel)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(NSColor.clearColor())
            panel.setIgnoresMouseEvents_(True)
            panel.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorFullScreenAuxiliary
                | NSWindowCollectionBehaviorStationary
            )
            view = _DimView.alloc().initWithAlpha_(self.alpha)
            panel.setContentView_(view)
            panel.orderFrontRegardless()
            self.windows[str(id(panel))] = panel

# ------------------------------------------------------------
# Singleton wrapper
# ------------------------------------------------------------
_manager: DimOverlayManager | None = None

def enable_overlay(alpha: float = 0.35):
    global _manager
    if _manager is None:
        _manager = DimOverlayManager.alloc().init()
    _manager.enable_(alpha)

def set_overlay(alpha: float):
    if _manager is not None:
        _manager.setAlpha_(alpha)

def disable_overlay():
    global _manager
    if _manager is not None:
        _manager.disable()
