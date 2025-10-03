from __future__ import annotations

from AppKit import (  # type: ignore
    NSApplication, NSApp, NSStatusBar, NSVariableStatusItemLength,
    NSMenu, NSMenuItem, NSWorkspace, NSView, NSSlider, NSTextField,
    NSApplicationActivationPolicyAccessory,
)
from Foundation import NSObject  # type: ignore

# --- Brightness module for callbacks + restore on quit 
from smartdim.lut import (  # type: ignore
    disable as lut_disable,
    register_display_callbacks as lut_register_callbacks,
    reapply_if_enabled as lut_reapply_if_enabled,
    unregister_display_callbacks as lut_unregister_callbacks,
)

# --- Warmth module for callbacks + restore on quit 
from smartdim.warmth import (  # type: ignore
    disable as warmth_disable,
    register_display_callbacks as warmth_register_callbacks,
    reapply_if_enabled as warmth_reapply_if_enabled,
    unregister_display_callbacks as warmth_unregister_callbacks,
)

# Composer to combine brightness + warmth into single LUT
from smartdim.composer import (  # type: ignore
    apply_combined as apply_combined_lut_warmth,
    restore_colors as compose_restore,
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
        lbl_w = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Warmth", None, "")
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

    def _apply_current(self):
        """
        Compose current Brightness + Warmth into a single LUT and apply once.
        Muted effects are treated as zero.
        """
        intensity = 0.0 if self.isMutedLUT else float(self.lutSlider.floatValue())
        warmth    = 0.0 if self.isMutedWarmth else float(self.warmthSlider.floatValue())

        # Update labels (keep UI in sync even if muted)
        self.lutValueLabel.setStringValue_(f"{int(round(float(self.lutSlider.floatValue()) * 100))}%")
        self.warmthValueLabel.setStringValue_(f"{int(round(float(self.warmthSlider.floatValue()) * 100))}%")

        if intensity <= 0.001 and warmth <= 0.001:
            compose_restore()
        else:
            apply_combined_lut_warmth(intensity, warmth, n=512)

    # =========================
    # Actions: Brightness (LUT)
    # =========================
    def lutSliderChanged_(self, sender):
        val = float(sender.floatValue())  # 0..1
        self.lastLUT = val
        self.lutValueLabel.setStringValue_(f"{int(round(val * 100))}%")
        self._apply_current()

    def toggleBrightnessAction_(self, _):
        self.isMutedLUT = not self.isMutedLUT
        self._update_toggle_titles()
        self._apply_current()

    # =========================
    # Actions: Warmth
    # =========================
    def warmthSliderChanged_(self, sender):
        val = float(sender.floatValue())  # 0..1
        self.lastWarmth = val
        self.warmthValueLabel.setStringValue_(f"{int(round(val * 100))}%")
        self._apply_current()

    def toggleWarmthAction_(self, _):
        self.isMutedWarmth = not self.isMutedWarmth
        self._update_toggle_titles()
        self._apply_current()

    # =========================
    # Actions: Reset & Quit
    # =========================
    def resetAction_(self, _):
        # Restore colors and keep slider values (do not change UI)
        compose_restore()

    def quitAction_(self, _):
        # 1) Restore colors
        try:
            compose_restore()
        except Exception:
            # Fallback: call individual restores
            try: lut_disable()
            except Exception: pass
            try: warmth_disable()
            except Exception: pass

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
        # Simply reapply the current combined state; respects mutes
        self._apply_current()


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
