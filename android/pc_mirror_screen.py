"""
CelSuite PC Mirror Screen (PC -> Phone Reverse Mirroring Client).
Provides ultra-low-latency display surface, multi-touch / trackpad input injection,
floating draggable HUD, on-screen shortcut Quick-Bar with swipe-up reveal gesture,
audio receiver, and LDPlayer 9 / Nox Player-grade customizable On-Screen Gamepad Overlay!
"""

from __future__ import annotations

import json
import math
import os
import socket
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# Theme Palette (CelStudio Emerald Glass)
DARK_BG = (0.04, 0.08, 0.06, 1)
ACCENT_PRIMARY = (0.063, 0.725, 0.506, 1)    # Emerald Green
ACCENT_SECONDARY = (0.00, 0.89, 0.80, 1)  # Cyan Glow
CARD_BG = (0.06, 0.12, 0.09, 0.85)
BUTTON_BG = (0.10, 0.18, 0.14, 0.90)
TEXT_PRIMARY = (0.95, 0.98, 0.96, 1)
TEXT_SECONDARY = (0.65, 0.75, 0.70, 1)
WARNING_COLOR = (0.95, 0.65, 0.20, 1)
DANGER_COLOR = (0.95, 0.30, 0.30, 1)

PORT_REVERSE_VIDEO = 5560
PORT_REVERSE_AUDIO = 5561
PORT_REVERSE_INPUT = 5562

def _get_gamepad_config_path() -> str:
    try:
        import main as mobile_main
        base_dir = os.path.dirname(mobile_main.CONFIG_FILE)
        return os.path.join(base_dir, "gamepad_layout.json")
    except Exception:
        return os.path.join(os.path.expanduser("~"), "scrcpy_link", "gamepad_layout.json")

GAMEPAD_CONFIG_FILE = _get_gamepad_config_path()


# ── Nox / LDPlayer 9 On-Screen Virtual Controls Overlay ────────────────────────

