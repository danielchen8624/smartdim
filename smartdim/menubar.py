# smartdim/menubar.py
from __future__ import annotations
from AppKit import (  # type: ignore
    NSApplication, NSStatusBar, NSVariableStatusItemLength,
    NSMenu, NSMenuItem, NSWorkspace, NSView, NSSlider,
    NSApplicationActivationPolicyAccessory,
)
from Foundation import NSObject  # type: ignore

from smartdim.lut import (  # type: ignore
    enable, disable, toggle,
    enable_aggressive, enable_extra_aggressive, enable_nuclear,
    reapply_if_enabled, register_display_callbacks,
    set_intensity,
)

ICON_EMOJI = "🌙"

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, _):
        # Status item
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.statusItem.setTitle_(ICON_EMOJI)

        menu = NSMenu.alloc().init()

        # --- LUT actions
        menu.addItem_(self._make_item("Enable Smart Dim (LUT)", "onAction:"))
        menu.addItem_(self._make_item("Disable", "offAction:"))
        menu.addItem_(self._make_item("Toggle", "toggleAction:"))
        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(self._make_item("Aggressive (preset)", "aggrAction:"))
        menu.addItem_(self._make_item("Extra Aggressive (preset)", "extraAggrAction:"))
        menu.addItem_(self._make_item("Nuclear (preset)", "nuclearAction:"))
        menu.addItem_(NSMenuItem.separatorItem())

        # --- Smart Dim (LUT) intensity slider (0 = no effect → almost nuclear)
        lut_label = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Smart Dim Intensity (0 = no effect → almost nuclear)", None, ""
        )
        lut_label.setEnabled_(False)
        menu.addItem_(lut_label)
        menu.addItem_(self._slider_item(selector="lutSliderChanged:", initial=0.0))  # start at 0

        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(self._make_item("Quit", "quitAction:"))

        self.statusItem.setMenu_(menu)

        # Notifications / display callbacks
        self._install_notifications()
        register_display_callbacks()

    # ----- helpers -----
    def _make_item(self, title, action):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        item.setTarget_(self)
        return item

    def _slider_item(self, selector: str, initial: float = 0.0):
        # A view-backed menu item hosting an NSSlider (0..1)
        container = NSView.alloc().initWithFrame_(((0, 0), (220, 30)))
        slider = NSSlider.alloc().initWithFrame_(((8, 6), (204, 18)))
        slider.setMinValue_(0.0)
        slider.setMaxValue_(1.0)
        slider.setFloatValue_(float(initial))
        slider.setContinuous_(True)
        slider.setTarget_(self)
        slider.setAction_(selector)
        container.addSubview_(slider)

        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        mi.setView_(container)
        return mi

    # ----- Actions -----
    # LUT presets
    def onAction_(self, _):        print("[smartdim] enable (LUT)");  enable()
    def offAction_(self, _):       print("[smartdim] disable");       disable()
    def toggleAction_(self, _):    print("[smartdim] toggle");        toggle()
    def aggrAction_(self, _):      print("[smartdim] aggressive");    enable_aggressive()
    def extraAggrAction_(self, _): print("[smartdim] extra agg");     enable_extra_aggressive()
    def nuclearAction_(self, _):   print("[smartdim] nuclear");       enable_nuclear()

    # Slider: 0 = exact no-effect (restore), >0 = apply curve
    def lutSliderChanged_(self, sender):
        val = float(sender.floatValue())
        print(f"[smartdim] LUT intensity → {val:.3f}")
        if val <= 0.001:
            disable()           # exact pass-through (restore system colors)
        else:
            set_intensity(val)

    # Quit
    def quitAction_(self, _):
        print("[smartdim] quit")
        disable()
        import sys
        sys.exit(0)

    # Reapply after wake
    def _install_notifications(self):
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        center.addObserver_selector_name_object_(self, "reapplyNotif:", "NSWorkspaceDidWakeNotification", None)
    def reapplyNotif_(self, _): reapply_if_enabled()

def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()

if __name__ == "__main__":
    main()
