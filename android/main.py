import os
import sys
import time
import socket
import struct
import threading
import json
import subprocess
import traceback
import random

# Samsung JNI and Modified UTF-8 sensor workarounds
os.environ['SDL_SENSOR_DRIVER'] = 'dummy'
os.environ['KIVY_NO_ARGS'] = '1'

from kivy.config import Config
if 'ANDROID_ARGUMENT' not in os.environ and 'PYTHON_SERVICE_ARGUMENT' not in os.environ:
    Config.set('graphics', 'width', '400')
    Config.set('graphics', 'height', '720')
    Config.set('graphics', 'resizable', '0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.switch import Switch
from kivy.uix.spinner import Spinner
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.widget import Widget
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.uix.slider import Slider
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line, Ellipse, Scale, PushMatrix, PopMatrix
from kivy.metrics import dp, sp
from kivy.core.window import Window
from kivy.animation import Animation
from kivy.properties import NumericProperty

# App Version & Ports
VERSION = "2610.30.0"
PORT_TCP_TRANSFER = 5558
PORT_MIRROR_VIDEO = 5563  # PC -> Phone MJPEG mirror TCP

def get_storage_dirs():
    """Determines the correct internal and external storage directories for the app."""
    external_data_dir = None
    internal_dir = os.path.join(os.path.expanduser("~"), "scrcpy_link")

    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        if activity:
            internal_dir = activity.getFilesDir().getAbsolutePath()
            ext_files = activity.getExternalFilesDir(None)
            if ext_files:
                external_data_dir = ext_files.getAbsolutePath()
    except Exception as exc:
        print(f"Failed to query Android context: {exc}")

    base_dir = external_data_dir or internal_dir
    os.makedirs(base_dir, exist_ok=True)

    config_file = os.path.join(base_dir, "scrcpy_heartbeat_config.json")
    log_dir = os.path.join(base_dir, "log")
    os.makedirs(log_dir, exist_ok=True)
    vault_dir = os.path.join(base_dir, "Vault")
    os.makedirs(vault_dir, exist_ok=True)

    can_write = external_data_dir is not None
    return config_file, log_dir, vault_dir, can_write

CONFIG_FILE, LOG_DIR, VAULT_DIR, CAN_WRITE_EXTERNAL = get_storage_dirs()
LOG_FILE = os.path.join(LOG_DIR, "ScrcpyLink.log")

try:
    os.makedirs(VAULT_DIR, exist_ok=True)
except OSError as e:
    print(f"Failed to create vault dir: {e}")

def load_config():
    """Loads the application configuration from JSON."""
    defaults = {
        "heartbeat_port": 5556,
        "discovery_port": 5557,
        "adb_port": 5555,
        "logging_enabled": True,
        "use_system_font": True,
        "glass_opacity": 0.40,
        "wallpaper_tint_opacity": 0.40,
        "wallpaper_fit": "Stretch",
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config_data = json.load(f)
            for k, v in defaults.items():
                if k not in config_data:
                    config_data[k] = v
            return config_data
    except OSError as e:
        print(f"Config load failed: {e}")
    except json.JSONDecodeError as e:
        print(f"Config parse failed: {e}")
    return defaults

def save_config(config_data):
    """Saves the application configuration to JSON."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=2)
    except OSError as e:
        print(f"Config save failed: {e}")

config = load_config()

# CelStudio Emerald Green Liquid Glass Palette
GLASS_OPACITY = float(config.get("glass_opacity", 0.40))
WALLPAPER_TINT = float(config.get("wallpaper_tint_opacity", 0.40))

DARK_BG = (0.03, 0.07, 0.05, 1)
PRIMARY_BG = (0.04, 0.09, 0.07, 1)
SECONDARY_BG = (0.06, 0.12, 0.09, 1)
CARD_BG = (0.05, 0.13, 0.09, max(0.40, GLASS_OPACITY))
INPUT_BG = (0.03, 0.09, 0.06, 0.70)
BUTTON_BG = (0.07, 0.18, 0.12, max(0.45, GLASS_OPACITY))

ACCENT_PRIMARY = (0.10, 0.85, 0.58, 1)     # High-contrast bright Emerald
ACCENT_SECONDARY = (0.25, 0.90, 0.65, 1)   # Bright Mint
ACCENT_TERTIARY = (0.12, 0.80, 0.72, 1)    # Bright Teal
ACCENT_GLOW = (0.50, 0.95, 0.75, 1)        # Vivid Neon Glow

TEXT_PRIMARY = (0.96, 0.99, 0.97, 1)
TEXT_SECONDARY = (0.70, 0.82, 0.75, 1)
TEXT_ON_ACCENT = (0.02, 0.10, 0.06, 1)

SUCCESS = (0.10, 0.85, 0.58, 1)
WARNING = (0.98, 0.68, 0.12, 1)
ERROR = (0.96, 0.32, 0.32, 1)

BORDER_SUBTLE = (0.10, 0.85, 0.58, 0.50)

LOG_MAX_BYTES = 50 * 1024
def app_log(msg):
    """Logs messages to console and file, maintaining a size limit."""
    print(msg)
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_str = f"[{timestamp}] {msg}\n"
        with open(LOG_FILE, "a") as f:
            f.write(log_str)

        if os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
            with open(LOG_FILE, "r") as f:
                content = f.read()
            with open(LOG_FILE, "w") as f:
                f.write(content[len(content)//2:])
    except OSError as e:
        print(f"Logging failed: {e}")

_vm_policy_disabled = False

def disable_file_uri_exposure_check():
    """Disables the FileUriExposedException checks on Android 11+ (runs once)."""
    global _vm_policy_disabled
    if _vm_policy_disabled:
        return
    try:
        from jnius import autoclass
        StrictMode = autoclass('android.os.StrictMode')
        VmPolicy = autoclass('android.os.StrictMode$VmPolicy')
        Builder = autoclass('android.os.StrictMode$VmPolicy$Builder')
        builder = Builder()
        StrictMode.setVmPolicy(builder.build())
        _vm_policy_disabled = True
        app_log("Disabled VmPolicy FileUriExposedException checks.")
    except Exception as e:
        app_log(f"Failed to disable VmPolicy: {e}")

_shizuku_last_attempt = 0.0
_shizuku_cooldown_sec = 120.0

def enable_shizuku_wireless_adb():
    """Attempts to enable wireless ADB via Shizuku API, then falls back to root."""
    global _shizuku_last_attempt
    now = time.time()
    if now - _shizuku_last_attempt < _shizuku_cooldown_sec:
        return
    _shizuku_last_attempt = now
    app_log("Starting Shizuku/Root wireless ADB trigger...")
    adb_cmd = "setprop service.adb.tcp.port 5555; setprop persist.adb.tcp.port 5555; setprop service.adb.tcp.bind 0.0.0.0; stop adbd && start adbd"

    try:
        from jnius import autoclass
        Shizuku = autoclass('rikka.shizuku.Shizuku')

        if not Shizuku.pingBinder():
            app_log("Shizuku service not running, skipping API method")
        elif Shizuku.checkSelfPermission() != 0:
            app_log("Shizuku permission not granted, requesting...")
            Shizuku.requestPermission(0)
            app_log("Requested Shizuku permission. Will try again next heartbeat.")
        else:
            process = Shizuku.newProcess(["sh", "-c", adb_cmd], None, None)
            exit_code = process.waitFor()
            app_log(f"Shizuku API: wireless ADB enabled! (exit={exit_code})")
            return
    except Exception as e:
        app_log(f"Shizuku not available (normal on stock phones): {e}")

    try:
        from jnius import autoclass
        Runtime = autoclass('java.lang.Runtime')
        process = Runtime.getRuntime().exec(["su", "-c", adb_cmd])
        process.waitFor()
        app_log("Root trigger successful via JNI Runtime")
        return
    except Exception as e:
        app_log(f"Root (su) not available (normal): {e}")

    app_log("Wireless ADB auto-enable skipped — enable Wireless Debugging manually.")


# --- SHARED LIQUID GLASS BASE SCREEN ---

class GlassScreen(Screen):
    """
    Base Screen providing the CelSuite CelWeave wallpaper, dark tint overlay,
    and responsive geometry synchronization across all application views.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._bg_layout = FloatLayout(size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})

        wp_path = 'wallpaper_mobile.jpg'
        if not os.path.exists(wp_path):
            wp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wallpaper_mobile.jpg')
        if not os.path.exists(wp_path):
            wp_path = 'wallpaper.jpg'
        if not os.path.exists(wp_path):
            wp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wallpaper.jpg')

        with self._bg_layout.canvas.before:
            Color(0.02, 0.06, 0.04, 1)
            self.base_rect = Rectangle()

            if os.path.exists(wp_path):
                Color(1, 1, 1, 1)
                self.wp_rect = Rectangle(source=wp_path)
            else:
                self.wp_rect = None

            tint_val = float(config.get("wallpaper_tint_opacity", 0.40))
            self.tint_color_inst = Color(0.01, 0.05, 0.03, tint_val)
            self.tint_rect = Rectangle()

        self._bg_layout.bind(pos=self._update_bg, size=self._update_bg)
        self.add_widget(self._bg_layout)

    def _update_bg(self, *args):
        win_size = Window.size
        win_w, win_h = win_size
        self.base_rect.pos = (0, 0)
        self.base_rect.size = win_size

        if self.wp_rect:
            fit_mode = config.get("wallpaper_fit", "Stretch")
            if fit_mode == "Zoom" and win_h > 0:
                img_ratio = 1080.0 / 2340.0
                win_ratio = win_w / float(win_h)
                if win_ratio > img_ratio:
                    target_w = win_w
                    target_h = win_w / img_ratio
                else:
                    target_h = win_h
                    target_w = win_h * img_ratio
                x = (win_w - target_w) / 2.0
                y = (win_h - target_h) / 2.0
                self.wp_rect.pos = (x, y)
                self.wp_rect.size = (target_w, target_h)
            else:
                self.wp_rect.pos = (0, 0)
                self.wp_rect.size = win_size

        self.tint_rect.pos = (0, 0)
        self.tint_rect.size = win_size

    def update_tint(self, val):
        if hasattr(self, 'tint_color_inst'):
            self.tint_color_inst.a = val

    def on_enter(self):
        super().on_enter()
        self._update_bg()


# --- CUSTOM WIDGET CLASSES ---

_active_cards = []

class RoundedCard(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self.bg_color_inst = Color(*CARD_BG)
            self.rect = RoundedRectangle(radius=[dp(14)])
            self.border_color_inst = Color(*BORDER_SUBTLE)
            self.border = Line(width=1.2)
        self.bind(pos=self.update_canvas, size=self.update_canvas)
        _active_cards.append(self)

    def update_canvas(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
        self.border.rounded_rectangle = [self.x, self.y, self.width, self.height, dp(14)]

    def refresh_theme(self):
        self.bg_color_inst.rgba = CARD_BG


class AnimatedButton(Button):
    scale_value = NumericProperty(1.0)

    def __init__(self, **kwargs):
        kwargs.setdefault('background_normal', '')
        kwargs.setdefault('background_down', '')
        kwargs.setdefault('background_color', (0, 0, 0, 0))
        self.btn_color = kwargs.pop('btn_color', ACCENT_PRIMARY)
        if self.btn_color == ACCENT_PRIMARY:
            kwargs.setdefault('color', TEXT_ON_ACCENT)
        else:
            kwargs.setdefault('color', (1, 1, 1, 1))
        kwargs.setdefault('font_size', sp(14))
        kwargs.setdefault('bold', True)
        super().__init__(**kwargs)

        with self.canvas.before:
            PushMatrix()
            self.scale_inst = Scale(1.0, 1.0, 1.0)
            self.color_inst = Color(*self.btn_color)
            self.bg_rect = RoundedRectangle(radius=[dp(10)])
        with self.canvas.after:
            PopMatrix()

        self.bind(scale_value=self.on_scale_value, pos=self.on_pos_size, size=self.on_pos_size)

    def on_pos_size(self, *args):
        self.scale_inst.origin = self.center
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def on_scale_value(self, instance, value):
        self.scale_inst.x = value
        self.scale_inst.y = value

    def on_press(self):
        super().on_press()
        anim = Animation(scale_value=0.95, duration=0.05, t='out_quad') + Animation(scale_value=1.0, duration=0.1, t='out_bounce')
        anim.start(self)


class GridCard(BoxLayout):
    def __init__(self, icon="", title="", subtitle="", btn_color=CARD_BG, on_press_callback=None, **kwargs):
        kwargs.setdefault('orientation', 'vertical')
        kwargs.setdefault('padding', dp(12))
        kwargs.setdefault('spacing', dp(4))
        super().__init__(**kwargs)
        self.btn_color = btn_color
        self.on_press_callback = on_press_callback

        with self.canvas.before:
            self.bg_color_inst = Color(*self.btn_color)
            self.bg_rect = RoundedRectangle(radius=[dp(16)])
            Color(*BORDER_SUBTLE)
            self.border_line = Line(width=1.2)

        self.bind(pos=self.update_canvas, size=self.update_canvas)

        icon_lbl = Label(text=icon, font_size=sp(16), bold=True, size_hint_y=0.45, halign='center', valign='middle', color=ACCENT_PRIMARY)
        icon_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        title_lbl = Label(text=title, font_size=sp(14), bold=True, size_hint_y=0.35, halign='center', valign='middle', color=TEXT_PRIMARY)
        title_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        sub_lbl = Label(text=subtitle, font_size=sp(11), size_hint_y=0.2, halign='center', valign='middle', color=TEXT_SECONDARY)
        sub_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        self.add_widget(icon_lbl)
        self.add_widget(title_lbl)
        self.add_widget(sub_lbl)
        _active_cards.append(self)

    def update_canvas(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.border_line.rounded_rectangle = [self.x, self.y, self.width, self.height, dp(16)]

    def refresh_theme(self):
        self.bg_color_inst.rgba = CARD_BG

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self.on_press_callback:
                self.on_press_callback(self)
            return True
        return super().on_touch_down(touch)


class PulseIndicator(Widget):
    radius = NumericProperty(dp(10))
    alpha = NumericProperty(0.8)

    def __init__(self, **kwargs):
        kwargs.setdefault('size_hint_y', None)
        kwargs.setdefault('height', dp(40))
        kwargs.setdefault('size_hint_x', None)
        kwargs.setdefault('width', dp(40))
        super().__init__(**kwargs)
        self.is_connected = False
        with self.canvas:
            self.color_inst = Color(WARNING[0], WARNING[1], WARNING[2], self.alpha)
            self.line_inst = Line(circle=(self.center_x, self.center_y, self.radius), width=dp(2))
        self.bind(radius=self.update_circle, alpha=self.update_circle, pos=self.update_circle, size=self.update_circle)
        Clock.schedule_interval(self.pulse, 1.2)

    def update_circle(self, *args):
        self.color_inst.a = self.alpha
        self.line_inst.circle = (self.center_x, self.center_y, self.radius)

    def pulse(self, dt):
        c = SUCCESS if self.is_connected else WARNING
        self.color_inst.rgb = c[:3]
        self.radius = dp(8)
        self.alpha = 0.8
        anim = Animation(radius=dp(20), alpha=0, duration=1.0, t='out_quad')
        anim.start(self)

    def set_state(self, connected):
        self.is_connected = connected


class GradientBar(Widget):
    progress = NumericProperty(0)

    def __init__(self, **kwargs):
        kwargs.setdefault('size_hint_y', None)
        kwargs.setdefault('height', dp(10))
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*INPUT_BG)
            self.bg_rect = RoundedRectangle(radius=[dp(5)])
            self.fg_color = Color(*ACCENT_PRIMARY)
            self.fg_rect = RoundedRectangle(radius=[dp(5)])
        self.bind(pos=self.update_rect, size=self.update_rect, progress=self.update_rect)

    def update_rect(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.fg_rect.pos = self.pos
        self.fg_rect.size = (self.width * (self.progress / 100.0), self.height)


# --- TCP FILE SERVER THREAD ---

class TCPFileServerThread(threading.Thread):
    """Listens on TCP port 5558 for incoming files/folders sent from PC."""
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.server_sock = None

    def run(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(('0.0.0.0', PORT_TCP_TRANSFER))
            self.server_sock.listen(3)
            app_log(f"Mobile TCP Server active on port {PORT_TCP_TRANSFER}")

            while self.running:
                try:
                    client, addr = self.server_sock.accept()
                    threading.Thread(target=self.handle_client, args=(client, addr), daemon=True).start()
                except OSError:
                    break
        except Exception as e:
            app_log(f"Mobile TCP Server init failed: {e}")

    def handle_client(self, client, addr):
        try:
            client.settimeout(60.0)
            header_line = b""
            while not header_line.endswith(b"\n"):
                c = client.recv(1)
                if not c:
                    return
                header_line += c

            parts = header_line.decode('utf-8').strip().split('|')
            cmd = parts[0]

            if cmd == "FILE_SEND" and len(parts) >= 3:
                filename = parts[1]
                filesize = int(parts[2])
                save_path = os.path.join(VAULT_DIR, filename)
                app_log(f"Receiving '{filename}' ({filesize} bytes) from {addr[0]}...")

                with open(save_path, 'wb') as f:
                    recvd = 0
                    while recvd < filesize:
                        chunk = client.recv(min(65536, filesize - recvd))
                        if not chunk:
                            break
                        f.write(chunk)
                        recvd += len(chunk)

                app_log(f"Received file: {save_path}")

            elif cmd == "FOLDER_SEND" and len(parts) >= 3:
                import zipfile
                foldername = parts[1]
                filesize = int(parts[2])
                temp_zip = os.path.join(VAULT_DIR, f".tmp_{foldername}.zip")
                dest_dir = os.path.join(VAULT_DIR, foldername)
                app_log(f"Receiving folder '{foldername}' ({filesize} bytes)...")

                with open(temp_zip, 'wb') as f:
                    recvd = 0
                    while recvd < filesize:
                        chunk = client.recv(min(65536, filesize - recvd))
                        if not chunk:
                            break
                        f.write(chunk)
                        recvd += len(chunk)

                os.makedirs(dest_dir, exist_ok=True)
                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    zf.extractall(dest_dir)
                try:
                    os.remove(temp_zip)
                except OSError:
                    pass
                app_log(f"Extracted folder to: {dest_dir}")

        except Exception as e:
            app_log(f"File transfer client error: {e}")
        finally:
            try:
                client.close()
            except OSError:
                pass


# --- PARTICLE BACKGROUND ---

class ParticleBackground(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.particles = []
        Clock.schedule_interval(self.update_particles, 1/30)

    def update_particles(self, dt):
        if not self.canvas: return
        if random.random() < 0.1 and len(self.particles) < 35:
            p = {
                'x': random.uniform(self.x, self.right),
                'y': self.y - dp(10),
                'speed': random.uniform(dp(20), dp(45)),
                'size': random.uniform(dp(3), dp(7)),
                'alpha': random.uniform(0.1, 0.35),
                'inst': None,
                'color_inst': None
            }
            with self.canvas:
                p['color_inst'] = Color(*ACCENT_GLOW[:3], p['alpha'])
                p['inst'] = Ellipse(pos=(p['x'], p['y']), size=(p['size'], p['size']))
            self.particles.append(p)

        for p in self.particles[:]:
            p['y'] += p['speed'] * dt
            if p['y'] > self.top:
                self.canvas.remove(p['color_inst'])
                self.canvas.remove(p['inst'])
                self.particles.remove(p)
            else:
                p['inst'].pos = (p['x'], p['y'])


# ── SCREEN 1: MAIN SCREEN (HOME) ──────────────────────────────────────────────

class MainScreen(GlassScreen):
    """The main interface for the Scrcpy Link."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.particle_bg = ParticleBackground(size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        self._bg_layout.add_widget(self.particle_bg)

        scroll = ScrollView(size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(14), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        # 1. Top Header Bar
        top_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(36), spacing=dp(8))
        face_path = 'android_face.png'
        if not os.path.exists(face_path):
            face_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'android_face.png')
        if os.path.exists(face_path):
            face_img = Image(source=face_path, size_hint=(None, 1), width=dp(28))
            top_bar.add_widget(face_img)

        self.label = Label(
            text="CelSuite — P2P Screen Mirror",
            font_size=sp(15),
            bold=True,
            color=TEXT_PRIMARY,
            outline_color=(0.02, 0.05, 0.03, 1),
            outline_width=dp(1.2),
            size_hint_x=1.0,
            halign='left',
            valign='middle'
        )
        self.label.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        top_bar.add_widget(self.label)
        content.add_widget(top_bar)

        # 2. Central Hero Connection Card
        hero_card = RoundedCard(orientation='vertical', size_hint_y=None, height=dp(170), padding=dp(14), spacing=dp(8))

        self.pc_ip_label = Label(
            text="Searching for PC broadcast...",
            font_size=sp(14),
            bold=True,
            color=TEXT_PRIMARY,
            size_hint_y=None,
            height=dp(26),
            halign='center',
            valign='middle'
        )
        self.pc_ip_label.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        hero_card.add_widget(self.pc_ip_label)

        status_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(36), spacing=dp(8))
        self.pulse = PulseIndicator()
        self.status_label = Label(
            text="Listening on UDP:5557...",
            font_size=sp(12),
            color=TEXT_SECONDARY,
            halign='left',
            valign='middle'
        )
        self.status_label.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        status_row.add_widget(self.pulse)
        status_row.add_widget(self.status_label)
        hero_card.add_widget(status_row)

        restart_btn = AnimatedButton(text="TAP TO LINK", btn_color=ACCENT_PRIMARY, font_size=sp(15), size_hint_y=None, height=dp(46))
        restart_btn.bind(on_press=self.restart_connection)
        hero_card.add_widget(restart_btn)

        content.add_widget(hero_card)

        # 3. 2x3 Action Grid
        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, height=dp(325))
        grid.add_widget(GridCard(icon="[PC]", title="Watch PC", subtitle="Live PC screen + control", btn_color=CARD_BG, on_press_callback=lambda x: setattr(self.manager, 'current', 'pc_mirror')))
        grid.add_widget(GridCard(icon="[WIFI]", title="WiFi Transfer", subtitle="Send & receive files", btn_color=CARD_BG, on_press_callback=lambda x: setattr(self.manager, 'current', 'transfer')))
        grid.add_widget(GridCard(icon="[VAULT]", title="File Vault", subtitle="Downloaded media", btn_color=CARD_BG, on_press_callback=lambda x: setattr(self.manager, 'current', 'vault')))
        grid.add_widget(GridCard(icon="[CFG]", title="Settings", subtitle="App preferences", btn_color=CARD_BG, on_press_callback=lambda x: setattr(self.manager, 'current', 'settings')))
        grid.add_widget(GridCard(icon="[LOGS]", title="System Logs", subtitle="Live terminal logs", btn_color=CARD_BG, on_press_callback=lambda x: setattr(self.manager, 'current', 'logs')))
        grid.add_widget(GridCard(icon="[GUIDE]", title="Setup Manual", subtitle="Guide & instructions", btn_color=CARD_BG, on_press_callback=lambda x: setattr(self.manager, 'current', 'help')))

        content.add_widget(grid)
        scroll.add_widget(content)
        self.add_widget(scroll)

        self.sending = False
        self.discovered_pc_ip = None
        self._discovery_running = False

    def on_enter(self):
        super().on_enter()
        disable_file_uri_exposure_check()
        if not self._discovery_running:
            app_log("Launching background ADB triggers")
            threading.Thread(target=enable_shizuku_wireless_adb, daemon=True).start()
            self._start_services()

    def restart_connection(self, instance):
        app_log("Restarting link...")
        self._stop_services()
        threading.Thread(target=enable_shizuku_wireless_adb, daemon=True).start()
        self.pc_ip_label.text = "Searching for PC broadcast..."
        self.status_label.text = "Listening on UDP:5557..."
        self.pulse.set_state(False)
        self._start_services()

    def _start_services(self):
        self._discovery_running = True
        threading.Thread(target=self.discovery_listener, daemon=True).start()

    def _stop_services(self):
        self._discovery_running = False
        self.sending = False

    def discovery_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(2.0)
            sock.bind(("0.0.0.0", config.get("discovery_port", 5557)))

            while self._discovery_running:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = data.decode('utf-8').strip()
                    if msg.startswith("SCRCPC_HERE"):
                        pc_ip = msg.split()[1]
                        if self.discovered_pc_ip != pc_ip:
                            self.discovered_pc_ip = pc_ip
                            app_log(f"Discovered PC: {pc_ip}")
                            Clock.schedule_once(lambda dt: self.start_heartbeat(pc_ip))
                except socket.timeout:
                    pass
                except Exception as e:
                    time.sleep(1)
        except Exception as e:
            app_log(f"Discovery socket failed: {e}")
        finally:
            sock.close()

    def start_heartbeat(self, pc_ip):
        self.pc_ip_label.text = f"Linked PC: {pc_ip}"
        self.status_label.text = f"Link active (Heartbeat -> {pc_ip})"
        self.pulse.set_state(True)
        if not self.sending:
            self.sending = True
            threading.Thread(target=self.heartbeat_loop, args=(pc_ip,), daemon=True).start()

    def stop_heartbeat(self):
        self.sending = False
        self.pulse.set_state(False)
        self.status_label.text = "Mirroring suspended"

    def _get_phone_ip(self, target_ip):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target_ip, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        return "127.0.0.1"

    def heartbeat_loop(self, target_ip):
        port = config.get("heartbeat_port", 5556)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        consecutive_errors = 0
        backoff = 4.0
        try:
            while self.sending:
                try:
                    phone_ip = self._get_phone_ip(target_ip)
                    msg = f"HELLO_USER|{phone_ip}|{config.get('adb_port', 5555)}"
                    sock.sendto(msg.encode('utf-8'), (target_ip, port))
                    consecutive_errors = 0
                    backoff = 4.0
                except OSError as e:
                    consecutive_errors += 1
                    if consecutive_errors >= 60:
                        self.sending = False
                        break
                    try:
                        sock.close()
                    except Exception:
                        pass
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    backoff = min(backoff * 1.5, 30.0)
                except Exception:
                    pass
                time.sleep(backoff)
        finally:
            try:
                sock.close()
            except Exception:
                pass


# ── SCREEN 2: PC MIRROR SCREEN (WATCH PC) ─────────────────────────────────────

class PCMirrorScreen(GlassScreen):
    """
    Low-Latency Reverse PC Mirroring & Gamepad Screen for CelSuite Mobile.
    Features:
    - Dynamic Landscape & Portrait switching (via Android ActivityInfo & Window resizing)
    - 1:1 Pixel-Perfect Direct Touch mapping for PC emulators (LDPlayer, Nox, MuMu)
    - Zero-Buffer Stale Frame Dropping for 60FPS ultra-low latency gaming
    - Floating Collapsible Gaming HUD with D-Pad & Action buttons
    - Multi-Touch hold support for simultaneous movement + action
    - Virtual Keyboard toggle for in-game text entry
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_landscape = False
        self.touch_mode = "DIRECT"  # "DIRECT" (Emulator/Game) or "TRACKPAD" (Desktop)
        self.hud_visible = True
        self._mirror_sock = None
        self._mirror_running = False
        self._latest_jpg = None
        self._render_scheduled = False
        self._fps_counter = 0
        self._fps_t0 = time.time()
        self._live_fps = 0

        # Root layout for screen
        self.root_float = FloatLayout(size_hint=(1, 1))

        # 1. Fullscreen Video Surface
        self.video_img = Image(allow_stretch=True, keep_ratio=True, size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        self.video_img.opacity = 0
        self.root_float.add_widget(self.video_img)

        # Connection / Guide Hint Overlay
        self.hint_box = RoundedCard(orientation='vertical', size_hint=(0.68, 0.42), pos_hint={'center_x': 0.5, 'center_y': 0.58}, padding=dp(10), spacing=dp(6))
        self.hint_title = Label(text="PC Mirror Ready", font_size=sp(15), bold=True, color=ACCENT_PRIMARY, size_hint_y=None, height=dp(26))
        self.hint_desc = Label(
            text="Waiting for live PC stream on port 5563...\n\n"
                 "• Launch your game or emulator (LDPlayer, Nox, MuMu) on PC.\n"
                 "• Tap 'Rotate' for Fullscreen Landscape Gaming mode!",
            font_size=sp(11),
            color=TEXT_PRIMARY,
            halign='center',
            valign='middle'
        )
        self.hint_desc.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        self.hint_reconnect_btn = AnimatedButton(text="Connect / Refresh", btn_color=ACCENT_PRIMARY, size_hint_y=None, height=dp(40))
        self.hint_reconnect_btn.bind(on_press=lambda x: self.start_video())
        self.hint_box.add_widget(self.hint_title)
        self.hint_box.add_widget(self.hint_desc)
        self.hint_box.add_widget(self.hint_reconnect_btn)
        self.root_float.add_widget(self.hint_box)

        # 2. Top Floating Gaming Pill Toolbar
        self.top_toolbar = RoundedCard(orientation='horizontal', size_hint=(0.96, None), height=dp(38), pos_hint={'center_x': 0.5, 'top': 0.98}, padding=dp(4), spacing=dp(6))
        
        self.btn_exit = AnimatedButton(text="< Exit", btn_color=BUTTON_BG, size_hint_x=None, width=dp(65), font_size=sp(11))
        self.btn_exit.bind(on_press=self.go_back)

        self.status_badge = Label(text="Connecting...", font_size=sp(11), bold=True, color=WARNING, size_hint_x=1.0, halign='left', valign='middle')
        self.status_badge.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        self.btn_rotate = AnimatedButton(text="Rotate", btn_color=ACCENT_TERTIARY, size_hint_x=None, width=dp(65), font_size=sp(11))
        self.btn_rotate.bind(on_press=self.toggle_orientation)

        self.btn_mode = AnimatedButton(text="Direct", btn_color=CARD_BG, size_hint_x=None, width=dp(60), font_size=sp(11))
        self.btn_mode.bind(on_press=self.toggle_touch_mode)

        self.btn_keyboard = AnimatedButton(text="Keybd", btn_color=CARD_BG, size_hint_x=None, width=dp(55), font_size=sp(11))
        self.btn_keyboard.bind(on_press=self.toggle_keyboard)

        self.btn_hud_toggle = AnimatedButton(text="HUD", btn_color=ACCENT_PRIMARY, size_hint_x=None, width=dp(50), font_size=sp(11))
        self.btn_hud_toggle.bind(on_press=self.toggle_hud_visibility)

        self.top_toolbar.add_widget(self.btn_exit)
        self.top_toolbar.add_widget(self.status_badge)
        self.top_toolbar.add_widget(self.btn_rotate)
        self.top_toolbar.add_widget(self.btn_mode)
        self.top_toolbar.add_widget(self.btn_keyboard)
        self.top_toolbar.add_widget(self.btn_hud_toggle)
        self.root_float.add_widget(self.top_toolbar)

        # 3. Floating Virtual Gamepad Overlay (D-Pad on Left, Actions on Right)
        self.hud_overlay = FloatLayout(size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})

        # D-Pad (Left Thumb Zone)
        self.dpad_box = RoundedCard(orientation='vertical', size_hint=(None, None), size=(dp(140), dp(130)), pos_hint={'x': 0.03, 'y': 0.05}, padding=dp(4), spacing=dp(2))
        
        dpad_top = BoxLayout(orientation='horizontal', size_hint_y=0.33)
        btn_w = AnimatedButton(text="W", btn_color=BUTTON_BG, font_size=sp(12))
        btn_w.bind(on_press=lambda x: self.send_key_action("DOWN", "w"), on_release=lambda x: self.send_key_action("UP", "w"))
        dpad_top.add_widget(Label(size_hint_x=0.25))
        dpad_top.add_widget(btn_w)
        dpad_top.add_widget(Label(size_hint_x=0.25))

        dpad_mid = BoxLayout(orientation='horizontal', size_hint_y=0.33, spacing=dp(4))
        btn_a = AnimatedButton(text="A", btn_color=BUTTON_BG, font_size=sp(12))
        btn_a.bind(on_press=lambda x: self.send_key_action("DOWN", "a"), on_release=lambda x: self.send_key_action("UP", "a"))
        btn_s = AnimatedButton(text="S", btn_color=BUTTON_BG, font_size=sp(12))
        btn_s.bind(on_press=lambda x: self.send_key_action("DOWN", "s"), on_release=lambda x: self.send_key_action("UP", "s"))
        btn_d = AnimatedButton(text="D", btn_color=BUTTON_BG, font_size=sp(12))
        btn_d.bind(on_press=lambda x: self.send_key_action("DOWN", "d"), on_release=lambda x: self.send_key_action("UP", "d"))
        dpad_mid.add_widget(btn_a)
        dpad_mid.add_widget(btn_s)
        dpad_mid.add_widget(btn_d)

        dpad_bot = BoxLayout(orientation='horizontal', size_hint_y=0.33, spacing=dp(4))
        btn_lclick = AnimatedButton(text="L-Click", btn_color=CARD_BG, font_size=sp(10))
        btn_lclick.bind(on_press=lambda x: self.send_mouse_cmd("DOWN", 1, 0), on_release=lambda x: self.send_mouse_cmd("UP", 1, 0))
        btn_rclick = AnimatedButton(text="R-Click", btn_color=CARD_BG, font_size=sp(10))
        btn_rclick.bind(on_press=lambda x: self.send_mouse_cmd("DOWN", 3, 0), on_release=lambda x: self.send_mouse_cmd("UP", 3, 0))
        dpad_bot.add_widget(btn_lclick)
        dpad_bot.add_widget(btn_rclick)

        self.dpad_box.add_widget(dpad_top)
        self.dpad_box.add_widget(dpad_mid)
        self.dpad_box.add_widget(dpad_bot)
        self.hud_overlay.add_widget(self.dpad_box)

        # Action Buttons (Right Thumb Zone)
        self.actions_box = RoundedCard(orientation='vertical', size_hint=(None, None), size=(dp(140), dp(130)), pos_hint={'right': 0.97, 'y': 0.05}, padding=dp(4), spacing=dp(4))
        
        act_row1 = BoxLayout(orientation='horizontal', size_hint_y=0.33, spacing=dp(4))
        btn_space = AnimatedButton(text="Space", btn_color=ACCENT_PRIMARY, font_size=sp(11))
        btn_space.bind(on_press=lambda x: self.send_key_action("DOWN", "space"), on_release=lambda x: self.send_key_action("UP", "space"))
        btn_enter = AnimatedButton(text="Enter", btn_color=BUTTON_BG, font_size=sp(11))
        btn_enter.bind(on_press=lambda x: self.send_key_action("DOWN", "enter"), on_release=lambda x: self.send_key_action("UP", "enter"))
        act_row1.add_widget(btn_space)
        act_row1.add_widget(btn_enter)

        act_row2 = BoxLayout(orientation='horizontal', size_hint_y=0.33, spacing=dp(4))
        btn_esc = AnimatedButton(text="Esc", btn_color=BUTTON_BG, font_size=sp(11))
        btn_esc.bind(on_press=lambda x: self.send_key_action("TAP", "esc"))
        btn_tab = AnimatedButton(text="Tab", btn_color=BUTTON_BG, font_size=sp(11))
        btn_tab.bind(on_press=lambda x: self.send_key_action("TAP", "tab"))
        act_row2.add_widget(btn_esc)
        act_row2.add_widget(btn_tab)

        act_row3 = BoxLayout(orientation='horizontal', size_hint_y=0.33, spacing=dp(4))
        btn_sup = AnimatedButton(text="Scroll ^", btn_color=CARD_BG, font_size=sp(10))
        btn_sup.bind(on_press=lambda x: self.send_mouse_cmd("SCROLL", 1, 0))
        btn_sdn = AnimatedButton(text="Scroll v", btn_color=CARD_BG, font_size=sp(10))
        btn_sdn.bind(on_press=lambda x: self.send_mouse_cmd("SCROLL", -1, 0))
        act_row3.add_widget(btn_sup)
        act_row3.add_widget(btn_sdn)

        self.actions_box.add_widget(act_row1)
        self.actions_box.add_widget(act_row2)
        self.actions_box.add_widget(act_row3)
        self.hud_overlay.add_widget(self.actions_box)

        self.root_float.add_widget(self.hud_overlay)
        self.add_widget(self.root_float)

        self.last_trackpad_pos = None

    def toggle_orientation(self, instance=None):
        """Flips between Landscape Gaming Mode and Portrait mode."""
        self.set_landscape(not self.is_landscape)

    def set_landscape(self, landscape=True):
        self.is_landscape = landscape
        self.btn_rotate.text = "Port" if landscape else "Land"
        
        # Native Android orientation control via PyJNIus
        if 'ANDROID_ARGUMENT' in os.environ or 'PYTHON_SERVICE_ARGUMENT' in os.environ:
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                ActivityInfo = autoclass('android.content.pm.ActivityInfo')
                activity = PythonActivity.mActivity
                if activity:
                    if landscape:
                        activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE)
                    else:
                        activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
                    app_log(f"Switched Android orientation: {'LANDSCAPE' if landscape else 'PORTRAIT'}")
            except Exception as e:
                app_log(f"Native orientation error: {e}")
        else:
            # Desktop testing window resizing
            Window.size = (720, 400) if landscape else (400, 720)
            app_log(f"Simulated desktop orientation: {Window.size}")

        Clock.schedule_once(lambda dt: self._update_bg(), 0.1)

    def toggle_touch_mode(self, instance=None):
        if self.touch_mode == "DIRECT":
            self.touch_mode = "TRACKPAD"
            self.btn_mode.text = "Trackpad"
            self.btn_mode.btn_color = ACCENT_SECONDARY
        else:
            self.touch_mode = "DIRECT"
            self.btn_mode.text = "Direct"
            self.btn_mode.btn_color = CARD_BG

    def toggle_hud_visibility(self, instance=None):
        self.hud_visible = not self.hud_visible
        self.hud_overlay.opacity = 1 if self.hud_visible else 0
        self.hud_overlay.disabled = not self.hud_visible
        self.btn_hud_toggle.text = "HUD" if self.hud_visible else "Hide"
        self.btn_hud_toggle.btn_color = ACCENT_PRIMARY if self.hud_visible else CARD_BG

    def toggle_keyboard(self, instance=None):
        try:
            Window.show_keyboard()
            app_log("Keyboard shown")
        except Exception as e:
            app_log(f"Keyboard toggle: {e}")

    def on_enter(self):
        super().on_enter()
        main_screen = self.manager.get_screen('main')
        pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
        if pc_ip:
            self.status_badge.text = f"Live: {pc_ip}"
            self.status_badge.color = SUCCESS
            self.start_video()
        else:
            self.status_badge.text = "Link PC on Home"
            self.status_badge.color = WARNING
            self.start_video()

    def on_leave(self):
        super().on_leave()
        self.stop_video()
        # Always return to portrait orientation when leaving mirror
        if self.is_landscape:
            self.set_landscape(False)

    def go_back(self, instance=None):
        self.stop_video()
        if self.is_landscape:
            self.set_landscape(False)
        self.manager.current = 'main'

    def start_video(self):
        if self._mirror_running:
            return
        main_screen = self.manager.get_screen('main')
        pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
        if not pc_ip:
            self.status_badge.text = "No linked PC found"
            self.status_badge.color = WARNING
            return

        # Send wake UDP handshake to PC
        self._udp_send(pc_ip, 5562, "WAKE_MIRROR\n")
        self._udp_send(pc_ip, 5556, f"WAKE_MIRROR|{PORT_MIRROR_VIDEO}\n")

        self._mirror_running = True
        self.status_badge.text = f"Connecting: {pc_ip}..."
        self.status_badge.color = WARNING
        threading.Thread(target=self._video_loop, args=(pc_ip,), daemon=True).start()

    def stop_video(self):
        self._mirror_running = False
        try:
            if self._mirror_sock:
                self._mirror_sock.close()
        except Exception:
            pass
        self._mirror_sock = None

    def _video_loop(self, pc_ip):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Low latency socket: disable Nagle algorithm & enlarge receive buffer
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
            except Exception:
                pass
            s.settimeout(5.0)
            s.connect((pc_ip, PORT_MIRROR_VIDEO))
            self._mirror_sock = s
            Clock.schedule_once(lambda dt: self._on_connected(pc_ip))
        except Exception as e:
            app_log(f"PC video stream connection failed ({pc_ip}): {e}")
            Clock.schedule_once(lambda dt: setattr(self.status_badge, 'text', "PC Mirror offline"))
            self._mirror_running = False
            return

        try:
            # Read CELJ header (8 bytes)
            hdr = self._recvn(s, 8)
            s.settimeout(8.0)
            while self._mirror_running:
                lb = self._recvn(s, 4)
                if not lb:
                    break
                (ln,) = struct.unpack("!I", lb)
                if ln <= 0 or ln > 8 * 1024 * 1024:
                    break
                jpg = self._recvn(s, ln)
                if not jpg:
                    break

                # Zero-buffering stale frame dropper: store freshest JPEG and trigger render
                self._latest_jpg = jpg
                if not self._render_scheduled:
                    self._render_scheduled = True
                    Clock.schedule_once(self._render_latest_frame, 0)

        except Exception as e:
            app_log(f"Video loop exception: {e}")
        finally:
            try:
                s.close()
            except Exception:
                pass
            self._mirror_running = False

    def _on_connected(self, pc_ip):
        self.status_badge.text = f"Live: {pc_ip}"
        self.status_badge.color = SUCCESS
        self.hint_box.opacity = 0
        self.hint_box.disabled = True

    def _render_latest_frame(self, dt):
        self._render_scheduled = False
        jpg = self._latest_jpg
        if not jpg:
            return
        try:
            from io import BytesIO
            from kivy.core.image import Image as CoreImage
            tex = CoreImage(BytesIO(jpg), ext="jpg").texture
            self.video_img.texture = tex
            if self.video_img.opacity == 0:
                self.video_img.opacity = 1
                self.hint_box.opacity = 0
                self.hint_box.disabled = True

            # Telemetry FPS
            self._fps_counter += 1
            now = time.time()
            if now - self._fps_t0 >= 1.0:
                self._live_fps = self._fps_counter / (now - self._fps_t0)
                main_screen = self.manager.get_screen('main')
                pc_ip = getattr(main_screen, 'discovered_pc_ip', "PC")
                self.status_badge.text = f"{pc_ip} • {self._live_fps:.0f} FPS"
                self._fps_counter = 0
                self._fps_t0 = now
        except Exception:
            pass

    def _recvn(self, s, n):
        buf = b""
        while len(buf) < n and self._mirror_running:
            try:
                c = s.recv(n - len(buf))
            except Exception:
                return None
            if not c:
                return None
            buf += c
        return buf if len(buf) == n else None

    def get_rendered_video_rect(self):
        """Calculates exact mathematical letterboxing boundaries of the 16:9 PC frame."""
        if not self.video_img.texture:
            return (self.video_img.x, self.video_img.y, self.video_img.width, self.video_img.height)
        tw, th = self.video_img.texture.size
        vw, vh = self.video_img.size
        if tw <= 0 or th <= 0 or vw <= 0 or vh <= 0:
            return (self.video_img.x, self.video_img.y, self.video_img.width, self.video_img.height)
        scale = min(vw / float(tw), vh / float(th))
        rw, rh = tw * scale, th * scale
        rx = self.video_img.x + (vw - rw) / 2.0
        ry = self.video_img.y + (vh - rh) / 2.0
        return (rx, ry, rw, rh)

    def on_touch_down(self, touch):
        # Allow top bar and virtual gamepad HUD buttons to process touch first
        if self.top_toolbar.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if self.hud_visible and (self.dpad_box.collide_point(*touch.pos) or self.actions_box.collide_point(*touch.pos)):
            return super().on_touch_down(touch)

        # 1:1 Direct Touch for PC Emulators (LDPlayer, Nox, MuMu)
        if self.touch_mode == "DIRECT":
            rx, ry, rw, rh = self.get_rendered_video_rect()
            if rx <= touch.x <= rx + rw and ry <= touch.y <= ry + rh:
                norm_x = (touch.x - rx) / max(1.0, rw)
                norm_y = 1.0 - ((touch.y - ry) / max(1.0, rh))
                norm_x = max(0.0, min(1.0, norm_x))
                norm_y = max(0.0, min(1.0, norm_y))
                self.send_touch_cmd(touch.id, "DOWN", norm_x, norm_y)
                touch.grab(self)
                return True
        else:
            # Trackpad cursor mode
            self.last_trackpad_pos = (touch.x, touch.y)
            touch.grab(self)
            return True

        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            if self.touch_mode == "DIRECT":
                rx, ry, rw, rh = self.get_rendered_video_rect()
                norm_x = (touch.x - rx) / max(1.0, rw)
                norm_y = 1.0 - ((touch.y - ry) / max(1.0, rh))
                norm_x = max(0.0, min(1.0, norm_x))
                norm_y = max(0.0, min(1.0, norm_y))
                self.send_touch_cmd(touch.id, "MOVE", norm_x, norm_y)
            else:
                if self.last_trackpad_pos:
                    dx = touch.x - self.last_trackpad_pos[0]
                    dy = -(touch.y - self.last_trackpad_pos[1])
                    self.send_mouse_cmd("MOVE_REL", dx * 1.5, dy * 1.5)
                self.last_trackpad_pos = (touch.x, touch.y)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            if self.touch_mode == "DIRECT":
                rx, ry, rw, rh = self.get_rendered_video_rect()
                norm_x = (touch.x - rx) / max(1.0, rw)
                norm_y = 1.0 - ((touch.y - ry) / max(1.0, rh))
                norm_x = max(0.0, min(1.0, norm_x))
                norm_y = max(0.0, min(1.0, norm_y))
                self.send_touch_cmd(touch.id, "UP", norm_x, norm_y)
            else:
                self.last_trackpad_pos = None
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def send_touch_cmd(self, touch_id, action, norm_x, norm_y):
        main_screen = self.manager.get_screen('main')
        pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
        if pc_ip:
            cmd = f"TOUCH|{touch_id}|{action}|{norm_x:.4f}|{norm_y:.4f}\n"
            self._udp_send(pc_ip, 5562, cmd)

    def send_mouse_cmd(self, action, p1, p2):
        main_screen = self.manager.get_screen('main')
        pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
        if pc_ip:
            cmd = f"MOUSE|{action}|{p1}|{p2}\n"
            self._udp_send(pc_ip, 5562, cmd)

    def send_key_action(self, action, key_name):
        main_screen = self.manager.get_screen('main')
        pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
        if pc_ip:
            cmd = f"KEY|{action}|{key_name}\n"
            self._udp_send(pc_ip, 5562, cmd)

    def _udp_send(self, ip, port, msg):
        def _task():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.sendto(msg.encode('utf-8'), (ip, port))
                s.close()
            except Exception:
                pass
        threading.Thread(target=_task, daemon=True).start()


# ── SCREEN 3: FILE & FOLDER TRANSFER SCREEN ───────────────────────────────────

class FileTransferScreen(GlassScreen):
    """Paginated, non-laggy WiFi File & Folder Hub."""
    PAGE_SIZE = 8

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.current_path = "/storage/emulated/0" if os.path.exists("/storage/emulated/0") else VAULT_DIR
        self.current_items = []
        self.page = 1
        self.selected_files = set()
        self.menu_expanded = False

        main_layout = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))

        # 1. Header with Options Menu Button
        header_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(36), spacing=dp(6))
        title = Label(
            text="WiFi File & Folder Hub",
            font_size=sp(16),
            bold=True,
            color=TEXT_PRIMARY,
            outline_color=(0.02, 0.05, 0.03, 1),
            outline_width=dp(1.2),
            size_hint_x=1.0,
            halign='left',
            valign='middle'
        )
        title.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        self.options_btn = AnimatedButton(text="Options", btn_color=CARD_BG, size_hint_x=None, width=dp(75), font_size=sp(12))
        self.options_btn.bind(on_press=self.toggle_options_menu)

        header_row.add_widget(title)
        header_row.add_widget(self.options_btn)
        main_layout.add_widget(header_row)

        # 2. Permission Status Badge
        self.perm_badge = AnimatedButton(text="Checking permissions...", btn_color=BUTTON_BG, size_hint_y=None, height=dp(28), font_size=sp(11))
        self.perm_badge.bind(on_press=self.request_full_storage_permission)
        main_layout.add_widget(self.perm_badge)

        # 3. Receiver status mini card
        recv_card = RoundedCard(orientation='horizontal', padding=dp(8), spacing=dp(8), size_hint_y=None, height=dp(34))
        self.serv_status_lbl = Label(text="WiFi Receiver: ACTIVE (port 5558)", font_size=sp(11), color=SUCCESS, bold=True, halign='left', valign='middle')
        self.serv_status_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        recv_card.add_widget(self.serv_status_lbl)
        main_layout.add_widget(recv_card)

        # 4. Collapsible Options Menu Panel
        self.menu_panel = RoundedCard(orientation='vertical', padding=dp(8), spacing=dp(6), size_hint_y=None, height=dp(0))
        self.menu_panel.opacity = 0

        m_row1 = BoxLayout(orientation='horizontal', spacing=dp(6), size_hint_y=None, height=dp(30))
        btn_sel_all = AnimatedButton(text="Select All", btn_color=CARD_BG, font_size=sp(11))
        btn_sel_all.bind(on_press=self.select_all_page)
        btn_clr_sel = AnimatedButton(text="Clear All", btn_color=CARD_BG, font_size=sp(11))
        btn_clr_sel.bind(on_press=self.clear_selection)
        m_row1.add_widget(btn_sel_all)
        m_row1.add_widget(btn_clr_sel)

        m_row2 = BoxLayout(orientation='horizontal', spacing=dp(6), size_hint_y=None, height=dp(30))
        btn_saf = AnimatedButton(text="Open Folder (SAF)", btn_color=ACCENT_TERTIARY, font_size=sp(11))
        btn_saf.bind(on_press=self.open_saf_folder)
        btn_perm = AnimatedButton(text="Full Access", btn_color=ACCENT_SECONDARY, color=(0.02, 0.10, 0.06, 1), font_size=sp(11))
        btn_perm.bind(on_press=self.request_full_storage_permission)
        m_row2.add_widget(btn_saf)
        m_row2.add_widget(btn_perm)

        self.menu_panel.add_widget(m_row1)
        self.menu_panel.add_widget(m_row2)
        main_layout.add_widget(self.menu_panel)

        # 5. Quick navigation bookmarks
        quick_nav = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(32), spacing=dp(4))
        bookmarks = [
            ("/sdcard", "/storage/emulated/0"),
            ("Downloads", "/storage/emulated/0/Download"),
            ("DCIM", "/storage/emulated/0/DCIM"),
            ("Vault", VAULT_DIR),
        ]
        for b_name, b_path in bookmarks:
            b_btn = AnimatedButton(text=b_name, btn_color=BUTTON_BG, font_size=sp(10))
            b_btn.bind(on_press=lambda inst, p=b_path: self.set_path(p))
            quick_nav.add_widget(b_btn)
        main_layout.add_widget(quick_nav)

        # 6. Current Path + Up button
        path_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(32), spacing=dp(6))
        self.up_btn = AnimatedButton(text="[..] Up", btn_color=ACCENT_TERTIARY, size_hint_x=None, width=dp(65), font_size=sp(11))
        self.up_btn.bind(on_press=self.go_up)
        self.path_lbl = Label(text=self.current_path, font_size=sp(11), color=TEXT_PRIMARY, halign='left', valign='middle')
        self.path_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        path_row.add_widget(self.up_btn)
        path_row.add_widget(self.path_lbl)
        main_layout.add_widget(path_row)

        # 7. Paginated Items Container (inside a glass card for readability!)
        items_card = RoundedCard(orientation='vertical', padding=dp(6), spacing=dp(4), size_hint=(1, 1))
        self.items_container = BoxLayout(orientation='vertical', spacing=dp(4), size_hint=(1, 1))
        items_card.add_widget(self.items_container)
        main_layout.add_widget(items_card)

        # 8. Pagination Controls Row
        page_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(32), spacing=dp(8))
        self.prev_btn = AnimatedButton(text="< Prev", btn_color=BUTTON_BG, size_hint_x=None, width=dp(70), font_size=sp(11))
        self.prev_btn.bind(on_press=self.prev_page)

        self.page_lbl = Label(text="Page 1/1 (0 items)", font_size=sp(11), color=TEXT_PRIMARY, halign='center', valign='middle')

        self.next_btn = AnimatedButton(text="Next >", btn_color=BUTTON_BG, size_hint_x=None, width=dp(70), font_size=sp(11))
        self.next_btn.bind(on_press=self.next_page)

        page_row.add_widget(self.prev_btn)
        page_row.add_widget(self.page_lbl)
        page_row.add_widget(self.next_btn)
        main_layout.add_widget(page_row)

        # 9. Transfer Action Buttons Row
        send_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40), spacing=dp(8))
        self.send_selected_btn = AnimatedButton(text="Send Selected (0)", btn_color=ACCENT_PRIMARY, font_size=sp(13))
        self.send_selected_btn.bind(on_press=self.start_multi_file_send)

        self.send_folder_btn = AnimatedButton(text="Send Folder Intact", btn_color=ACCENT_TERTIARY, font_size=sp(13))
        self.send_folder_btn.bind(on_press=self.start_folder_send)

        send_row.add_widget(self.send_selected_btn)
        send_row.add_widget(self.send_folder_btn)
        main_layout.add_widget(send_row)

        # 10. Progress bar and status label
        self.progress_lbl = Label(text="Ready", font_size=sp(11), color=TEXT_SECONDARY, size_hint_y=None, height=dp(18))
        self.progress_bar = GradientBar(progress=0)
        main_layout.add_widget(self.progress_lbl)
        main_layout.add_widget(self.progress_bar)

        # 11. Bottom Back Button
        back_btn = AnimatedButton(text="Back to Home", btn_color=BUTTON_BG, size_hint_y=None, height=dp(38))
        back_btn.bind(on_press=self.go_back)
        main_layout.add_widget(back_btn)

        self.add_widget(main_layout)

    def on_enter(self):
        super().on_enter()
        self.update_permission_badge()
        self.load_directory()

    def update_permission_badge(self):
        has_perm = self.has_full_file_access()
        if has_perm:
            self.perm_badge.text = "Full File Access Granted (All folders unlocked)"
            self.perm_badge.btn_color = BUTTON_BG
            self.perm_badge.color = SUCCESS
        else:
            self.perm_badge.text = "Full Access Needed (Android 11+) • Tap to Grant"
            self.perm_badge.btn_color = (0.35, 0.15, 0.05, 0.8)
            self.perm_badge.color = WARNING

    def has_full_file_access(self):
        try:
            from jnius import autoclass
            Build = autoclass('android.os.Build$VERSION')
            if Build.SDK_INT >= 30:
                Environment = autoclass('android.os.Environment')
                return bool(Environment.isExternalStorageManager())
            return True
        except Exception:
            return True

    def request_full_storage_permission(self, instance=None):
        try:
            from jnius import autoclass
            Build = autoclass('android.os.Build$VERSION')
            if Build.SDK_INT >= 30:
                Environment = autoclass('android.os.Environment')
                if not Environment.isExternalStorageManager():
                    Intent = autoclass('android.content.Intent')
                    Settings = autoclass('android.provider.Settings')
                    Uri = autoclass('android.net.Uri')
                    PythonActivity = autoclass('org.kivy.android.PythonActivity')
                    intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                    uri = Uri.fromParts("package", PythonActivity.mActivity.getPackageName(), None)
                    intent.setData(uri)
                    PythonActivity.mActivity.startActivity(intent)
        except Exception as e:
            app_log(f"Request full storage error: {e}")

    def open_saf_folder(self, instance=None):
        try:
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            PythonActivity.mActivity.startActivity(intent)
            self.toggle_options_menu(None)
        except Exception as e:
            app_log(f"SAF folder open error: {e}")

    def toggle_options_menu(self, instance):
        self.menu_expanded = not self.menu_expanded
        if self.menu_expanded:
            self.menu_panel.opacity = 1
            self.menu_panel.height = dp(75)
            self.options_btn.text = "Close"
        else:
            self.menu_panel.opacity = 0
            self.menu_panel.height = 0
            self.options_btn.text = "Options"

    def set_path(self, path):
        if os.path.exists(path):
            self.current_path = path
            self.page = 1
            self.load_directory()

    def go_up(self, instance=None):
        parent = os.path.dirname(self.current_path.rstrip("/\\"))
        if parent and os.path.exists(parent):
            self.current_path = parent
            self.page = 1
            self.load_directory()

    def load_directory(self):
        self.path_lbl.text = self.current_path
        self.current_items = []
        try:
            dirs = []
            files = []
            with os.scandir(self.current_path) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    try:
                        is_d = entry.is_dir(follow_symlinks=False)
                        sz = entry.stat().st_size if not is_d else 0
                        item = {"name": entry.name, "path": entry.path, "is_dir": is_d, "size": sz}
                        if is_d:
                            dirs.append(item)
                        else:
                            files.append(item)
                    except OSError:
                        pass
            dirs.sort(key=lambda x: x["name"].lower())
            files.sort(key=lambda x: x["name"].lower())
            self.current_items = dirs + files
        except Exception as e:
            app_log(f"Directory list error: {e}")
            self.current_items = []

        total_pages = max(1, (len(self.current_items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self.page > total_pages:
            self.page = total_pages
        self.render_page()

    def render_page(self):
        self.items_container.clear_widgets()
        total_items = len(self.current_items)
        total_pages = max(1, (total_items + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page_lbl.text = f"Page {self.page}/{total_pages} ({total_items} items)"

        self.prev_btn.disabled = (self.page <= 1)
        self.next_btn.disabled = (self.page >= total_pages)

        start_idx = (self.page - 1) * self.PAGE_SIZE
        page_items = self.current_items[start_idx:start_idx + self.PAGE_SIZE]

        if not page_items:
            empty_row = Label(
                text="This folder is empty.",
                font_size=sp(13),
                color=TEXT_SECONDARY,
                size_hint_y=None,
                height=dp(100),
                halign='center',
                valign='middle'
            )
            empty_row.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
            self.items_container.add_widget(empty_row)
            return

        for item in page_items:
            is_dir = item["is_dir"]
            p = item["path"]
            name = item["name"]
            sz = item["size"]

            is_sel = p in self.selected_files
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(34), spacing=dp(6))

            if is_dir:
                sel_btn = AnimatedButton(text="[DIR]", btn_color=BUTTON_BG, size_hint_x=None, width=dp(44), font_size=sp(10))
                sel_btn.bind(on_press=lambda inst, path=p: self.set_path(path))
            else:
                sel_text = "[X]" if is_sel else "[ ]"
                sel_btn = AnimatedButton(text=sel_text, btn_color=ACCENT_PRIMARY if is_sel else CARD_BG, size_hint_x=None, width=dp(44), font_size=sp(11))
                sel_btn.bind(on_press=lambda inst, path=p: self.toggle_file_selection(path))

            display_name = ("> " if is_dir else "  ") + name
            if len(display_name) > 34:
                display_name = display_name[:34] + "..."
            name_btn = AnimatedButton(
                text=display_name,
                btn_color=BUTTON_BG if not is_sel else (0.1, 0.35, 0.2, 0.8),
                color=TEXT_PRIMARY,
                halign='left',
                font_size=sp(11),
                size_hint_x=1.0
            )
            if is_dir:
                name_btn.bind(on_press=lambda inst, path=p: self.set_path(path))
            else:
                name_btn.bind(on_press=lambda inst, path=p: self.toggle_file_selection(path))

            sz_str = "--" if is_dir else f"{sz // (1024*1024)}M" if sz >= 1024*1024 else f"{sz // 1024}K"
            sz_lbl = Label(text=sz_str, font_size=sp(10), color=TEXT_SECONDARY, size_hint_x=None, width=dp(45), halign='right', valign='middle')

            row.add_widget(sel_btn)
            row.add_widget(name_btn)
            row.add_widget(sz_lbl)
            self.items_container.add_widget(row)

    def prev_page(self, instance):
        if self.page > 1:
            self.page -= 1
            self.render_page()

    def next_page(self, instance):
        total_pages = max(1, (len(self.current_items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self.page < total_pages:
            self.page += 1
            self.render_page()

    def toggle_file_selection(self, path):
        if path in self.selected_files:
            self.selected_files.remove(path)
        else:
            self.selected_files.add(path)
        self.send_selected_btn.text = f"Send Selected ({len(self.selected_files)})"
        self.render_page()

    def select_all_page(self, instance):
        start_idx = (self.page - 1) * self.PAGE_SIZE
        page_items = self.current_items[start_idx:start_idx + self.PAGE_SIZE]
        for it in page_items:
            if not it["is_dir"]:
                self.selected_files.add(it["path"])
        self.send_selected_btn.text = f"Send Selected ({len(self.selected_files)})"
        self.render_page()

    def clear_selection(self, instance):
        self.selected_files.clear()
        self.send_selected_btn.text = "Send Selected (0)"
        self.render_page()

    def go_back(self, instance):
        self.manager.current = 'main'

    def start_multi_file_send(self, instance):
        if not self.selected_files:
            self.progress_lbl.text = "Please select at least one file first!"
            return

        main_screen = self.manager.get_screen('main')
        pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
        if not pc_ip:
            self.progress_lbl.text = "No linked PC! Tap 'TAP TO LINK' on Home first."
            return

        files_to_send = list(self.selected_files)
        self.send_selected_btn.disabled = True
        self.send_folder_btn.disabled = True

        def _task():
            total = len(files_to_send)
            success_count = 0
            for idx, filepath in enumerate(files_to_send):
                filename = os.path.basename(filepath)
                Clock.schedule_once(lambda dt, fn=filename, i=idx+1, t=total: setattr(
                    self.progress_lbl, 'text', f"Sending [{i}/{t}]: {fn}..."
                ))
                ok = self._stream_single_file(pc_ip, filepath, filename)
                if ok:
                    success_count += 1

            Clock.schedule_once(lambda dt, s=success_count, t=total: self.on_batch_complete(s, t))

        threading.Thread(target=_task, daemon=True).start()

    def _stream_single_file(self, pc_ip, filepath, filename):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15.0)
        try:
            sock.connect((pc_ip, PORT_TCP_TRANSFER))
            filesize = os.path.getsize(filepath)
            header = f"FILE_SEND|{filename}|{filesize}\n"
            sock.sendall(header.encode('utf-8'))

            sent_bytes = 0
            last_time = time.time()
            with open(filepath, "rb") as f:
                while sent_bytes < filesize:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    sent_bytes += len(chunk)
                    now = time.time()
                    if now - last_time >= 0.5:
                        pct = int((sent_bytes / filesize) * 100) if filesize > 0 else 0
                        Clock.schedule_once(lambda dt, p=pct, fn=filename: self.update_send_progress(p, fn))
                        last_time = now

            sock.close()
            return True
        except Exception as e:
            app_log(f"Stream error for {filename}: {e}")
            try:
                sock.close()
            except OSError:
                pass
            return False

    def start_folder_send(self, instance):
        if not os.path.isdir(self.current_path):
            self.progress_lbl.text = "Current path is not a valid folder!"
            return

        folder_name = os.path.basename(self.current_path.rstrip("/\\")) or "Phone_Storage"
        main_screen = self.manager.get_screen('main')
        pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
        if not pc_ip:
            self.progress_lbl.text = "No linked PC found! Link PC on Home screen first."
            return

        self.send_selected_btn.disabled = True
        self.send_folder_btn.disabled = True
        self.progress_lbl.text = f"Packaging '{folder_name}' intact into archive..."

        folder_path = self.current_path

        def _task():
            import zipfile
            temp_zip = os.path.join(VAULT_DIR, f".pack_{folder_name}.zip")
            try:
                with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(folder_path):
                        for f in files:
                            full_p = os.path.join(root, f)
                            rel_p = os.path.relpath(full_p, folder_path)
                            try:
                                zf.write(full_p, rel_p)
                            except Exception:
                                pass

                filesize = os.path.getsize(temp_zip)
                Clock.schedule_once(lambda dt: setattr(self.progress_lbl, 'text', f"Streaming folder '{folder_name}' ({filesize // (1024*1024)} MB)..."))

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(30.0)
                sock.connect((pc_ip, PORT_TCP_TRANSFER))
                header = f"FOLDER_SEND|{folder_name}|{filesize}\n"
                sock.sendall(header.encode('utf-8'))

                sent_bytes = 0
                last_time = time.time()
                with open(temp_zip, "rb") as f:
                    while sent_bytes < filesize:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        sock.sendall(chunk)
                        sent_bytes += len(chunk)
                        now = time.time()
                        if now - last_time >= 0.5:
                            pct = int((sent_bytes / filesize) * 100) if filesize > 0 else 0
                            Clock.schedule_once(lambda dt, p=pct, fn=folder_name: self.update_send_progress(p, f"Folder: {fn}"))
                            last_time = now

                sock.close()
                try:
                    os.remove(temp_zip)
                except OSError:
                    pass
                Clock.schedule_once(lambda dt: self.on_folder_complete(True, f"Folder '{folder_name}' sent intact to PC!"))
            except Exception as e:
                try:
                    if os.path.exists(temp_zip):
                        os.remove(temp_zip)
                except OSError:
                    pass
                Clock.schedule_once(lambda dt, err=str(e): self.on_folder_complete(False, f"Folder send failed: {err}"))

        threading.Thread(target=_task, daemon=True).start()

    def update_send_progress(self, percent, name=""):
        self.progress_bar.progress = percent
        self.progress_lbl.text = f"Sending '{name}' | {percent}%"

    def on_batch_complete(self, success_count, total):
        self.send_selected_btn.disabled = False
        self.send_folder_btn.disabled = False
        self.progress_bar.progress = 100 if success_count == total else 50
        self.progress_lbl.text = f"Finished: {success_count}/{total} files sent successfully!"
        self.selected_files.clear()
        self.send_selected_btn.text = "Send Selected (0)"
        self.render_page()

    def on_folder_complete(self, success, msg):
        self.send_selected_btn.disabled = False
        self.send_folder_btn.disabled = False
        self.progress_bar.progress = 100 if success else 0
        self.progress_lbl.text = msg


# ── SCREEN 4: SYSTEM LOGS SCREEN ──────────────────────────────────────────────

class LogsScreen(GlassScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(10))

        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(38), spacing=dp(8))
        title = Label(
            text="Live System Logs",
            font_size=sp(17),
            bold=True,
            color=TEXT_PRIMARY,
            outline_color=(0.02, 0.05, 0.03, 1),
            outline_width=dp(1.2),
            size_hint_x=1.0,
            halign='left',
            valign='middle'
        )
        title.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        self.copy_btn = AnimatedButton(text="Copy", btn_color=ACCENT_PRIMARY, size_hint_x=None, width=dp(70))
        self.copy_btn.bind(on_press=self.copy_logs)

        refresh_btn = AnimatedButton(text="Refresh", btn_color=ACCENT_TERTIARY, size_hint_x=None, width=dp(70))
        refresh_btn.bind(on_press=lambda x: self.load_logs())

        header.add_widget(title)
        header.add_widget(self.copy_btn)
        header.add_widget(refresh_btn)
        layout.add_widget(header)

        card = RoundedCard(orientation='vertical', padding=dp(10))
        self.scroll = ScrollView()
        self.log_label = Label(text="Loading system logs...", font_size=sp(11), color=TEXT_PRIMARY, size_hint_y=None, halign='left', valign='top')
        self.log_label.bind(width=lambda inst, val: setattr(inst, 'text_size', (val, None)))
        self.log_label.bind(texture_size=lambda inst, val: setattr(inst, 'height', val[1]))
        self.scroll.add_widget(self.log_label)
        card.add_widget(self.scroll)
        layout.add_widget(card)

        btn_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(42), spacing=dp(10))
        clear_btn = AnimatedButton(text="Clear Logs", btn_color=ERROR)
        clear_btn.bind(on_press=self.clear_logs)
        back_btn = AnimatedButton(text="Back to Home", btn_color=BUTTON_BG)
        back_btn.bind(on_press=self.go_back)
        btn_row.add_widget(clear_btn)
        btn_row.add_widget(back_btn)
        layout.add_widget(btn_row)

        self.add_widget(layout)

    def go_back(self, instance):
        self.manager.current = 'main'

    def on_enter(self):
        super().on_enter()
        self.load_logs()

    def copy_logs(self, instance=None):
        try:
            from kivy.core.clipboard import Clipboard
            text = self.log_label.text
            Clipboard.copy(text)
            self.copy_btn.text = "Copied!"
            Clock.schedule_once(lambda dt: setattr(self.copy_btn, 'text', 'Copy'), 1.5)
        except Exception as e:
            app_log(f"Failed to copy logs: {e}")

    def load_logs(self):
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r") as f:
                    self.log_label.text = f.read().strip() or "Log file is empty."
            else:
                self.log_label.text = "No log file found."
        except OSError as e:
            self.log_label.text = f"Error reading logs: {e}"

    def clear_logs(self, instance):
        try:
            with open(LOG_FILE, "w") as f:
                f.write("")
            self.log_label.text = "Logs cleared successfully."
        except OSError as e:
            self.log_label.text = f"Failed to clear logs: {e}"


# ── SCREEN 5: SETTINGS SCREEN ─────────────────────────────────────────────────

class SettingsScreen(GlassScreen):
    """Full-featured, responsive, persistent Settings Screen."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root_box = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(10))

        title = Label(
            text="App Configuration",
            font_size=sp(18),
            bold=True,
            color=TEXT_PRIMARY,
            outline_color=(0.02, 0.05, 0.03, 1),
            outline_width=dp(1.2),
            size_hint_y=None,
            height=dp(32)
        )
        root_box.add_widget(title)

        scroll = ScrollView(size_hint=(1, 1))
        content = BoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        card = RoundedCard(orientation='vertical', padding=dp(14), spacing=dp(10), size_hint_y=None)
        card.bind(minimum_height=card.setter('height'))

        # Logging Switch
        log_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(38))
        log_layout.add_widget(Label(text="Enable Session Logging", color=TEXT_PRIMARY, font_size=sp(14), halign='left', size_hint_x=0.7))
        self.log_switch = Switch(active=config.get("logging_enabled", True))
        self.log_switch.bind(active=self.on_log_switch)
        log_layout.add_widget(self.log_switch)
        card.add_widget(log_layout)

        # Port Spinners
        self.add_port_spinner(card, "Heartbeat Port (Phone -> PC)", "heartbeat_port")
        self.add_port_spinner(card, "Discovery Port (PC Broadcast)", "discovery_port")
        self.add_port_spinner(card, "scrcpy ADB Port", "adb_port")

        # Liquid Glass Opacity Slider
        glass_val = float(config.get("glass_opacity", 0.40))
        self.glass_lbl = Label(text=f"Liquid Glass Opacity: {int(glass_val * 100)}%", color=TEXT_PRIMARY, font_size=sp(13), halign='left', size_hint_y=None, height=dp(20))
        self.glass_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        glass_slider = Slider(min=0.10, max=0.90, value=glass_val, step=0.01, size_hint_y=None, height=dp(32))
        glass_slider.bind(value=self.on_glass_slider)
        card.add_widget(self.glass_lbl)
        card.add_widget(glass_slider)

        # Wallpaper Dark Tint Slider
        tint_val = float(config.get("wallpaper_tint_opacity", 0.40))
        self.tint_lbl = Label(text=f"Wallpaper Dark Tint: {int(tint_val * 100)}%", color=TEXT_PRIMARY, font_size=sp(13), halign='left', size_hint_y=None, height=dp(20))
        self.tint_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        tint_slider = Slider(min=0.10, max=0.90, value=tint_val, step=0.01, size_hint_y=None, height=dp(32))
        tint_slider.bind(value=self.on_tint_slider)
        card.add_widget(self.tint_lbl)
        card.add_widget(tint_slider)

        # Wallpaper Fit Mode Spinner
        fit_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40))
        fit_lbl = Label(text="Wallpaper Fit Mode", color=TEXT_PRIMARY, font_size=sp(13), halign='left', size_hint_x=0.6)
        fit_lbl.bind(size=fit_lbl.setter('text_size'))
        fit_box.add_widget(fit_lbl)
        self.fit_spinner = Spinner(
            text=config.get("wallpaper_fit", "Stretch"),
            values=["Stretch", "Zoom"],
            background_color=INPUT_BG,
            color=TEXT_PRIMARY,
            size_hint_x=0.4
        )
        self.fit_spinner.bind(text=self.on_fit_change)
        fit_box.add_widget(self.fit_spinner)
        card.add_widget(fit_box)

        # Version Badge
        ver_lbl = Label(
            text=f"CelSuite Mobile • Version v{VERSION}",
            color=ACCENT_SECONDARY,
            font_size=sp(12),
            bold=True,
            halign='center',
            size_hint_y=None,
            height=dp(24)
        )
        card.add_widget(ver_lbl)

        content.add_widget(card)
        scroll.add_widget(content)
        root_box.add_widget(scroll)

        back_btn = AnimatedButton(text="Save & Return", btn_color=ACCENT_PRIMARY, font_size=sp(15), size_hint_y=None, height=dp(44))
        back_btn.bind(on_press=self.go_back)
        root_box.add_widget(back_btn)

        self.add_widget(root_box)

    def on_fit_change(self, instance, text):
        config["wallpaper_fit"] = text
        save_config(config)
        if self.manager:
            for s in self.manager.screens:
                if hasattr(s, '_update_bg'):
                    s._update_bg()

    def on_glass_slider(self, instance, value):
        self.glass_lbl.text = f"Liquid Glass Opacity: {int(value * 100)}%"
        config["glass_opacity"] = round(value, 2)
        save_config(config)
        global GLASS_OPACITY, CARD_BG, BUTTON_BG
        GLASS_OPACITY = round(value, 2)
        CARD_BG = (0.05, 0.13, 0.09, max(0.40, GLASS_OPACITY))
        BUTTON_BG = (0.07, 0.18, 0.12, max(0.45, GLASS_OPACITY))
        for c in _active_cards:
            try:
                c.refresh_theme()
            except Exception:
                pass

    def on_tint_slider(self, instance, value):
        self.tint_lbl.text = f"Wallpaper Dark Tint: {int(value * 100)}%"
        config["wallpaper_tint_opacity"] = round(value, 2)
        save_config(config)
        if self.manager:
            for s in self.manager.screens:
                if hasattr(s, 'update_tint'):
                    s.update_tint(value)

    def go_back(self, instance):
        self.manager.current = 'main'

    def add_port_spinner(self, layout, label_text, config_key):
        box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40))
        lbl = Label(text=label_text, color=TEXT_PRIMARY, font_size=sp(12), halign='left', size_hint_x=0.65)
        lbl.bind(size=lbl.setter('text_size'))
        box.add_widget(lbl)
        spinner = Spinner(
            text=str(config.get(config_key, 5555)),
            values=[str(p) for p in range(5550, 5565)],
            background_color=INPUT_BG,
            color=TEXT_PRIMARY,
            size_hint_x=0.35
        )
        spinner.bind(text=lambda instance, text: self.on_port_change(config_key, text))
        box.add_widget(spinner)
        layout.add_widget(box)

    def on_log_switch(self, instance, value):
        config["logging_enabled"] = value
        save_config(config)

    def on_port_change(self, key, value):
        try:
            config[key] = int(value)
            save_config(config)
        except ValueError:
            pass


# ── SCREEN 6: SETUP MANUAL (HELP) SCREEN ──────────────────────────────────────

class HelpScreen(GlassScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))

        title = Label(
            text="Help & Setup Manual",
            color=TEXT_PRIMARY,
            outline_color=(0.02, 0.05, 0.03, 1),
            outline_width=dp(1.2),
            font_size=sp(18),
            bold=True,
            size_hint_y=None,
            height=dp(36)
        )
        layout.add_widget(title)

        card = RoundedCard(orientation='vertical', padding=dp(14))
        scroll = ScrollView()
        content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10))
        content.bind(minimum_height=content.setter('height'))

        guide_text = (
            f"[b]CelSuite - Peer2Peer Screen Mirror v{VERSION}[/b]\n\n"
            "[b]1. Quick Launch Instructions:[/b]\n"
            "• Link your phone and PC to the same WiFi or hotspot.\n"
            "• Open the PC CelSuite app, then open this app on your phone.\n"
            "• Peer-to-peer screen mirroring starts automatically!\n\n"
            "[b]2. Shizuku Wireless Setup:[/b]\n"
            "• For rootless wireless ADB, execute in Termux / Shizuku:\n"
            "  [color=10B981]rish -c 'adb tcpip 5555'[/color]\n\n"
            "[b]3. Watch PC (Screen Mirroring):[/b]\n"
            "• Tap 'Watch PC' to stream your PC screen live to your phone.\n"
            "• Full touch gestures and mouse shortcuts are supported!\n\n"
            "[b]4. WiFi File & Folder Hub:[/b]\n"
            "• Multi-megabyte peer-to-peer TCP transfers over port 5558.\n"
            "• Select multiple files or send whole folders intact.\n\n"
            "[b]5. Bidirectional Clipboard Sync:[/b]\n"
            "• Copy on PC, paste on phone — or vice versa automatically!"
        )

        guide_label = Label(text=guide_text, markup=True, color=TEXT_PRIMARY, font_size=sp(13), halign='left', valign='top', size_hint_y=None)
        guide_label.bind(width=lambda inst, val: setattr(inst, 'text_size', (val, None)))
        guide_label.bind(texture_size=lambda inst, val: setattr(inst, 'height', val[1]))

        content.add_widget(guide_label)
        scroll.add_widget(content)
        card.add_widget(scroll)
        layout.add_widget(card)

        back_btn = AnimatedButton(text="Back to Home", btn_color=BUTTON_BG, font_size=sp(15), size_hint_y=None, height=dp(44))
        back_btn.bind(on_press=self.go_back)
        layout.add_widget(back_btn)

        self.add_widget(layout)

    def go_back(self, instance):
        self.manager.current = 'main'


# ── SCREEN 7: FILE VAULT SCREEN ───────────────────────────────────────────────

class VaultScreen(GlassScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))

        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(38))
        title = Label(
            text="Downloaded Vault",
            color=TEXT_PRIMARY,
            outline_color=(0.02, 0.05, 0.03, 1),
            outline_width=dp(1.2),
            font_size=sp(18),
            bold=True,
            size_hint_x=1.0,
            halign='left'
        )
        title.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        refresh_btn = AnimatedButton(text="Refresh", btn_color=ACCENT_TERTIARY, size_hint_x=None, width=dp(80))
        refresh_btn.bind(on_press=lambda x: self.refresh_vault())

        header.add_widget(title)
        header.add_widget(refresh_btn)
        layout.add_widget(header)

        self.card = RoundedCard(orientation='vertical', padding=dp(10))
        self.scroll = ScrollView()
        self.file_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(6))
        self.file_list.bind(minimum_height=self.file_list.setter('height'))

        self.empty_label = Label(
            text="No files in Vault yet.\nSend files or folders from your PC over WiFi to store them here!",
            color=TEXT_SECONDARY,
            font_size=sp(13),
            halign='center',
            valign='middle',
            size_hint_y=None,
            height=dp(150)
        )
        self.empty_label.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        self.file_list.add_widget(self.empty_label)

        self.scroll.add_widget(self.file_list)
        self.card.add_widget(self.scroll)
        layout.add_widget(self.card)

        back_btn = AnimatedButton(text="Back to Home", btn_color=BUTTON_BG, font_size=sp(15), size_hint_y=None, height=dp(44))
        back_btn.bind(on_press=self.go_back)
        layout.add_widget(back_btn)

        self.add_widget(layout)

    def go_back(self, instance):
        self.manager.current = 'main'

    def on_enter(self):
        super().on_enter()
        self.refresh_vault()

    def refresh_vault(self):
        self.file_list.clear_widgets()
        try:
            files = sorted(os.listdir(VAULT_DIR))
            received_files = [f for f in files if os.path.isfile(os.path.join(VAULT_DIR, f)) and not f.startswith(".")]

            if not received_files:
                self.file_list.add_widget(self.empty_label)
                return

            for filename in received_files:
                filepath = os.path.join(VAULT_DIR, filename)
                size = os.path.getsize(filepath)

                row = RoundedCard(orientation='horizontal', size_hint_y=None, height=dp(48), padding=dp(8), spacing=dp(8))

                name_label = Label(text=filename, color=TEXT_PRIMARY, font_size=sp(13), halign='left')
                name_label.bind(width=lambda i, v: setattr(i, 'text_size', (v, None)))

                size_label = Label(
                    text=f"{size / (1024*1024):.1f}M" if size >= 1024*1024 else f"{size/1024:.1f}K",
                    color=TEXT_SECONDARY,
                    font_size=sp(11),
                    size_hint_x=None,
                    width=dp(50)
                )

                share_btn = AnimatedButton(text="Share", btn_color=ACCENT_SECONDARY, color=(0.02, 0.10, 0.06, 1), size_hint_x=None, width=dp(65), font_size=sp(11))
                share_btn.bind(on_press=lambda btn, path=filepath: self.share_file(path))

                row.add_widget(name_label)
                row.add_widget(size_label)
                row.add_widget(share_btn)
                self.file_list.add_widget(row)
        except OSError as e:
            app_log(f"Vault refresh failed: {e}")

    def share_file(self, file_path):
        try:
            import mimetypes
            from jnius import autoclass, cast
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            File = autoclass('java.io.File')
            context = PythonActivity.mActivity
            file_obj = File(file_path)
            mime, _ = mimetypes.guess_type(file_path)
            mime = mime or "*/*"
            uri = None
            try:
                FileProvider = autoclass('androidx.core.content.FileProvider')
                authority = context.getPackageName() + ".fileprovider"
                uri = FileProvider.getUriForFile(context, authority, file_obj)
            except Exception:
                Uri = autoclass('android.net.Uri')
                uri = Uri.fromFile(file_obj)
            intent = Intent(Intent.ACTION_SEND)
            intent.setType(mime)
            intent.putExtra(Intent.EXTRA_STREAM, cast('android.os.Parcelable', uri))
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            chooser = Intent.createChooser(intent, "Share File via:")
            chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(chooser)
        except Exception as e:
            app_log(f"Share trigger failed: {e}")


# ── APPLICATION ROOT ──────────────────────────────────────────────────────────

class HeartbeatApp(App):
    """The main application class for CelSuite Mobile."""
    title = "CelSuite — P2P Screen Mirror"
    icon = "icon_mobile.png"

    def build(self):
        Window.bind(on_keyboard=self.on_keyboard)

        # Android runtime permissions
        try:
            from android.permissions import request_permissions, Permission
            try:
                from jnius import autoclass as _ac
                _sdk = int(str(_ac('android.os.Build$VERSION').SDK_INT))
            except Exception:
                _sdk = 33
            if _sdk >= 33:
                try:
                    _perms = [Permission.READ_MEDIA_IMAGES, Permission.READ_MEDIA_VIDEO, Permission.READ_MEDIA_AUDIO]
                except AttributeError:
                    _perms = [Permission.READ_EXTERNAL_STORAGE]
            else:
                _perms = [Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE]
            request_permissions(_perms)
            app_log("Requested Storage permissions from OS.")
        except Exception as e:
            app_log(f"Permissions setup: {e}")

        app_log(f"Storage mode: {'External (/sdcard)' if CAN_WRITE_EXTERNAL else 'Internal App Data'}")
        app_log(f"Log path: {LOG_FILE}")

        # Start background TCP File Server
        server = TCPFileServerThread()
        server.start()

        # Instant 0ms transition between screens — eliminates ghosting and lag!
        self.root_sm = ScreenManager(transition=NoTransition())
        self.root_sm.add_widget(MainScreen(name='main'))
        self.root_sm.add_widget(PCMirrorScreen(name='pc_mirror'))
        self.root_sm.add_widget(FileTransferScreen(name='transfer'))
        self.root_sm.add_widget(VaultScreen(name='vault'))
        self.root_sm.add_widget(LogsScreen(name='logs'))
        self.root_sm.add_widget(SettingsScreen(name='settings'))
        self.root_sm.add_widget(HelpScreen(name='help'))

        # Clipboard Broadcast receiver on Android
        try:
            from android.broadcast import BroadcastReceiver

            def on_clipboard_intent(context, intent):
                action = intent.getAction()
                if action in ("henryjayz.celsuite.scrcpyheartbeat.SET_CLIPBOARD", "org.henry.scrcpy.SET_CLIPBOARD"):
                    txt = intent.getStringExtra("text")
                    if txt:
                        self.set_local_clipboard(txt)
                elif action in ("henryjayz.celsuite.scrcpyheartbeat.GET_CLIPBOARD", "org.henry.scrcpy.GET_CLIPBOARD"):
                    self.send_local_clipboard_to_pc()
                elif action in ("henryjayz.celsuite.scrcpyheartbeat.TOGGLE_HEARTBEAT", "org.henry.scrcpy.TOGGLE_HEARTBEAT"):
                    active = intent.getBooleanExtra("active", True)
                    self.handle_tile_toggle(active)

            receiver = BroadcastReceiver(
                on_clipboard_intent,
                actions=[
                    "henryjayz.celsuite.scrcpyheartbeat.SET_CLIPBOARD",
                    "henryjayz.celsuite.scrcpyheartbeat.GET_CLIPBOARD",
                    "henryjayz.celsuite.scrcpyheartbeat.TOGGLE_HEARTBEAT",
                    "org.henry.scrcpy.SET_CLIPBOARD",
                    "org.henry.scrcpy.GET_CLIPBOARD",
                    "org.henry.scrcpy.TOGGLE_HEARTBEAT",
                ]
            )
            receiver.start()
            app_log("System BroadcastReceiver registered.")
        except Exception as e:
            app_log(f"System receiver bind: {e}")

        return self.root_sm

    def on_keyboard(self, window, key, scancode, codepoint, modifier):
        # 27 is Android hardware Back button / PC Esc key
        if key == 27:
            if self.root_sm and self.root_sm.current != 'main':
                self.root_sm.current = 'main'
                return True
        return False

    def set_local_clipboard(self, text):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(text)
            app_log(f"Updated local clipboard: '{text[:40]}...'")
        except Exception as e:
            app_log(f"Failed to set local clipboard: {e}")

    def send_local_clipboard_to_pc(self):
        try:
            from kivy.core.clipboard import Clipboard
            text = Clipboard.paste() or ""
            if not text:
                return
            main_screen = self.root_sm.get_screen('main')
            pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
            if pc_ip:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                msg = f"CLIPBOARD|{text}"
                s.sendto(msg.encode('utf-8'), (pc_ip, 5556))
                s.close()
        except Exception as e:
            app_log(f"Failed to send local clipboard: {e}")

    def handle_tile_toggle(self, active):
        main_screen = self.root_sm.get_screen('main')
        if active:
            main_screen._start_services()
        else:
            main_screen.stop_heartbeat()


if __name__ == '__main__':
    HeartbeatApp().run()
