from __future__ import annotations

from AppKit import (  # type: ignore
    NSApplication, NSApp, NSStatusBar, NSVariableStatusItemLength,
    NSMenu, NSMenuItem, NSWorkspace, NSView, NSSlider, NSTextField,
    NSApplicationActivationPolicyAccessory,
)
from Foundation import NSObject  # type: ignore

from smartdim.lut import (  # type: ignore
    set_intensity, disable,
    register_display_callbacks, reapply_if_enabled, 
    unregister_display_callbacks,
)

ICON_EMOJI = "🌙"

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, _):
        # App state
        self.isMuted = False
        self.lastSliderValue = 0.0

        # Status item
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.statusItem.setTitle_(ICON_EMOJI)

        # Menu
        menu = NSMenu.alloc().init()

        label_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Strength", None, ""
        )
        label_item.setEnabled_(False)
        menu.addItem_(label_item)

        self.slider_item = self._slider_item(selector="lutSliderChanged:", initial=self.lastSliderValue)
        menu.addItem_(self.slider_item)

        menu.addItem_(NSMenuItem.separatorItem())

        self.toggle_item = self._make_item("Toggle Off", "toggleAction:")
        menu.addItem_(self.toggle_item)

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

    def _slider_item(self, selector: str, initial: float = 0.0) -> NSMenuItem:
        container = NSView.alloc().initWithFrame_(((0, 0), (240, 44)))

        slider = NSSlider.alloc().initWithFrame_(((8, 8), (180, 20)))
        slider.setMinValue_(0.0)
        slider.setMaxValue_(1.0)
        slider.setFloatValue_(float(initial))
        slider.setContinuous_(True)
        slider.setTarget_(self)
        slider.setAction_(selector)
        container.addSubview_(slider)
        self.slider = slider

        value_label = NSTextField.alloc().initWithFrame_(((192, 8), (40, 20)))
        value_label.setEditable_(False)
        value_label.setBordered_(False)
        value_label.setDrawsBackground_(False)
        value_label.setAlignment_(1)  # right
        value_label.setStringValue_(f"{int(round(initial*100))}%")
        container.addSubview_(value_label)
        self.value_label = value_label

        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        mi.setView_(container)
        return mi

    def _update_toggle_title(self):
        self.toggle_item.setTitle_("Toggle On" if self.isMuted else "Toggle Off")

    # ----- Actions -----
    def lutSliderChanged_(self, sender):
        val = float(sender.floatValue())  # 0..1
        self.lastSliderValue = val
        self.value_label.setStringValue_(f"{int(round(val * 100))}%")

        if self.isMuted:
            return
        if val <= 0.001:
            disable()            # restore colors, but remain "On"
        else:
            set_intensity(val)   # apply mapping in lut.py

    def toggleAction_(self, _):
        self.isMuted = not self.isMuted
        self._update_toggle_title()

        if self.isMuted:
            disable()  # restore colors, keep slider value
        else:
            val = float(self.slider.floatValue())
            if val <= 0.001:
                disable()
            else:
                set_intensity(val)

    def quitAction_(self, _):
        # 1) Restore colors
        disable()
        # 2) Unregister display callbacks
        try:
            unregister_display_callbacks()
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

    # Reapply after wake (only if not muted and slider > 0)
    def _install_notifications(self):
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        center.addObserver_selector_name_object_(
            self, "reapplyNotif:", "NSWorkspaceDidWakeNotification", None
        )

    def reapplyNotif_(self, _):
        if self.isMuted:
            return
        if float(self.slider.floatValue()) > 0.001:
            set_intensity(float(self.slider.floatValue()))
        else:
            disable()

def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()

if __name__ == "__main__":
    main()
