# smartdim/menubar.py
from __future__ import annotations

from AppKit import (  # type: ignore
    NSApplication, NSStatusBar, NSVariableStatusItemLength,
    NSMenu, NSMenuItem, NSWorkspace,
    NSApplicationActivationPolicyAccessory,
)
from Foundation import NSObject  # type: ignore

# --- SmartDim imports ---
from smartdim.lut import (  # type: ignore
    enable, disable, toggle,
    enable_aggressive, enable_extra_aggressive, enable_nuclear,
    reapply_if_enabled, register_display_callbacks,
)
from smartdim.overlay import (  # type: ignore
    enable_overlay, set_overlay, disable_overlay,
)

ICON_EMOJI = "🌙"

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, _):
        # Status item
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.statusItem.setTitle_(ICON_EMOJI)

        # Menu
        menu = NSMenu.alloc().init()

        # LUT actions
        enable_item  = self._make_item("Enable Smart Dim", "onAction:")
        disable_item = self._make_item("Disable", "offAction:")
        toggle_item  = self._make_item("Toggle", "toggleAction:")
        aggr_item    = self._make_item("Aggressive (test)", "aggrAction:")
        extra_item   = self._make_item("Extra Aggressive", "extraAggrAction:")
        nuclear_item = self._make_item("Nuclear (extreme)", "nuclearAction:")

        # Presets submenu
        presets = NSMenu.alloc().init()
        presets.addItem_(self._make_preset_item("Reading (strong)", 0.55, 0.85))
        presets.addItem_(self._make_preset_item("Coding (medium)",  0.62, 0.65))
        presets.addItem_(self._make_preset_item("Movie (light)",    0.68, 0.45))
        presets_item = NSMenuItem.alloc().init()
        presets_item.setTitle_("Presets")
        presets_item.setSubmenu_(presets)

        # Overlay submenu
        overlay = NSMenu.alloc().init()
        overlay.addItem_(self._make_overlay_item("Overlay 20%", 0.20))
        overlay.addItem_(self._make_overlay_item("Overlay 35%", 0.35))
        overlay.addItem_(self._make_overlay_item("Overlay 50%", 0.50))
        overlay.addItem_(self._make_overlay_item("Overlay 70%", 0.70))
        overlay.addItem_(NSMenuItem.separatorItem())
        off_item = self._make_item("Overlay Off", "overlayOff:")
        overlay.addItem_(off_item)
        overlay_item = NSMenuItem.alloc().init()
        overlay_item.setTitle_("Overlay Mode")
        overlay_item.setSubmenu_(overlay)

        # Quit
        quit_item = self._make_item("Quit", "quitAction:")

        # Build menu
        menu.addItem_(enable_item)
        menu.addItem_(disable_item)
        menu.addItem_(toggle_item)
        menu.addItem_(aggr_item)
        menu.addItem_(extra_item)
        menu.addItem_(nuclear_item)
        menu.addItem_(presets_item)
        menu.addItem_(overlay_item)
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(quit_item)
        self.statusItem.setMenu_(menu)

        # Notifications / display callbacks
        self._install_notifications()
        register_display_callbacks()

    # --- helper builders ---
    def _make_item(self, title, action):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        item.setTarget_(self)
        return item

    def _make_preset_item(self, title, tau, alpha):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "presetAction:", "")
        item.setRepresentedObject_({"tau": tau, "alpha": alpha})
        item.setTarget_(self)
        return item

    def _make_overlay_item(self, title, alpha):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "overlaySet:", "")
        item.setRepresentedObject_(alpha)
        item.setTarget_(self)
        return item

    # --- Actions ---
    def onAction_(self, _):        print("[smartdim] enable");  enable()
    def offAction_(self, _):       print("[smartdim] disable"); disable()
    def toggleAction_(self, _):    print("[smartdim] toggle");  toggle()
    def aggrAction_(self, _):      print("[smartdim] aggressive"); enable_aggressive()
    def extraAggrAction_(self, _): print("[smartdim] extra aggressive"); enable_extra_aggressive()
    def nuclearAction_(self, _):   print("[smartdim] nuclear"); enable_nuclear()

    def presetAction_(self, sender):
        cfg = sender.representedObject()
        print("[smartdim] preset", cfg)
        enable(cfg["tau"], cfg["alpha"])

    # Overlay actions
    def overlaySet_(self, sender):
        alpha = sender.representedObject()
        print(f"[smartdim] overlay enable {alpha}")
        enable_overlay(alpha)

    def overlayOff_(self, _):
        print("[smartdim] overlay off")
        disable_overlay()

    # Quit
    def quitAction_(self, _):
        print("[smartdim] quit")
        disable_overlay()
        disable()
        import sys
        sys.exit(0)

    # --- Notifications ---
    def _install_notifications(self):
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        center.addObserver_selector_name_object_(
            self, "reapplyNotif:", "NSWorkspaceDidWakeNotification", None
        )

    def reapplyNotif_(self, _):
        reapply_if_enabled()

# --------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------
def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()

if __name__ == "__main__":
    main()
