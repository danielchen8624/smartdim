# smartdim/menubar.py
from __future__ import annotations

from AppKit import (  # type: ignore
    NSApplication, NSApp, NSStatusBar, NSVariableStatusItemLength,
    NSMenu, NSMenuItem, NSWorkspace, NSView, NSSlider, NSTextField,
    NSApplicationActivationPolicyAccessory,
)
from Foundation import NSObject  # type: ignore

# --- Brightness (your LUT engine) ---
from smartdim.lut import (  # type: ignore
    set_intensity as lut_set_intensity,
    disable as lut_disable,
    register_display_callbacks as lut_register_callbacks,
    reapply_if_enabled as lut_reapply_if_enabled,
    unregister_display_callbacks as lut_unregister_callbacks,
)

# --- Warmth (f.lux-style) ---
from smartdim.warmth import (  # type: ignore
    set_warmth,
    disable as warmth_disable,
    register_display_callbacks as warmth_register_callbacks,
    reapply_if_enabled as warmth_reapply_if_enabled,
    unregister_display_callbacks as warmth_unregister_callbacks,
)

ICON_EMOJI = "🌙"


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, _):
        # -------- App state --------
        self.isMutedLUT = False
        self.isMutedWarmth = False
        self.lastLUT = 0.0       # brightness strength (0..1)
        self.lastWarmth = 0.0    # warmth strength (0..1)

        # -------- Status item --------
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.statusItem.setTitle_(ICON_EMOJI)

        # -------- Menu --------
        menu = NSMenu.alloc().init()

        # Brightness (LUT) section
        lbl_b = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Brightness", None, "")
        lbl_b.setEnabled_(False)
        menu.addItem_(lbl_b)
        menu.addItem_(self._slider_item_lut(initial=self.lastLUT))

        menu.addItem_(NSMenuItem.separatorItem())

        # Warmth section
        lbl_w = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Warmth (f.lux-style)", None, "")
        lbl_w.setEnabled_(False)
        menu.addItem_(lbl_w)
        menu.addItem_(self._slider_item_warmth(initial=self.lastWarmth))

        menu.addItem_(NSMenuItem.separatorItem())

        # Toggles
        self.toggle_brightness_item = self._make_item("Toggle Brightness Off", "toggleBrightnessAction:")
        menu.addItem_(self.toggle_brightness_item)

        self.toggle_warmth_item = self._make_item("Toggle Warmth Off", "toggleWarmthAction:")
        menu.addItem_(self.toggle_warmth_item)

        # Optional reset
        menu.addItem_(self._make_item("Reset (Restore Colors)", "resetAction:"))

        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(self._make_item("Quit", "quitAction:"))

        self.statusItem.setMenu_(menu)

        # -------- Notifications / display callbacks --------
        self._install_notifications()
        lut_register_callbacks()
        warmth_register_callbacks()

    # =========================
    # Helpers
    # =========================
    def _make_item(self, title, action):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        item.setTarget_(self)
        return item

    def _slider_item_lut(self, initial: float = 0.0) -> NSMenuItem:
        container = NSView.alloc().initWithFrame_(((0, 0), (240, 44)))

        slider = NSSlider.alloc().initWithFrame_(((8, 8), (180, 20)))
        slider.setMinValue_(0.0)
        slider.setMaxValue_(1.0)
        slider.setFloatValue_(float(initial))
        slider.setContinuous_(True)
        slider.setTarget_(self)
        slider.setAction_("lutSliderChanged:")
        container.addSubview_(slider)
        self.lutSlider = slider

        value_label = NSTextField.alloc().initWithFrame_(((192, 8), (40, 20)))
        value_label.setEditable_(False)
        value_label.setBordered_(False)
        value_label.setDrawsBackground_(False)
        value_label.setAlignment_(1)  # right
        value_label.setStringValue_(f"{int(round(initial*100))}%")
        container.addSubview_(value_label)
        self.lutValueLabel = value_label

        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        mi.setView_(container)
        return mi

    def _slider_item_warmth(self, initial: float = 0.0) -> NSMenuItem:
        container = NSView.alloc().initWithFrame_(((0, 0), (240, 44)))

        slider = NSSlider.alloc().initWithFrame_(((8, 8), (180, 20)))
        slider.setMinValue_(0.0)
        slider.setMaxValue_(1.0)
        slider.setFloatValue_(float(initial))
        slider.setContinuous_(True)
        slider.setTarget_(self)
        slider.setAction_("warmthSliderChanged:")
        container.addSubview_(slider)
        self.warmthSlider = slider

        value_label = NSTextField.alloc().initWithFrame_(((192, 8), (40, 20)))
        value_label.setEditable_(False)
        value_label.setBordered_(False)
        value_label.setDrawsBackground_(False)
        value_label.setAlignment_(1)  # right
        value_label.setStringValue_(f"{int(round(initial*100))}%")
        container.addSubview_(value_label)
        self.warmthValueLabel = value_label

        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        mi.setView_(container)
        return mi

    def _update_toggle_titles(self):
        self.toggle_brightness_item.setTitle_("Toggle Brightness On" if self.isMutedLUT else "Toggle Brightness Off")
        self.toggle_warmth_item.setTitle_("Toggle Warmth On" if self.isMutedWarmth else "Toggle Warmth Off")

    # =========================
    # Actions: Brightness (LUT)
    # =========================
    def lutSliderChanged_(self, sender):
        val = float(sender.floatValue())  # 0..1
        self.lastLUT = val
        self.lutValueLabel.setStringValue_(f"{int(round(val * 100))}%")
        if self.isMutedLUT:
            return
        if val <= 0.001:
            lut_disable()  # restore colors for LUT path
        else:
            lut_set_intensity(val)

    def toggleBrightnessAction_(self, _):
        self.isMutedLUT = not self.isMutedLUT
        self._update_toggle_titles()
        if self.isMutedLUT:
            lut_disable()
        else:
            val = float(self.lutSlider.floatValue())
            if val <= 0.001:
                lut_disable()
            else:
                lut_set_intensity(val)

    # =========================
    # Actions: Warmth
    # =========================
    def warmthSliderChanged_(self, sender):
        val = float(sender.floatValue())  # 0..1
        self.lastWarmth = val
        self.warmthValueLabel.setStringValue_(f"{int(round(val * 100))}%")
        if self.isMutedWarmth:
            return
        if val <= 0.001:
            warmth_disable()
        else:
            set_warmth(val)

    def toggleWarmthAction_(self, _):
        self.isMutedWarmth = not self.isMutedWarmth
        self._update_toggle_titles()
        if self.isMutedWarmth:
            warmth_disable()
        else:
            val = float(self.warmthSlider.floatValue())
            if val <= 0.001:
                warmth_disable()
            else:
                set_warmth(val)

    # =========================
    # Actions: Reset & Quit
    # =========================
    def resetAction_(self, _):
        # Restore colors and keep slider values (do not change UI)
        lut_disable()
        warmth_disable()

    def quitAction_(self, _):
        # 1) Restore colors
        try:
            lut_disable()
        except Exception:
            pass
        try:
            warmth_disable()
        except Exception:
            pass

        # 2) Unregister display callbacks
        try:
            lut_unregister_callbacks()
        except Exception:
            pass
        try:
            warmth_unregister_callbacks()
        except Exception:
            pass

        # 3) Remove wake observer
        try:
            NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self)
        except Exception:
            pass

        # 4) Remove status item so the menu bar icon disappears immediately
        try:
            NSStatusBar.systemStatusBar().removeStatusItem_(self.statusItem)
        except Exception:
            pass

        # 5) Terminate the app
        NSApp.terminate_(self)

    # =========================
    # Reapply after wake
    # =========================
    def _install_notifications(self):
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        center.addObserver_selector_name_object_(
            self, "reapplyNotif:", "NSWorkspaceDidWakeNotification", None
        )

    def reapplyNotif_(self, _):
        # Reapply brightness if not muted and > 0
        if not self.isMutedLUT and float(self.lutSlider.floatValue()) > 0.001:
            try:
                # If your lut.reapply_if_enabled() later stores params, use it; otherwise set explicitly
                lut_set_intensity(float(self.lutSlider.floatValue()))
            except Exception:
                lut_reapply_if_enabled()
        else:
            lut_disable()

        # Reapply warmth if not muted and > 0
        if not self.isMutedWarmth and float(self.warmthSlider.floatValue()) > 0.001:
            try:
                set_warmth(float(self.warmthSlider.floatValue()))
            except Exception:
                warmth_reapply_if_enabled()
        else:
            warmth_disable()


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
