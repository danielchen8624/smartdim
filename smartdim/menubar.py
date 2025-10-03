from __future__ import annotations

from AppKit import (  # type: ignore
    NSApplication, NSApp, NSStatusBar, NSVariableStatusItemLength,
    NSMenu, NSMenuItem, NSWorkspace, NSView, NSSlider, NSTextField,
    NSApplicationActivationPolicyAccessory,
)
from Foundation import NSObject  # type: ignore

# Brightness 
from smartdim.lut import (  # type: ignore
    disable as lut_disable,
    register_display_callbacks as lut_register_callbacks,
    reapply_if_enabled as lut_reapply_if_enabled,
    unregister_display_callbacks as lut_unregister_callbacks,
)

# Warmth  
from smartdim.warmth import (  # type: ignore
    disable as warmth_disable,
    register_display_callbacks as warmth_register_callbacks,
    reapply_if_enabled as warmth_reapply_if_enabled,
    unregister_display_callbacks as warmth_unregister_callbacks,
)

#  Compose to combine warmth + brightness
from smartdim.composer import (  # type: ignore
    apply_combined as apply_combined_lut_warmth,
    restore_colors as compose_restore,
)

ICON_EMOJI = "🌙"


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, _):
        #app state
        self.isMutedLUT = False
        self.isMutedWarmth = False
        self.lastLUT = 0.0       # brightness strength (0..1)
        self.lastWarmth = 0.0    # warmth strength (0..1)

        # status item
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.statusItem.setTitle_(ICON_EMOJI)

    
        menu = NSMenu.alloc().init()

        # LUT
        lbl_b = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Brightness", None, "")
        lbl_b.setEnabled_(False)
        menu.addItem_(lbl_b)
        menu.addItem_(self._slider_item_lut(initial=self.lastLUT))

        menu.addItem_(NSMenuItem.separatorItem())

        # Warmth 
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

        menu.addItem_(NSMenuItem.separatorItem())
        menu.addItem_(self._make_item("Quit", "quitAction:"))

        self.statusItem.setMenu_(menu)

        # Init titles
        self._install_notifications()
        lut_register_callbacks()
        warmth_register_callbacks()

    def _make_item(self, title, action):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
        item.setTarget_(self)
        return item

    def _format_percent(self, value: float) -> str:
        """Show slider value as percentage with '%' suffix."""
        return f"{int(round(value * 100))}%"

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
        value_label.setAlignment_(1)
        value_label.setStringValue_(self._format_percent(initial))
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
        value_label.setAlignment_(1)
        value_label.setStringValue_(self._format_percent(initial))
        container.addSubview_(value_label)
        self.warmthValueLabel = value_label

        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        mi.setView_(container)
        return mi

    def _update_toggle_titles(self):
        self.toggle_brightness_item.setTitle_("Toggle Brightness On" if self.isMutedLUT else "Toggle Brightness Off")
        self.toggle_warmth_item.setTitle_("Toggle Warmth On" if self.isMutedWarmth else "Toggle Warmth Off")

    def _apply_current(self):
        """Compose current Brightness + Warmth into a single LUT and apply once."""
        intensity = 0.0 if self.isMutedLUT else float(self.lutSlider.floatValue())
        warmth    = 0.0 if self.isMutedWarmth else float(self.warmthSlider.floatValue())


        self.lutValueLabel.setStringValue_(self._format_percent(float(self.lutSlider.floatValue())))
        self.warmthValueLabel.setStringValue_(self._format_percent(float(self.warmthSlider.floatValue())))

        if intensity <= 0.001 and warmth <= 0.001:
            compose_restore()
        else:
            apply_combined_lut_warmth(intensity, warmth, n=512)

   #ACTIONS
   #brightness
    def lutSliderChanged_(self, sender):
        val = float(sender.floatValue())
        self.lastLUT = val
        self.lutValueLabel.setStringValue_(self._format_percent(val))
        self._apply_current()

    def toggleBrightnessAction_(self, _):
        self.isMutedLUT = not self.isMutedLUT
        self._update_toggle_titles()
        self._apply_current()

    #warmth
    def warmthSliderChanged_(self, sender):
        val = float(sender.floatValue())
        self.lastWarmth = val
        self.warmthValueLabel.setStringValue_(self._format_percent(val))
        self._apply_current()

    def toggleWarmthAction_(self, _):
        self.isMutedWarmth = not self.isMutedWarmth
        self._update_toggle_titles()
        self._apply_current()

    #quit
    def quitAction_(self, _):
        # restore colours
        try:
            compose_restore()
        except Exception:
            try: lut_disable()
            except Exception: pass
            try: warmth_disable()
            except Exception: pass

        try:
            lut_unregister_callbacks()
        except Exception:
            pass
        try:
            warmth_unregister_callbacks()
        except Exception:
            pass

        try:
            NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self)
        except Exception:
            pass

        try:
            NSStatusBar.systemStatusBar().removeStatusItem_(self.statusItem)
        except Exception:
            pass

        NSApp.terminate_(self)

    #reapply after wake
    def _install_notifications(self):
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        center.addObserver_selector_name_object_(
            self, "reapplyNotif:", "NSWorkspaceDidWakeNotification", None
        )

    def reapplyNotif_(self, _):
        self._apply_current()


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