class VirtualJoystick(Widget):
    """
    Analog WASD / Arrow / Camera Joystick inspired by LDPlayer 9 / Nox Player on-screen keybinds.
    Supports spring-loaded thumbstick knob, 8-way WASD or Arrow generation, Camera Look,
    and drag-to-reposition in Edit Mode.
    """

    def __init__(
        self,
        screen_owner: "PCMirrorScreen",
        stick_id: str = "stick_0",
        stick_type: str = "wasd",
        radius=dp(56),
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.screen_owner = screen_owner
        self.stick_id = stick_id
        self.stick_type = stick_type  # 'wasd', 'arrows', or 'camera'
        self.base_radius = radius
        self.knob_radius = dp(22)
        self.hud_opacity = 0.55
        self.active_keys: Set[str] = set()
        self.current_touch = None
        self.knob_offset = [0, 0]
        self.is_dragging_in_edit = False

        self.size_hint = (None, None)
        self.size = (self.base_radius * 2 + dp(20), self.base_radius * 2 + dp(20))

        self.bind(pos=self._redraw, size=self._redraw)
        Clock.schedule_once(lambda dt: self._redraw(), 0)

    def set_opacity_val(self, val: float):
        self.hud_opacity = val
        self._redraw()

    @property
    def center_pt(self) -> Tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def _redraw(self, *args):
        self.canvas.clear()
        cx, cy = self.center_pt
        kx = cx + self.knob_offset[0]
        ky = cy + self.knob_offset[1]
        is_edit = getattr(self.screen_owner.gamepad_overlay, 'edit_mode', False)

        with self.canvas:
            # 1. Dark Glass Base Circle
            Color(0.02, 0.08, 0.05, (0.70 if is_edit else 0.42) * self.hud_opacity)
            Ellipse(pos=(cx - self.base_radius, cy - self.base_radius), size=(self.base_radius * 2, self.base_radius * 2))

            # 2. Glowing Emerald Outer Ring
            ring_color = ACCENT_SECONDARY if is_edit else ACCENT_PRIMARY
            Color(*ring_color[:3], 0.90 * self.hud_opacity)
            Line(circle=(cx, cy, self.base_radius), width=2.0 if is_edit else 1.6)

            # 3. Directional Axis Markings
            Color(0.20, 0.83, 0.60, 0.35 * self.hud_opacity)
            Line(points=[cx - self.base_radius * 0.85, cy, cx + self.base_radius * 0.85, cy], width=1.0)
            Line(points=[cx, cy - self.base_radius * 0.85, cx, cy + self.base_radius * 0.85], width=1.0)

            # 4. Spring-loaded Draggable Inner Knob
            Color(0.05, 0.14, 0.09, 0.85 * self.hud_opacity)
            Ellipse(pos=(kx - self.knob_radius, ky - self.knob_radius), size=(self.knob_radius * 2, self.knob_radius * 2))
            knob_glow = ACCENT_SECONDARY if (self.current_touch or is_edit) else ACCENT_PRIMARY
            Color(*knob_glow[:3], 0.95 * self.hud_opacity)
            Line(circle=(kx, ky, self.knob_radius), width=2.2)

            if is_edit:
                Color(1, 1, 1, 0.8)
                Line(rectangle=(self.x, self.y, self.width, self.height), width=1.0)

    def on_touch_down(self, touch):
        # 1. Eliminate Ghost Touch Eating: If gamepad or parent is not visible, don't grab touch
        if not getattr(self.screen_owner, 'gamepad_visible', False):
            return False
        if self.parent and (getattr(self.parent, 'disabled', False) or getattr(self.parent, 'opacity', 1.0) <= 0):
            return False
        if self.current_touch is not None:
            return False

        cx, cy = self.center_pt
        dist = math.hypot(touch.x - cx, touch.y - cy)
        if dist <= self.base_radius * 1.35:
            touch.grab(self)
            self.current_touch = touch
            is_edit = getattr(self.screen_owner.gamepad_overlay, 'edit_mode', False)
            if is_edit:
                self.is_dragging_in_edit = True
                touch.ud['drag_offset'] = (self.x - touch.x, self.y - touch.y)
                self.screen_owner.gamepad_overlay.select_joystick_for_edit(self)
            else:
                self._process_joystick_movement(touch.x, touch.y)
                if self.stick_type == "camera":
                    self._start_camera_loop()
            return True
        return False

    def on_touch_move(self, touch):
        if touch.grab_current is self and touch == self.current_touch:
            if self.is_dragging_in_edit:
                off_x, off_y = touch.ud.get('drag_offset', (0, 0))
                self.x = max(0, min(Window.width - self.width, touch.x + off_x))
                self.y = max(0, min(Window.height - self.height, touch.y + off_y))
                self._redraw()
            else:
                self._process_joystick_movement(touch.x, touch.y)
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is self and touch == self.current_touch:
            touch.ungrab(self)
            self.current_touch = None
            self.is_dragging_in_edit = False
            self.knob_offset = [0, 0]
            self._stop_camera_loop()
            self._release_all_keys()
            self._redraw()
            return True
        return False

    def _start_camera_loop(self):
        self._stop_camera_loop()
        self._camera_event = Clock.schedule_interval(self._camera_tick, 1.0 / 60.0)

    def _stop_camera_loop(self):
        if hasattr(self, '_camera_event') and self._camera_event:
            self._camera_event.cancel()
            self._camera_event = None

    def _camera_tick(self, dt):
        if self.stick_type != "camera" or self.current_touch is None:
            return
        dx, dy = self.knob_offset
        dist = math.hypot(dx, dy)
        deadzone = dp(10)
        if dist < deadzone:
            return

        # Smooth non-linear dampening curve for gaming precision
        norm_dist = min(1.0, (dist - deadzone) / max(1.0, self.base_radius - deadzone))
        speed = math.pow(norm_dist, 1.35) * 22.0
        angle = math.atan2(dy, dx)
        step_x = int(math.cos(angle) * speed)
        step_y = int(-math.sin(angle) * speed)
        if step_x != 0 or step_y != 0:
            self.screen_owner.send_input_cmd(f"MOUSE|MOVE_REL|{step_x}|{step_y}")

    def _process_joystick_movement(self, tx: float, ty: float):
        cx, cy = self.center_pt
        dx = tx - cx
        dy = ty - cy
        dist = math.hypot(dx, dy)

        max_dist = self.base_radius
        if dist > max_dist and dist > 0:
            scale = max_dist / dist
            dx *= scale
            dy *= scale
            dist = max_dist

        self.knob_offset = [dx, dy]
        self._redraw()

        if self.stick_type == "camera":
            return

        deadzone = dp(14)
        new_keys: Set[str] = set()

        up_k = "up" if self.stick_type == "arrows" else "w"
        down_k = "down" if self.stick_type == "arrows" else "s"
        left_k = "left" if self.stick_type == "arrows" else "a"
        right_k = "right" if self.stick_type == "arrows" else "d"

        if dist >= deadzone:
            angle = math.degrees(math.atan2(dy, dx)) % 360
            if 22.5 <= angle < 67.5:
                new_keys.update([up_k, right_k])
            elif 67.5 <= angle < 112.5:
                new_keys.add(up_k)
            elif 112.5 <= angle < 157.5:
                new_keys.update([up_k, left_k])
            elif 157.5 <= angle < 202.5:
                new_keys.add(left_k)
            elif 202.5 <= angle < 247.5:
                new_keys.update([down_k, left_k])
            elif 247.5 <= angle < 292.5:
                new_keys.add(down_k)
            elif 292.5 <= angle < 337.5:
                new_keys.update([down_k, right_k])
            else:
                new_keys.add(right_k)

        to_press = new_keys - self.active_keys
        to_release = self.active_keys - new_keys

        for k in to_press:
            self.screen_owner.send_input_cmd(f"KEY|DOWN|{k}")
        for k in to_release:
            self.screen_owner.send_input_cmd(f"KEY|UP|{k}")

        self.active_keys = new_keys

    def _release_all_keys(self):
        for k in self.active_keys:
            self.screen_owner.send_input_cmd(f"KEY|UP|{k}")
        self.active_keys.clear()


class VirtualKeyButton(Widget):
    """
    Circular On-Screen Action Button (Nox Player / LDPlayer style).
    Supports drag-to-reposition and configuration bar editing in Edit Mode.
    """

    def __init__(
        self,
        screen_owner: "PCMirrorScreen",
        btn_id: str,
        key_name: str,
        label_text: str,
        is_mouse: bool = False,
        radius=dp(26),
        border_color: Tuple[float, float, float, float] = ACCENT_PRIMARY,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.screen_owner = screen_owner
        self.btn_id = btn_id
        self.key_name = key_name
        self.label_text = label_text
        self.is_mouse = is_mouse
        self.radius = radius
        self.border_color = border_color
        self.hud_opacity = 0.55
        self.is_pressed = False
        self.current_touch = None
        self.is_dragging_in_edit = False

        self.size_hint = (None, None)
        self.size = (self.radius * 2 + dp(8), self.radius * 2 + dp(8))

        self.lbl = Label(
            text=label_text,
            font_size=sp(11 if len(label_text) <= 4 else 9),
            bold=True,
            color=(1, 1, 1, 0.95),
            size_hint=(None, None),
            size=self.size,
        )
        self.add_widget(self.lbl)

        self.bind(pos=self._redraw, size=self._redraw)
        Clock.schedule_once(lambda dt: self._redraw(), 0)

    def set_opacity_val(self, val: float):
        self.hud_opacity = val
        self.lbl.color = (1, 1, 1, min(1.0, val + 0.3))
        self._redraw()

    def update_definition(self, key_name: str, label_text: str, radius: float):
        self.key_name = key_name
        self.label_text = label_text
        self.radius = radius
        self.size = (self.radius * 2 + dp(8), self.radius * 2 + dp(8))
        self.lbl.text = label_text
        self.lbl.font_size = sp(11 if len(label_text) <= 4 else 9)
        self.lbl.size = self.size
        self._redraw()

    @property
    def center_pt(self) -> Tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def _redraw(self, *args):
        self.lbl.pos = self.pos
        self.lbl.size = self.size
        cx, cy = self.center_pt
        r = self.radius * (0.92 if self.is_pressed else 1.0)
        is_edit = getattr(self.screen_owner.gamepad_overlay, 'edit_mode', False)

        self.canvas.before.clear()
        with self.canvas.before:
            bg_alpha = (0.75 if self.is_pressed else 0.40) * self.hud_opacity
            Color(0.05, 0.13, 0.09, bg_alpha)
            Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2))

            glow = ACCENT_SECONDARY if (self.is_pressed or is_edit) else self.border_color
            border_w = 2.4 if (self.is_pressed or is_edit) else 1.5
            Color(*glow[:3], min(1.0, (glow[3] if len(glow) > 3 else 1.0) * self.hud_opacity * (1.3 if self.is_pressed else 1.0)))
            Line(circle=(cx, cy, r), width=border_w)

            if is_edit:
                Color(1, 1, 1, 0.7)
                Line(rectangle=(self.x, self.y, self.width, self.height), width=1.0)

    def on_touch_down(self, touch):
        # Eliminate Ghost Touch Eating: If gamepad or parent is disabled/invisible, ignore touch
        if not getattr(self.screen_owner, 'gamepad_visible', False):
            return False
        if self.parent and (getattr(self.parent, 'disabled', False) or getattr(self.parent, 'opacity', 1.0) <= 0):
            return False
        if self.current_touch is not None:
            return False

        cx, cy = self.center_pt
        dist = math.hypot(touch.x - cx, touch.y - cy)
        if dist <= self.radius * 1.25:
            touch.grab(self)
            self.current_touch = touch
            is_edit = getattr(self.screen_owner.gamepad_overlay, 'edit_mode', False)
            if is_edit:
                self.is_dragging_in_edit = True
                touch.ud['drag_offset'] = (self.x - touch.x, self.y - touch.y)
                self.screen_owner.gamepad_overlay.select_button_for_edit(self)
            else:
                self.is_pressed = True
                self._redraw()
                self._emit_down()
            return True
        return False

    def on_touch_move(self, touch):
        if touch.grab_current is self and touch == self.current_touch:
            if self.is_dragging_in_edit:
                off_x, off_y = touch.ud.get('drag_offset', (0, 0))
                self.x = max(0, min(Window.width - self.width, touch.x + off_x))
                self.y = max(0, min(Window.height - self.height, touch.y + off_y))
                self._redraw()
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is self and touch == self.current_touch:
            touch.ungrab(self)
            self.current_touch = None
            if not self.is_dragging_in_edit:
                self.is_pressed = False
                self._redraw()
                self._emit_up()
            self.is_dragging_in_edit = False
            return True
        return False

    def _emit_down(self):
        if self.is_mouse:
            btn = "1" if self.key_name == "lclick" else "3"
            self.screen_owner.send_input_cmd(f"MOUSE|DOWN|{btn}|0")
        else:
            self.screen_owner.send_input_cmd(f"KEY|DOWN|{self.key_name}")

    def _emit_up(self):
        if self.is_mouse:
            btn = "1" if self.key_name == "lclick" else "3"
            self.screen_owner.send_input_cmd(f"MOUSE|UP|{btn}|0")
        else:
            self.screen_owner.send_input_cmd(f"KEY|UP|{self.key_name}")


class VirtualGamepadOverlay(FloatLayout):
    """
    On-Screen Keybinds & Gamepad HUD Manager with LDPlayer 9 Edit Mode.
    Allows multiple WASD/Arrow/Camera joysticks, custom action buttons, resizing,
    and persisting custom layouts to JSON without crashes.
    """

    def __init__(self, screen_owner: "PCMirrorScreen", **kwargs):
        super().__init__(**kwargs)
        self.screen_owner = screen_owner
        self.current_preset = "fps"
        self.hud_opacity = 0.55
        self.edit_mode = False
        self.selected_button: Optional[VirtualKeyButton] = None
        self.selected_joystick: Optional[VirtualJoystick] = None
        self.joysticks: List[VirtualJoystick] = []
        self.action_buttons: List[VirtualKeyButton] = []
        self._btn_counter = 100
        self._stick_counter = 0

        # Edit Bar at Top of screen (visible during Edit Mode)
        self.edit_bar = BoxLayout(
            orientation='horizontal', size_hint=(0.96, None), height=dp(44),
            pos_hint={'center_x': 0.5, 'top': 0.98}, spacing=dp(6), padding=dp(4)
        )
        with self.edit_bar.canvas.before:
            Color(0.04, 0.12, 0.08, 0.95)
            self.eb_rect = RoundedRectangle(pos=self.edit_bar.pos, size=self.edit_bar.size, radius=[dp(10)])
            Color(*ACCENT_SECONDARY)
            self.eb_border = Line(rounded_rectangle=[self.edit_bar.x, self.edit_bar.y, self.edit_bar.width, self.edit_bar.height, dp(10)], width=1.2)
        self.edit_bar.bind(pos=self._update_edit_bar, size=self._update_edit_bar)
        self._build_edit_bar()
        self.edit_bar.opacity = 0
        self.edit_bar.disabled = True
        self.add_widget(self.edit_bar)

        self.bind(pos=self._reposition_widgets, size=self._reposition_widgets)
        Clock.schedule_once(lambda dt: self.load_or_build_layout(), 0)

    def _update_edit_bar(self, *args):
        self.eb_rect.pos = self.edit_bar.pos
        self.eb_rect.size = self.edit_bar.size
        self.eb_border.rounded_rectangle = [self.edit_bar.x, self.edit_bar.y, self.edit_bar.width, self.edit_bar.height, dp(10)]

    def _build_edit_bar(self):
        lbl = Label(text="EDIT MODE", font_size=sp(11), bold=True, color=ACCENT_SECONDARY, size_hint_x=0.20)
        
        add_stick_btn = Button(text="+ Stick", font_size=sp(10), bold=True, background_color=(0.10, 0.32, 0.22, 1), size_hint_x=0.15)
        add_stick_btn.bind(on_press=self.add_custom_joystick)

        add_key_btn = Button(text="+ Key", font_size=sp(10), bold=True, background_color=(0.12, 0.28, 0.20, 1), size_hint_x=0.13)
        add_key_btn.bind(on_press=self.add_custom_button)

        self.size_dec_btn = Button(text="- Size", font_size=sp(10), bold=True, background_color=(0.14, 0.22, 0.18, 1), size_hint_x=0.13, disabled=True)
        self.size_dec_btn.bind(on_press=lambda inst: self.adjust_selected_size(-dp(4)))

        self.size_inc_btn = Button(text="+ Size", font_size=sp(10), bold=True, background_color=(0.14, 0.22, 0.18, 1), size_hint_x=0.13, disabled=True)
        self.size_inc_btn.bind(on_press=lambda inst: self.adjust_selected_size(dp(4)))

        self.del_btn = Button(text="Del", font_size=sp(11), bold=True, background_color=(0.45, 0.15, 0.15, 1), size_hint_x=0.12, disabled=True)
        self.del_btn.bind(on_press=self.delete_selected_item)

        save_btn = Button(text="Save", font_size=sp(11), bold=True, background_color=(0.10, 0.50, 0.35, 1), size_hint_x=0.14)
        save_btn.bind(on_press=self.toggle_edit_mode)

        self.edit_bar.add_widget(lbl)
        self.edit_bar.add_widget(add_stick_btn)
        self.edit_bar.add_widget(add_key_btn)
        self.edit_bar.add_widget(self.size_dec_btn)
        self.edit_bar.add_widget(self.size_inc_btn)
        self.edit_bar.add_widget(self.del_btn)
        self.edit_bar.add_widget(save_btn)

    def adjust_selected_size(self, delta: float):
        if self.selected_button:
            new_r = max(dp(18), min(dp(50), self.selected_button.radius + delta))
            self.selected_button.radius = new_r
            self.selected_button.size = (new_r * 2 + dp(8), new_r * 2 + dp(8))
            self.selected_button.lbl.size = self.selected_button.size
            self.selected_button._redraw()
        elif self.selected_joystick:
            new_r = max(dp(35), min(dp(90), self.selected_joystick.base_radius + delta))
            self.selected_joystick.base_radius = new_r
            self.selected_joystick.size = (new_r * 2 + dp(20), new_r * 2 + dp(20))
            self.selected_joystick._redraw()

    def select_button_for_edit(self, btn: VirtualKeyButton):
        self.selected_button = btn
        self.selected_joystick = None
        self.del_btn.disabled = False
        self.size_dec_btn.disabled = False
        self.size_inc_btn.disabled = False
        for b in self.action_buttons:
            b._redraw()
        for j in self.joysticks:
            j._redraw()

    def select_joystick_for_edit(self, stick: VirtualJoystick):
        self.selected_joystick = stick
        self.selected_button = None
        self.del_btn.disabled = False
        self.size_dec_btn.disabled = False
        self.size_inc_btn.disabled = False
        for b in self.action_buttons:
            b._redraw()
        for j in self.joysticks:
            j._redraw()

    def toggle_edit_mode(self, instance=None):
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.edit_bar.opacity = 1
            self.edit_bar.disabled = False
        else:
            self.edit_bar.opacity = 0
            self.edit_bar.disabled = True
            self.selected_button = None
            self.selected_joystick = None
            self.del_btn.disabled = True
            self.size_dec_btn.disabled = True
            self.size_inc_btn.disabled = True
            self.save_layout()

        for j in self.joysticks:
            j._redraw()
        for btn in self.action_buttons:
            btn._redraw()

    def add_custom_joystick(self, instance=None):
        self._stick_counter += 1
        stick_type = "camera" if len(self.joysticks) == 1 else "arrows" if len(self.joysticks) > 1 else "wasd"
        stick = VirtualJoystick(
            screen_owner=self.screen_owner,
            stick_id=f"stick_{self._stick_counter}",
            stick_type=stick_type,
            radius=dp(54),
        )
        stick.pos = (Window.width / 2 - dp(54), Window.height / 2 - dp(54))
        stick.set_opacity_val(self.hud_opacity)
        self.joysticks.append(stick)
        self.add_widget(stick)
        self.select_joystick_for_edit(stick)

    def add_custom_button(self, instance=None):
        self._btn_counter += 1
        btn = VirtualKeyButton(
            screen_owner=self.screen_owner,
            btn_id=f"custom_{self._btn_counter}",
            key_name="e",
            label_text="ACT",
            radius=dp(28),
            border_color=ACCENT_SECONDARY,
        )
        btn.pos = (Window.width / 2 - dp(28), Window.height / 2 - dp(28))
        btn.set_opacity_val(self.hud_opacity)
        self.action_buttons.append(btn)
        self.add_widget(btn)
        self.select_button_for_edit(btn)

    def delete_selected_item(self, instance=None):
        if self.selected_button and self.selected_button in self.action_buttons:
            self.remove_widget(self.selected_button)
            self.action_buttons.remove(self.selected_button)
            self.selected_button = None
            self.del_btn.disabled = True
            self.size_dec_btn.disabled = True
            self.size_inc_btn.disabled = True
        elif self.selected_joystick and self.selected_joystick in self.joysticks:
            self.remove_widget(self.selected_joystick)
            self.joysticks.remove(self.selected_joystick)
            self.selected_joystick = None
            self.del_btn.disabled = True
            self.size_dec_btn.disabled = True
            self.size_inc_btn.disabled = True

    def set_hud_opacity(self, opacity: float):
        self.hud_opacity = opacity
        for j in self.joysticks:
            j.set_opacity_val(opacity)
        for btn in self.action_buttons:
            btn.set_opacity_val(opacity)

    def cycle_opacity(self) -> float:
        levels = [0.20, 0.40, 0.60, 0.80, 1.00]
        try:
            curr_idx = min(range(len(levels)), key=lambda i: abs(levels[i] - self.hud_opacity))
            next_idx = (curr_idx + 1) % len(levels)
        except Exception:
            next_idx = 2
        new_val = levels[next_idx]
        self.set_hud_opacity(new_val)
        return new_val

    def is_gamepad_touch(self, touch) -> bool:
        if not self.opacity:
            return False
        if self.edit_mode and self.edit_bar.collide_point(*touch.pos):
            return True
        for j in self.joysticks:
            if j.collide_point(*touch.pos):
                return True
        for btn in self.action_buttons:
            if btn.collide_point(*touch.pos):
                return True
        return False

    def clear_controls(self):
        for btn in self.action_buttons:
            self.remove_widget(btn)
        for j in self.joysticks:
            self.remove_widget(j)
        self.joysticks.clear()
        self.action_buttons.clear()

    def save_layout(self):
        try:
            os.makedirs(os.path.dirname(GAMEPAD_CONFIG_FILE), exist_ok=True)
            w, h = max(1.0, float(Window.width)), max(1.0, float(Window.height))
            data = {
                "joysticks": [],
                "buttons": []
            }
            for j in self.joysticks:
                data["joysticks"].append({
                    "id": j.stick_id,
                    "type": j.stick_type,
                    "radius": j.base_radius / dp(1),
                    "rel_x": j.x / w,
                    "rel_y": j.y / h,
                })
            for btn in self.action_buttons:
                data["buttons"].append({
                    "id": btn.btn_id,
                    "key": btn.key_name,
                    "label": btn.label_text,
                    "is_mouse": btn.is_mouse,
                    "radius": btn.radius / dp(1),
                    "rel_x": btn.x / w,
                    "rel_y": btn.y / h,
                })
            with open(GAMEPAD_CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def load_or_build_layout(self):
        if os.path.exists(GAMEPAD_CONFIG_FILE):
            try:
                with open(GAMEPAD_CONFIG_FILE, "r") as f:
                    data = json.load(f)
                self.clear_controls()

                # 1. Load Joysticks (multiple or legacy single)
                raw_sticks = data.get("joysticks", [])
                if not raw_sticks and "joystick" in data:
                    raw_sticks = [{
                        "id": "stick_0",
                        "type": "wasd",
                        "radius": 56,
                        "rel_x": data["joystick"].get("rel_x", 0.05),
                        "rel_y": data["joystick"].get("rel_y", 0.05),
                    }]

                for s in raw_sticks:
                    st = VirtualJoystick(
                        screen_owner=self.screen_owner,
                        stick_id=s.get("id", f"stick_{len(self.joysticks)}"),
                        stick_type=s.get("type", "wasd"),
                        radius=dp(s.get("radius", 56)),
                    )
                    st.set_opacity_val(self.hud_opacity)
                    self.joysticks.append(st)
                    self.add_widget(st)

                # 2. Load Buttons
                for b in data.get("buttons", []):
                    btn = VirtualKeyButton(
                        screen_owner=self.screen_owner,
                        btn_id=b.get("id", f"btn_{len(self.action_buttons)}"),
                        key_name=b.get("key", "space"),
                        label_text=b.get("label", "KEY"),
                        is_mouse=b.get("is_mouse", False),
                        radius=dp(b.get("radius", 26)),
                        border_color=ACCENT_SECONDARY if b.get("is_mouse") else ACCENT_PRIMARY,
                    )
                    btn.set_opacity_val(self.hud_opacity)
                    self.action_buttons.append(btn)
                    self.add_widget(btn)

                self._apply_relative_positions(data)
                return
            except Exception:
                pass

        self.build_preset(self.current_preset)

    def _apply_relative_positions(self, data: dict):
        w, h = Window.width, Window.height
        if not w or not h:
            return

        raw_sticks = data.get("joysticks", [])
        if not raw_sticks and "joystick" in data:
            raw_sticks = [data["joystick"]]

        for i, j in enumerate(self.joysticks):
            if i < len(raw_sticks):
                jx = raw_sticks[i].get("rel_x", 0.05) * w
                jy = raw_sticks[i].get("rel_y", 0.05) * h
                j.pos = (jx, jy)

        btns_data = data.get("buttons", [])
        for i, btn in enumerate(self.action_buttons):
            if i < len(btns_data):
                bx = btns_data[i].get("rel_x", 0.8) * w
                by = btns_data[i].get("rel_y", 0.2) * h
                btn.pos = (bx, by)

    def build_preset(self, preset_name: str):
        self.clear_controls()
        self.current_preset = preset_name

        primary_stick = VirtualJoystick(screen_owner=self.screen_owner, stick_id="stick_0", stick_type="wasd", radius=dp(56))
        primary_stick.set_opacity_val(self.hud_opacity)
        self.joysticks.append(primary_stick)
        self.add_widget(primary_stick)

        if preset_name == "fps":
            buttons_def = [
                ("lclick", "ATK", True, dp(32), ACCENT_SECONDARY),
                ("rclick", "AIM", True, dp(26), ACCENT_PRIMARY),
                ("space", "JUMP", False, dp(28), ACCENT_PRIMARY),
                ("shift", "SPRINT", False, dp(25), (0.3, 0.7, 0.9, 1)),
                ("e", "INV", False, dp(23), ACCENT_PRIMARY),
                ("q", "DROP", False, dp(22), (0.9, 0.4, 0.4, 1)),
                ("f", "USE", False, dp(23), ACCENT_PRIMARY),
                ("r", "RELOAD", False, dp(23), WARNING_COLOR),
            ]
        elif preset_name == "moba":
            buttons_def = [
                ("space", "ATK", False, dp(34), ACCENT_SECONDARY),
                ("e", "SKILL 1", False, dp(27), ACCENT_PRIMARY),
                ("q", "SKILL 2", False, dp(27), (0.2, 0.8, 0.9, 1)),
                ("r", "SUPER", False, dp(32), (0.98, 0.75, 0.15, 1)),
                ("f", "GADGET", False, dp(24), (0.8, 0.4, 0.9, 1)),
            ]
        else:
            buttons_def = [
                ("space", "A", False, dp(28), ACCENT_SECONDARY),
                ("shift", "B", False, dp(28), ACCENT_PRIMARY),
                ("e", "X", False, dp(26), WARNING_COLOR),
                ("q", "Y", False, dp(26), (0.2, 0.8, 0.9, 1)),
            ]

        for i, (key, label, is_mouse, radius, b_color) in enumerate(buttons_def):
            btn = VirtualKeyButton(
                screen_owner=self.screen_owner,
                btn_id=f"preset_{i}",
                key_name=key,
                label_text=label,
                is_mouse=is_mouse,
                radius=radius,
                border_color=b_color,
            )
            btn.set_opacity_val(self.hud_opacity)
            self.action_buttons.append(btn)
            self.add_widget(btn)

        self._reposition_widgets()

    @property
    def joystick(self) -> Optional[VirtualJoystick]:
        return self.joysticks[0] if self.joysticks else None

    def _reposition_widgets(self, *args):
        if not self.width or not self.height:
            return

        w, h = self.width, self.height

        # If custom layout exists, apply relative coordinates across resize/rotation
        if hasattr(self, 'saved_layout_data') and self.saved_layout_data:
            self._apply_relative_positions(self.saved_layout_data)
            return

        if self.joysticks:
            self.joysticks[0].pos = (dp(24), dp(24))

        if self.current_preset == "fps" and len(self.action_buttons) >= 8:
            atk, aim, jump, sprint, inv, drop, use, reload_btn = self.action_buttons[:8]
            atk.pos = (w - dp(95), dp(35))
            aim.pos = (w - dp(75), dp(115))
            jump.pos = (w - dp(165), dp(40))
            reload_btn.pos = (w - dp(145), dp(115))
            use.pos = (w - dp(115), dp(180))
            inv.pos = (w - dp(180), dp(175))
            sprint.pos = (dp(30), dp(150))
            drop.pos = (dp(150), dp(35))

        elif self.current_preset == "moba" and len(self.action_buttons) >= 5:
            atk, s1, s2, sup, gad = self.action_buttons[:5]
            atk.pos = (w - dp(105), dp(45))
            sup.pos = (w - dp(80), dp(135))
            s1.pos = (w - dp(170), dp(65))
            s2.pos = (w - dp(150), dp(145))
            gad.pos = (w - dp(120), dp(215))


# ── Main PC Mirror Screen ──────────────────────────────────────────────────────

class PCMirrorSurface(Widget):
    """
    Interactive touch surface that maps finger taps & gestures to PC coordinates.
    Also detects upward swipe gestures to smoothly reveal the bottom Quick-Bar!
    """

    def __init__(self, screen_owner: "PCMirrorScreen", **kwargs):
        super().__init__(**kwargs)
        self.screen_owner = screen_owner
        self.mode = "touchscreen"
        self.active_fingers = {}

        # Look for CelWeave wallpaper
        self._find_wallpapers()

        with self.canvas.before:
            Color(0.01, 0.03, 0.02, 1)
            self.base_rect = Rectangle(pos=(0, 0), size=Window.size)

            curr_wp = self._get_best_wallpaper()
            if curr_wp:
                Color(1, 1, 1, 1)
                self.wp_rect = Rectangle(source=curr_wp, pos=(0, 0), size=Window.size)
            else:
                self.wp_rect = None

            tint_val = self._get_tint_opacity()
            self.tint_color_inst = Color(0.01, 0.04, 0.02, tint_val)
            self.tint_rect = Rectangle(pos=(0, 0), size=Window.size)

            # Deep dark contrast pass
            Color(0.01, 0.02, 0.01, 0.35)
            self.shadow_rect = Rectangle(pos=(0, 0), size=Window.size)

            # Reset OpenGL drawing color to pure white so text and controls render bright and crisp
            Color(1, 1, 1, 1)

        self.bind(pos=self._update_rect, size=self._update_rect)
        Window.bind(size=self._update_rect)
        Clock.schedule_once(lambda dt: self._update_rect(), 0)

    def _find_wallpapers(self):
        here = os.path.dirname(os.path.abspath(__file__))
        cands_land = ['wallpaper.jpg', os.path.join(here, 'wallpaper.jpg')]
        cands_port = ['wallpaper_mobile.jpg', os.path.join(here, 'wallpaper_mobile.jpg')]
        self.wp_land = next((p for p in cands_land if os.path.exists(p)), None)
        self.wp_port = next((p for p in cands_port if os.path.exists(p)), None)

    def _get_best_wallpaper(self) -> Optional[str]:
        w, h = Window.width, Window.height
        if w > h and self.wp_land:
            return self.wp_land
        if self.wp_port:
            return self.wp_port
        return self.wp_land

    def _get_tint_opacity(self) -> float:
        try:
            import main as mobile_main
            return float(mobile_main.config.get("wallpaper_tint_opacity", 0.72))
        except Exception:
            return 0.72

    def _update_rect(self, *args):
        w = max(Window.width, self.width)
        h = max(Window.height, self.height)
        self.base_rect.pos = (0, 0)
        self.base_rect.size = (w, h)
        if self.wp_rect and h > 0 and w > 0:
            best_wp = self._get_best_wallpaper()
            if best_wp and self.wp_rect.source != best_wp:
                self.wp_rect.source = best_wp

            is_portrait = h > w
            img_ratio = (9.0 / 19.5) if (is_portrait and self.wp_port) else (16.0 / 9.0)
            win_ratio = w / float(h)
            if win_ratio > img_ratio:
                target_w = w
                target_h = w / img_ratio
            else:
                target_h = h
                target_w = h * img_ratio
            self.wp_rect.pos = ((w - target_w) / 2.0, (h - target_h) / 2.0)
            self.wp_rect.size = (target_w, target_h)
        self.tint_rect.pos = (0, 0)
        self.tint_rect.size = (w, h)
        if hasattr(self, 'shadow_rect'):
            self.shadow_rect.pos = (0, 0)
            self.shadow_rect.size = (w, h)

    def on_touch_down(self, touch):
        if self.screen_owner.is_hud_touch(touch):
            return False

        if not self.collide_point(*touch.pos):
            return False

        touch.grab(self)
        self.active_fingers[touch.id] = touch
        touch.ud['start_y'] = touch.y
        touch.ud['start_time'] = time.time()

        pc_ip = self.screen_owner.get_pc_ip()
        if not pc_ip:
            return True

        if self.mode == "touchscreen":
            norm_x = max(0.0, min(1.0, touch.x / max(1, self.width)))
            norm_y = max(0.0, min(1.0, 1.0 - (touch.y / max(1, self.height))))
            self.screen_owner.send_input_cmd(f"TOUCH|{touch.id}|DOWN|{norm_x:.4f}|{norm_y:.4f}")
        else:
            touch.ud["trackpad_start"] = touch.pos
            touch.ud["has_moved"] = False

        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False

        pc_ip = self.screen_owner.get_pc_ip()
        if not pc_ip:
            return True

        if self.mode == "touchscreen":
            norm_x = max(0.0, min(1.0, touch.x / max(1, self.width)))
            norm_y = max(0.0, min(1.0, 1.0 - (touch.y / max(1, self.height))))
            self.screen_owner.send_input_cmd(f"TOUCH|{touch.id}|MOVE|{norm_x:.4f}|{norm_y:.4f}")
        else:
            dx = touch.dx * 1.5
            dy = -touch.dy * 1.5
            touch.ud["has_moved"] = True
            self.screen_owner.send_input_cmd(f"MOUSE|MOVE_REL|{int(dx)}|{int(dy)}")

        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False

        touch.ungrab(self)
        self.active_fingers.pop(touch.id, None)

        # Detect swipe-up from bottom edge to show quick-bar
        start_y = touch.ud.get('start_y', touch.y)
        dy = touch.y - start_y
        dt = time.time() - touch.ud.get('start_time', time.time())
        if start_y < dp(80) and dy > dp(45) and dt < 0.6:
            self.screen_owner.register_swipe_up()

        pc_ip = self.screen_owner.get_pc_ip()
        if not pc_ip:
            return True

        if self.mode == "touchscreen":
            norm_x = max(0.0, min(1.0, touch.x / max(1, self.width)))
            norm_y = max(0.0, min(1.0, 1.0 - (touch.y / max(1, self.height))))
            self.screen_owner.send_input_cmd(f"TOUCH|{touch.id}|UP|{norm_x:.4f}|{norm_y:.4f}")
        else:
            if not touch.ud.get("has_moved", False):
                self.screen_owner.send_input_cmd("MOUSE|CLICK|0|0")

        return True


class PCMirrorScreen(Screen):
    """
    Dedicated PC Screen Mirroring View with unobstructive HUD, collapsible quick bar,
    immersive gaming mode, and LDPlayer 9 / Nox On-Screen Gamepad Keybinds!
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._input_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovered_pc_ip: Optional[str] = None
        self.is_audio_muted = False
        self.gamepad_visible = False  # Hidden by default so user has clean full touch screen!
        self._swipe_count = 0
        self._last_swipe_time = 0.0
        self._qb_hide_trigger = None

        self.root_lay = FloatLayout()

        # 1. Main Display / Touch Surface
        self.surface = PCMirrorSurface(screen_owner=self, size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        self.root_lay.add_widget(self.surface)

        # 2. Status Label in Center with Frosted Glass Card Backdrop
        self.status_box = BoxLayout(
            orientation='vertical', size_hint=(0.82, None), height=dp(130),
            pos_hint={'center_x': 0.5, 'center_y': 0.5}, spacing=dp(6), padding=dp(12)
        )
        with self.status_box.canvas.before:
            Color(0.02, 0.08, 0.05, 0.88)
            self.sb_rect = RoundedRectangle(pos=self.status_box.pos, size=self.status_box.size, radius=[dp(16)])
            Color(*ACCENT_PRIMARY)
            self.sb_border = Line(rounded_rectangle=[self.status_box.x, self.status_box.y, self.status_box.width, self.status_box.height, dp(16)], width=1.4)
        self.status_box.bind(pos=self._update_status_box, size=self._update_status_box)

        self.status_title = Label(text="PC Mirror Active", font_size=sp(20), bold=True, color=ACCENT_PRIMARY)
        self.status_sub = Label(text="Waiting for PC video packets...", font_size=sp(13), color=TEXT_SECONDARY)
        self.mode_indicator = Label(text="Clean Touchscreen Mode (Swipe UP from bottom for Quick-Bar)", font_size=sp(11), color=ACCENT_SECONDARY)
        self.status_box.add_widget(self.status_title)
        self.status_box.add_widget(self.status_sub)
        self.status_box.add_widget(self.mode_indicator)
        self.root_lay.add_widget(self.status_box)

        # 3. Nox Player / LDPlayer 9 On-Screen Virtual Gamepad Overlay (Hidden initially)
        self.gamepad_overlay = VirtualGamepadOverlay(screen_owner=self, size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        self.gamepad_overlay.opacity = 0
        self.gamepad_overlay.disabled = True
        self.root_lay.add_widget(self.gamepad_overlay)

        # 4. Floating Quick-Bar (Hidden initially, triggered via swipe-up gesture)
        self.quick_bar = BoxLayout(
            orientation='horizontal', size_hint=(0.96, None), height=dp(40),
            pos_hint={'center_x': 0.5, 'y': 0.005}, spacing=dp(6), padding=dp(4)
        )
        with self.quick_bar.canvas.before:
            Color(0.04, 0.08, 0.06, 0.85)
            self.qb_rect = RoundedRectangle(pos=self.quick_bar.pos, size=self.quick_bar.size, radius=[dp(10)])
            Color(*ACCENT_PRIMARY)
            self.qb_border = Line(rounded_rectangle=[self.quick_bar.x, self.quick_bar.y, self.quick_bar.width, self.quick_bar.height, dp(10)], width=1.2)
        self.quick_bar.bind(pos=self._update_qb, size=self._update_qb)
        self._build_quick_bar_buttons()
        self.quick_bar.opacity = 0
        self.quick_bar.disabled = True
        self.root_lay.add_widget(self.quick_bar)

        # 5. Floating HUD Control Button (Translucent 35% opacity pill in corner)
        self.hud_btn = Button(
            text="MENU", font_size=sp(11), bold=True, size_hint=(None, None), size=(dp(48), dp(32)),
            pos_hint={'right': 0.99, 'top': 0.98}, background_color=(0, 0, 0, 0), opacity=0.45, color=TEXT_PRIMARY
        )
        with self.hud_btn.canvas.before:
            Color(0.12, 0.24, 0.18, 0.7)
            self.hud_btn_rect = RoundedRectangle(pos=self.hud_btn.pos, size=self.hud_btn.size, radius=[dp(12)])
        self.hud_btn.bind(pos=self._update_hud_btn, size=self._update_hud_btn, on_press=self.toggle_menu)
        self.root_lay.add_widget(self.hud_btn)

        # 6. Slide-down Control Drawer / Menu (Initially hidden)
        self.menu_drawer = BoxLayout(
            orientation='vertical', size_hint=(0.85, None), height=dp(340),
            pos_hint={'center_x': 0.5, 'top': 0.94}, spacing=dp(6), padding=dp(10)
        )
        with self.menu_drawer.canvas.before:
            Color(0.05, 0.10, 0.08, 0.96)
            self.menu_rect = RoundedRectangle(pos=self.menu_drawer.pos, size=self.menu_drawer.size, radius=[dp(16)])
            Color(*ACCENT_PRIMARY)
            self.menu_border = Line(rounded_rectangle=[self.menu_drawer.x, self.menu_drawer.y, self.menu_drawer.width, self.menu_drawer.height, dp(16)], width=1.2)
        self.menu_drawer.bind(pos=self._update_menu, size=self._update_menu)
        self._build_menu_drawer()
        self.menu_drawer.opacity = 0
        self.menu_drawer.disabled = True
        self.root_lay.add_widget(self.menu_drawer)

        # 7. Hidden TextInput for Native Soft Keyboard
        self.hidden_input = TextInput(size_hint=(None, None), size=(1, 1), opacity=0)
        self.hidden_input.bind(text=self._on_keyboard_text)
        self.root_lay.add_widget(self.hidden_input)

        self.add_widget(self.root_lay)

    def _update_status_box(self, *args):
        if hasattr(self, 'sb_rect'):
            self.sb_rect.pos = self.status_box.pos
            self.sb_rect.size = self.status_box.size
            self.sb_border.rounded_rectangle = [self.status_box.x, self.status_box.y, self.status_box.width, self.status_box.height, dp(16)]

    def _update_qb(self, *args):
        self.qb_rect.pos = self.quick_bar.pos
        self.qb_rect.size = self.quick_bar.size
        self.qb_border.rounded_rectangle = [self.quick_bar.x, self.quick_bar.y, self.quick_bar.width, self.quick_bar.height, dp(10)]

    def _update_hud_btn(self, *args):
        self.hud_btn_rect.pos = self.hud_btn.pos
        self.hud_btn_rect.size = self.hud_btn.size

    def _update_menu(self, *args):
        self.menu_rect.pos = self.menu_drawer.pos
        self.menu_rect.size = self.menu_drawer.size
        self.menu_border.rounded_rectangle = [self.menu_drawer.x, self.menu_drawer.y, self.menu_drawer.width, self.menu_drawer.height, dp(16)]

    def register_swipe_up(self):
        """Track upward swipes from bottom edge to reveal Quick-Bar."""
        now = time.time()
        if now - self._last_swipe_time > 1.8:
            self._swipe_count = 1
        else:
            self._swipe_count += 1
        self._last_swipe_time = now

        threshold = 2
        try:
            import main as mobile_main
            threshold = int(mobile_main.config.get("swipe_up_threshold", 2))
        except Exception:
            pass

        if self._swipe_count >= threshold:
            self.show_quick_bar()
            self._swipe_count = 0

    def show_quick_bar(self):
        self.quick_bar.disabled = False
        Animation.stop_all(self.quick_bar)
        anim = Animation(opacity=1.0, duration=0.22, t='out_quad')
        anim.start(self.quick_bar)
        if self._qb_hide_trigger:
            self._qb_hide_trigger.cancel()
        self._qb_hide_trigger = Clock.schedule_once(lambda dt: self.hide_quick_bar(), 6.0)

    def hide_quick_bar(self):
        Animation.stop_all(self.quick_bar)
        anim = Animation(opacity=0.0, duration=0.22, t='in_quad')
        anim.bind(on_complete=lambda *args: setattr(self.quick_bar, 'disabled', True))
        anim.start(self.quick_bar)

    def _build_quick_bar_buttons(self):
        self.quick_bar.clear_widgets()
        shortcuts = [
            ("Ctrl+C", "copy"),
            ("Ctrl+V", "paste"),
            ("Ctrl+Z", "undo"),
            ("Alt+Tab", "alt_tab"),
            ("Win+D", "win_d"),
            ("Esc", "esc"),
            ("Enter", "enter"),
            ("Ctrl+Alt+Del", "ctrl_alt_del"),
        ]
        try:
            import main as mobile_main
            cfg_shortcuts = mobile_main.config.get("quickbar_shortcuts", None)
            if cfg_shortcuts:
                shortcuts = [(s["label"], s["macro"]) for s in cfg_shortcuts]
        except Exception:
            pass
        for label, macro in shortcuts:
            btn = Button(
                text=label, font_size=sp(10 if len(label) > 6 else 11), bold=True,
                background_color=(0.14, 0.26, 0.20, 0.9), color=TEXT_PRIMARY
            )
            btn.bind(on_press=lambda inst, m=macro: self._on_quick_bar_click(m))
            self.quick_bar.add_widget(btn)

    def _on_quick_bar_click(self, macro: str):
        if macro == "ctrl_alt_del":
            self.send_input_cmd("KEY|DOWN|ctrl")
            self.send_input_cmd("KEY|DOWN|alt")
            self.send_input_cmd("KEY|DOWN|delete")
            self.send_input_cmd("KEY|UP|delete")
            self.send_input_cmd("KEY|UP|alt")
            self.send_input_cmd("KEY|UP|ctrl")
        else:
            self.send_input_cmd(f"MACRO|{macro}")

        # Refresh hide timer
        if self._qb_hide_trigger:
            self._qb_hide_trigger.cancel()
        self._qb_hide_trigger = Clock.schedule_once(lambda dt: self.hide_quick_bar(), 4.0)

    def _build_menu_drawer(self):
        self.menu_drawer.add_widget(Label(text="CelSuite Gaming & Controls", font_size=sp(15), bold=True, color=ACCENT_PRIMARY, size_hint_y=None, height=dp(24)))

        # Toggle Gamepad ON/OFF
        self.gamepad_btn = Button(text="On-Screen Gamepad: OFF", font_size=sp(12), bold=True, background_color=(0.12, 0.22, 0.17, 1), size_hint_y=None, height=dp(36))
        self.gamepad_btn.bind(on_press=self.toggle_gamepad)
        self.menu_drawer.add_widget(self.gamepad_btn)

        # Edit Gamepad Controls (LDPlayer 9 Mode)
        self.edit_ctrl_btn = Button(text="🛠️ Edit Controls (Move / Resize / Add)", font_size=sp(12), bold=True, background_color=(0.15, 0.32, 0.24, 1), size_hint_y=None, height=dp(36))
        self.edit_ctrl_btn.bind(on_press=self.enter_edit_mode)
        self.menu_drawer.add_widget(self.edit_ctrl_btn)

        # Switch Preset
        self.preset_btn = Button(text="Preset: FPS / PC RPG (WASD + Mouse)", font_size=sp(12), bold=True, background_color=(0.12, 0.22, 0.17, 1), size_hint_y=None, height=dp(36))
        self.preset_btn.bind(on_press=self.cycle_preset)
        self.menu_drawer.add_widget(self.preset_btn)

        # Opacity Cycle
        self.opacity_btn = Button(text="Gamepad Opacity: 55%", font_size=sp(12), bold=True, background_color=(0.12, 0.22, 0.17, 1), size_hint_y=None, height=dp(36))
        self.opacity_btn.bind(on_press=self.cycle_gamepad_opacity)
        self.menu_drawer.add_widget(self.opacity_btn)

        # Audio mute toggle
        self.audio_btn = Button(text="Mute PC Audio", font_size=sp(12), bold=True, background_color=(0.12, 0.22, 0.17, 1), size_hint_y=None, height=dp(36))
        self.audio_btn.bind(on_press=self.toggle_audio)
        self.menu_drawer.add_widget(self.audio_btn)

        # Soft keyboard
        kbd_btn = Button(text="Open Soft Keyboard", font_size=sp(12), bold=True, background_color=(0.12, 0.22, 0.17, 1), size_hint_y=None, height=dp(36))
        kbd_btn.bind(on_press=self.open_soft_keyboard)
        self.menu_drawer.add_widget(kbd_btn)

        # Exit
        exit_btn = Button(text="Exit PC Mirror", font_size=sp(12), bold=True, background_color=(0.45, 0.15, 0.15, 1), size_hint_y=None, height=dp(36))
        exit_btn.bind(on_press=self.go_back_home)
        self.menu_drawer.add_widget(exit_btn)

    def toggle_gamepad(self, instance=None):
        self.gamepad_visible = not self.gamepad_visible
        if self.gamepad_visible:
            self.gamepad_overlay.opacity = 1
            self.gamepad_overlay.disabled = False
            self.gamepad_btn.text = "On-Screen Gamepad: ON"
            self.mode_indicator.text = "Control Mode: Tablet Touchscreen • Gamepad Active"
        else:
            self.gamepad_overlay.opacity = 0
            self.gamepad_overlay.disabled = True
            self.gamepad_btn.text = "On-Screen Gamepad: OFF"
            self.mode_indicator.text = "Clean Touchscreen Mode (Swipe UP from bottom for Quick-Bar)"

    def close_menu(self):
        Animation.stop_all(self.menu_drawer)
        anim = Animation(opacity=0.0, duration=0.18, t='in_quad')
        anim.bind(on_complete=lambda *args: setattr(self.menu_drawer, 'disabled', True))
        anim.start(self.menu_drawer)

    def enter_edit_mode(self, instance=None):
        self.close_menu()
        if not self.gamepad_visible:
            self.toggle_gamepad()
        self.gamepad_overlay.toggle_edit_mode()

    def cycle_preset(self, instance):
        if self.gamepad_overlay.current_preset == "fps":
            self.gamepad_overlay.build_preset("moba")
            self.preset_btn.text = "Preset: MOBA / Brawl Stars (3-Skills)"
        else:
            self.gamepad_overlay.build_preset("fps")
            self.preset_btn.text = "Preset: FPS / PC RPG (WASD + Mouse)"

    def cycle_gamepad_opacity(self, instance):
        new_val = self.gamepad_overlay.cycle_opacity()
        self.opacity_btn.text = f"Gamepad Opacity: {int(new_val * 100)}%"

    def toggle_menu(self, instance=None):
        Animation.stop_all(self.menu_drawer)
        if self.menu_drawer.opacity < 0.1:
            self.menu_drawer.disabled = False
            Animation(opacity=1.0, duration=0.2, t='out_quad').start(self.menu_drawer)
        else:
            self.close_menu()

    def toggle_audio(self, instance):
        self.is_audio_muted = not self.is_audio_muted
        if self.is_audio_muted:
            self.audio_btn.text = "Unmute PC Audio"
        else:
            self.audio_btn.text = "Mute PC Audio"

    def open_soft_keyboard(self, instance):
        self.close_menu()
        self.hidden_input.focus = True

    def _on_keyboard_text(self, instance, text):
        if text:
            char = text[-1]
            self.send_input_cmd(f"KEY|TAP|{char}")
            self.hidden_input.text = ""

    def go_back_home(self, instance):
        self.close_menu()
        self.manager.current = 'main'

    def is_hud_touch(self, touch) -> bool:
        """Check if touch landed on interactive UI overlays or virtual controls."""
        if self.hud_btn.collide_point(*touch.pos):
            return True
        if self.menu_drawer.opacity > 0 and self.menu_drawer.collide_point(*touch.pos):
            return True
        if self.quick_bar.opacity > 0 and self.quick_bar.collide_point(*touch.pos):
            return True
        if self.gamepad_visible and self.gamepad_overlay.is_gamepad_touch(touch):
            return True
        return False

    def get_pc_ip(self) -> Optional[str]:
        if not self.discovered_pc_ip:
            main_screen = self.manager.get_screen('main')
            self.discovered_pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
        return self.discovered_pc_ip

    def send_input_cmd(self, cmd: str) -> None:
        """Shoot UDP input packet to PC input listener port 5562."""
        pc_ip = self.get_pc_ip()
        if not pc_ip:
            return
        try:
            self._input_sock.sendto(cmd.encode("utf-8"), (pc_ip, PORT_REVERSE_INPUT))
        except Exception:
            pass

    def on_enter(self):
        pc_ip = self.get_pc_ip()
        if pc_ip:
            self.status_sub.text = f"Connected to PC: {pc_ip}\nListening for stream on UDP port {PORT_REVERSE_VIDEO}..."
        else:
            self.status_sub.text = "PC not linked yet! Tap to Link on Home screen first."

        # Re-sync quick-bar shortcuts dynamically from config
        self._build_quick_bar_buttons()

        # Check default gamepad setting from user config
        try:
            import main as mobile_main
            should_enable = bool(mobile_main.config.get("gamepad_enabled_default", False))
            if should_enable and not self.gamepad_visible:
                self.toggle_gamepad()
            op = float(mobile_main.config.get("gamepad_opacity", 0.55))
            self.gamepad_overlay.set_hud_opacity(op)
            self.opacity_btn.text = f"Gamepad Opacity: {int(op * 100)}%"
        except Exception:
            pass

        # Start UDP video packet listener thread
        self._video_listener_running = True
        threading.Thread(target=self._video_listener_loop, daemon=True, name="MobileVideoListener").start()

    def on_leave(self):
        self._video_listener_running = False

    def _video_listener_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", PORT_REVERSE_VIDEO))
            sock.settimeout(1.0)
        except Exception:
            return

        received_packets = 0
        while getattr(self, "_video_listener_running", False):
            try:
                data, addr = sock.recvfrom(65536)
                if data:
                    received_packets += 1
                    if received_packets == 1:
                        Clock.schedule_once(lambda dt: self._on_first_video_packet(addr[0]))
            except socket.timeout:
                continue
            except Exception:
                break
        try:
            sock.close()
        except Exception:
            pass

    def _on_first_video_packet(self, sender_ip: str):
        self.status_title.text = "PC Screen Live!"
        self.status_sub.text = f"Beaming desktop from {sender_ip}\n(Hardware Decoded • Low Latency)"
        self.status_box.opacity = 0.2
