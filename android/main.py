import os
import sys
import time
import socket
import threading
import json
import subprocess
import traceback
import random

# Samsung JNI and Modified UTF-8 sensor workarounds
os.environ['SDL_SENSOR_DRIVER'] = 'dummy'
os.environ['KIVY_NO_ARGS'] = '1'

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.switch import Switch
from kivy.uix.spinner import Spinner
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
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

if 'ANDROID_ARGUMENT' not in os.environ and 'PYTHON_SERVICE_ARGUMENT' not in os.environ:
    Window.size = (400, 720)

# Port configuration
PORT_TCP_TRANSFER = 5558

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
            # Calling getExternalFilesDir(None) automatically creates /sdcard/Android/data/<pkg>/files
            ext_files = activity.getExternalFilesDir(None)
            if ext_files:
                external_data_dir = ext_files.getAbsolutePath()
    except Exception as exc:
        print(f"Failed to query Android context: {exc}")

    # Prefer /sdcard/Android/data/<pkg>/files so user can easily access config/logs/vault
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
        "glass_opacity": 0.33,
        "wallpaper_tint_opacity": 0.33,
        "wallpaper_fit": "Stretch",
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            for k, v in defaults.items():
                if k not in config: config[k] = v
            return config
    except OSError as e:
        print(f"Config load failed: {e}")
    except json.JSONDecodeError as e:
        print(f"Config parse failed: {e}")
    return defaults

def save_config(config):
    """Saves the application configuration to JSON."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except OSError as e:
        print(f"Config save failed: {e}")

config = load_config()

# CelStudio Emerald Green Liquid Glass Palette (33% default opacity)
GLASS_OPACITY = float(config.get("glass_opacity", 0.33))
WALLPAPER_TINT = float(config.get("wallpaper_tint_opacity", 0.33))

DARK_BG = (0.04, 0.08, 0.06, 1)
PRIMARY_BG = (0.05, 0.11, 0.08, 1)
SECONDARY_BG = (0.07, 0.14, 0.10, 1)
CARD_BG = (0.07, 0.16, 0.11, GLASS_OPACITY)
INPUT_BG = (0.05, 0.12, 0.08, 0.50)
BUTTON_BG = (0.08, 0.20, 0.13, GLASS_OPACITY)

ACCENT_PRIMARY = (0.063, 0.725, 0.506, 1)     # #10B981 Emerald
ACCENT_SECONDARY = (0.204, 0.827, 0.600, 1)   # #34D399 Light Mint
ACCENT_TERTIARY = (0.078, 0.722, 0.651, 1)    # #14B8A6 Teal
ACCENT_GLOW = (0.431, 0.906, 0.718, 1)        # #6EE7B7 Neon Glow

TEXT_PRIMARY = (0.94, 0.98, 0.95, 1)
TEXT_SECONDARY = (0.60, 0.72, 0.65, 1)
TEXT_ON_ACCENT = (0.02, 0.10, 0.06, 1)

SUCCESS = (0.063, 0.725, 0.506, 1)
WARNING = (0.961, 0.620, 0.043, 1)
ERROR = (0.937, 0.267, 0.267, 1)

BORDER_SUBTLE = (0.063, 0.725, 0.506, 0.40)

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

def enable_shizuku_wireless_adb():
    """Attempts to enable wireless ADB via Shizuku API, then falls back to root."""
    app_log("Starting Shizuku/Root wireless ADB trigger...")
    adb_cmd = "setprop service.adb.tcp.port 5555; setprop persist.adb.tcp.port 5555; setprop service.adb.tcp.bind 0.0.0.0; stop adbd && start adbd"
    
    # Method 1: Shizuku API (proper SDK integration)
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
            process = Shizuku.newProcess(
                ["sh", "-c", adb_cmd], None, None
            )
            exit_code = process.waitFor()
            app_log(f"Shizuku API: wireless ADB enabled! (exit={exit_code})")
            return
    except Exception as e:
        app_log(f"Shizuku API failed: {e}")
    
    # Method 2: Root (su) via JNI
    try:
        from jnius import autoclass
        Runtime = autoclass('java.lang.Runtime')
        process = Runtime.getRuntime().exec(["su", "-c", adb_cmd])
        process.waitFor()
        app_log("Root trigger successful via JNI Runtime")
        return
    except Exception as e:
        app_log(f"Root failed: {e}")
    
    app_log("All ADB trigger methods exhausted. User needs Shizuku or root.")

# --- CUSTOM WIDGET CLASSES ---

class RoundedCard(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*CARD_BG)
            self.rect = RoundedRectangle(radius=[dp(12)])
            Color(*BORDER_SUBTLE)
            self.border = Line(width=1.2)
        self.bind(pos=self.update_canvas, size=self.update_canvas)
        
    def update_canvas(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size
        self.border.rounded_rectangle = [self.x, self.y, self.width, self.height, dp(12)]

class AnimatedButton(Button):
    scale_value = NumericProperty(1.0)
    
    def __init__(self, **kwargs):
        kwargs.setdefault('background_normal', '')
        kwargs.setdefault('background_down', '')
        kwargs.setdefault('background_color', (0, 0, 0, 0)) # transparent so we draw custom bg
        self.btn_color = kwargs.pop('btn_color', ACCENT_PRIMARY)
        if self.btn_color == ACCENT_PRIMARY:
            kwargs.setdefault('color', TEXT_ON_ACCENT)
        else:
            kwargs.setdefault('color', (1, 1, 1, 1)) # Bright crisp white for visible text!
        kwargs.setdefault('font_size', sp(15))
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
            Color(*self.btn_color)
            self.bg_rect = RoundedRectangle(radius=[dp(16)])
            Color(*BORDER_SUBTLE)
            self.border_line = Line(width=1.2)
            
        self.bind(pos=self.update_canvas, size=self.update_canvas)

        icon_lbl = Label(text=icon, font_size=sp(20), bold=True, size_hint_y=0.45, halign='center', valign='middle', color=ACCENT_PRIMARY)
        icon_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        title_lbl = Label(text=title, font_size=sp(14), bold=True, size_hint_y=0.35, halign='center', valign='middle', color=TEXT_PRIMARY)
        title_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        sub_lbl = Label(text=subtitle, font_size=sp(11), size_hint_y=0.2, halign='center', valign='middle', color=TEXT_SECONDARY)
        sub_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        self.add_widget(icon_lbl)
        self.add_widget(title_lbl)
        self.add_widget(sub_lbl)

    def update_canvas(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.border_line.rounded_rectangle = [self.x, self.y, self.width, self.height, dp(16)]

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
        kwargs.setdefault('height', dp(60))
        kwargs.setdefault('size_hint_x', None)
        kwargs.setdefault('width', dp(60))
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
        self.radius = dp(10)
        self.alpha = 0.8
        anim = Animation(radius=dp(25), alpha=0, duration=1.0, t='out_quad')
        anim.start(self)

    def set_state(self, connected):
        self.is_connected = connected

class GradientBar(Widget):
    progress = NumericProperty(0) # 0 to 100
    
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

class ColoredBoxLayout(BoxLayout):
    """BoxLayout with a customizable background color."""
    def __init__(self, bg_color=DARK_BG, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*bg_color)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)
    
    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

class SlopButton(Button):
    """Button that cancels touch if dragged beyond a threshold."""
    touch_slop = dp(25)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._touch_start_pos = None
        self._touch_cancelled = False
    
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._touch_start_pos = touch.pos
            self._touch_cancelled = False
            touch.grab(self)
        return super().on_touch_down(touch)
    
    def on_touch_move(self, touch):
        if touch.grab_current is self and self._touch_start_pos:
            dx = abs(touch.x - self._touch_start_pos[0])
            dy = abs(touch.y - self._touch_start_pos[1])
            if max(dx, dy) > self.touch_slop:
                touch.ungrab(self)
                self.state = 'normal'
                self._touch_cancelled = True
                self._touch_start_pos = None
        return super().on_touch_move(touch)
    
    def on_touch_up(self, touch):
        if self._touch_cancelled:
            self._touch_cancelled = False
            self._touch_start_pos = None
            return True
        self._touch_start_pos = None
        return super().on_touch_up(touch)


class TCPFileServerThread(threading.Thread):
    """Dedicated background thread for handling incoming TCP file transfers."""
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.sock = None

    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("0.0.0.0", PORT_TCP_TRANSFER))
            self.sock.listen(1)
            app_log(f"Mobile TCP Server active on port {PORT_TCP_TRANSFER}")
        except Exception as e:
            app_log(f"Mobile TCP Server bind error: {e}")
            return

        while True:
            try:
                conn, addr = self.sock.accept()
                self._handle_client(conn, addr[0])
            except Exception as e:
                time.sleep(1)

    def _handle_client(self, conn, ip):
        try:
            conn.settimeout(15.0)
            header_bytes = b""
            while b"\n" not in header_bytes:
                c = conn.recv(1)
                if not c:
                    break
                header_bytes += c
            
            if not header_bytes:
                conn.close()
                return
            
            header = header_bytes.decode('utf-8', errors='ignore').strip()
            
            if header == "FILE_LIST":
                files_data = []
                for f in os.listdir(VAULT_DIR):
                    p = os.path.join(VAULT_DIR, f)
                    if os.path.isfile(p):
                        files_data.append({"name": f, "size": os.path.getsize(p)})
                conn.sendall((json.dumps(files_data) + "\n").encode('utf-8'))
                conn.close()
                return
                
            elif header.startswith("FILE_GET|"):
                parts = header.split('|')
                fname = parts[1]
                filepath = os.path.join(VAULT_DIR, fname)
                if os.path.exists(filepath):
                    filesize = os.path.getsize(filepath)
                    conn.sendall(f"FILE_SEND|{fname}|{filesize}\n".encode('utf-8'))
                    with open(filepath, "rb") as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk: break
                            conn.sendall(chunk)
                conn.close()
                return
                
            elif header.startswith("FILE_SEND|"):
                parts = header.split('|')
                filename = parts[1]
                filesize = int(parts[2])
                
                app_log(f"Receiving '{filename}' ({filesize} bytes)...")
                filepath = os.path.join(VAULT_DIR, filename)
                
                received_bytes = 0
                start_time = time.time()
                last_progress_time = start_time
                last_bytes = 0
                
                app = App.get_running_app()
                transfer_screen = app.root.get_screen('transfer') if app and app.root else None
                
                with open(filepath, "wb") as f:
                    while received_bytes < filesize:
                        to_read = min(65536, filesize - received_bytes)
                        chunk = conn.recv(to_read)
                        if not chunk:
                            raise Exception("Disconnected")
                        f.write(chunk)
                        received_bytes += len(chunk)
                        
                        now = time.time()
                        if now - last_progress_time >= 0.5:
                            dt = now - last_progress_time
                            delta = received_bytes - last_bytes
                            speed = (delta / dt) / (1024 * 1024) if dt > 0 else 0
                            percent = int((received_bytes / filesize) * 100) if filesize > 0 else 0
                            eta = (filesize - received_bytes) / (delta / dt) if delta > 0 else 0
                            
                            if transfer_screen:
                                transfer_screen.update_progress_from_server(percent, speed, eta, filename)
                            
                            last_bytes = received_bytes
                            last_progress_time = now
                
                conn.close()
                app_log(f"Successfully received '{filename}'")
                if transfer_screen:
                    transfer_screen.on_server_transfer_complete(True, filename)
        except Exception as e:
            try:
                conn.close()
            except OSError:
                pass
            app_log(f"TCP server receive error: {e}")
            app = App.get_running_app()
            transfer_screen = app.root.get_screen('transfer') if app and app.root else None
            if transfer_screen:
                transfer_screen.on_server_transfer_complete(False, str(e))

class ParticleBackground(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.particles = []
        Clock.schedule_interval(self.update_particles, 1/30)
        
    def update_particles(self, dt):
        if not self.canvas: return
        if random.random() < 0.1 and len(self.particles) < 40:
            p = {
                'x': random.uniform(self.x, self.right),
                'y': self.y - dp(10),
                'speed': random.uniform(dp(20), dp(50)),
                'size': random.uniform(dp(3), dp(8)),
                'alpha': random.uniform(0.1, 0.4),
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

class MainScreen(Screen):
    """The main interface for the Scrcpy Link."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        from kivy.uix.floatlayout import FloatLayout
        float_lay = FloatLayout()
        
        wp_path = 'wallpaper_mobile.jpg'
        if not os.path.exists(wp_path):
            wp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wallpaper_mobile.jpg')
        if not os.path.exists(wp_path):
            wp_path = 'wallpaper.jpg'
        if not os.path.exists(wp_path):
            wp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wallpaper.jpg')

        with float_lay.canvas.before:
            Color(0.03, 0.07, 0.05, 1)
            self.base_rect = Rectangle()
            
            if os.path.exists(wp_path):
                Color(1, 1, 1, 1)
                self.wp_rect = Rectangle(source=wp_path)
            else:
                self.wp_rect = None
                
            tint_val = float(config.get("wallpaper_tint_opacity", 0.33))
            self.tint_color_inst = Color(0.02, 0.06, 0.04, tint_val)
            self.tint_rect = Rectangle()
            
        float_lay.bind(pos=self._update_bg, size=self._update_bg)
        
        self.particle_bg = ParticleBackground(size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        float_lay.add_widget(self.particle_bg)
        
        # UI layer over particles (ScrollView top-aligned layout)
        scroll = ScrollView(size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(14), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))
        
        # ── 1. Top Header Bar (Android Face + In-app Title) ─────────────
        top_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(36), spacing=dp(6))
        
        face_path = 'android_face.png'
        if not os.path.exists(face_path):
            face_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'android_face.png')
        if os.path.exists(face_path):
            face_img = Image(source=face_path, size_hint=(None, 1), width=dp(30), allow_stretch=True, keep_ratio=True)
            top_bar.add_widget(face_img)

        self.label = Label(text="CelSuite - Scrcpy Heartbeat :)", font_size=sp(15), bold=True, color=ACCENT_PRIMARY, size_hint_x=1.0, halign='left', valign='middle')
        self.label.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        top_bar.add_widget(self.label)
        content.add_widget(top_bar)
        
        # ── 2. Central Hero Connection Card ─────────────────────────────
        hero_card = RoundedCard(orientation='vertical', size_hint_y=None, height=dp(210), padding=dp(14), spacing=dp(8))
        
        # PC IP status badge inside hero card on top
        self.pc_ip_input = TextInput(
            text="Discovering PC...", readonly=True, halign='center',
            font_size=sp(13), background_color=INPUT_BG, foreground_color=TEXT_PRIMARY,
            size_hint_y=None, height=dp(36)
        )
        hero_card.add_widget(self.pc_ip_input)

        status_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40), spacing=dp(8))
        self.pulse = PulseIndicator()
        self.status_label = Label(text="Listening for PC broadcast...", font_size=sp(12), color=TEXT_SECONDARY, halign='left', valign='middle')
        self.status_label.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        status_row.add_widget(self.pulse)
        status_row.add_widget(self.status_label)
        
        restart_btn = AnimatedButton(text="TAP TO LINK", btn_color=ACCENT_PRIMARY, font_size=sp(15), size_hint_y=None, height=dp(50))
        restart_btn.bind(on_press=self.restart_connection)
        
        hero_card.add_widget(status_row)
        hero_card.add_widget(restart_btn)
        content.add_widget(hero_card)
        
        # ── 3. 2x2 Glassmorphic Action Grid ──────────────────────────────
        grid = GridLayout(cols=2, spacing=dp(10), size_hint_y=None, height=dp(220))
        
        transfer_card = GridCard(icon="TRANSFER", title="WiFi Transfer", subtitle="Send & receive files", btn_color=CARD_BG, on_press_callback=self.go_transfer)
        vault_card = GridCard(icon="VAULT", title="File Vault", subtitle="Downloaded media", btn_color=CARD_BG, on_press_callback=self.go_vault)
        settings_card = GridCard(icon="SETTINGS", title="Settings & Help", subtitle="App preferences", btn_color=CARD_BG, on_press_callback=self.go_settings)
        logs_card = GridCard(icon="LOGS", title="System Logs", subtitle="Live terminal logs", btn_color=CARD_BG, on_press_callback=self.go_logs)
        
        grid.add_widget(transfer_card)
        grid.add_widget(vault_card)
        grid.add_widget(settings_card)
        grid.add_widget(logs_card)
        
        content.add_widget(grid)
        scroll.add_widget(content)
        
        float_lay.add_widget(scroll)
        self.add_widget(float_lay)

        self.sending = False
        self.discovered_pc_ip = None
        self._discovery_running = False
        Window.bind(size=self._update_bg)

    def _update_bg(self, *args):
        win_size = Window.size
        win_w, win_h = win_size
        self.base_rect.pos = (0, 0)
        self.base_rect.size = win_size
        
        if self.wp_rect:
            fit_mode = config.get("wallpaper_fit", "Stretch")
            if fit_mode == "Zoom" and win_h > 0:
                # Aspect Ratio Crop / Zoom to fill screen without distortion
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
                # Default "Stretch" to fit exactly
                self.wp_rect.pos = (0, 0)
                self.wp_rect.size = win_size
                
        self.tint_rect.pos = (0, 0)
        self.tint_rect.size = win_size

    def go_transfer(self, instance):
        self.manager.current = 'transfer'

    def go_vault(self, instance):
        self.manager.current = 'vault'

    def go_logs(self, instance):
        self.manager.current = 'logs'

    def go_settings(self, instance):
        self.manager.current = 'settings'

    def go_help(self, instance):
        self.manager.current = 'help'

    def on_enter(self):
        disable_file_uri_exposure_check()
        if not self._discovery_running:
            app_log("Launching background ADB triggers")
            threading.Thread(target=enable_shizuku_wireless_adb, daemon=True).start()
            self._start_services()

    def restart_connection(self, instance):
        app_log("Restarting link...")
        self._stop_services()
        threading.Thread(target=enable_shizuku_wireless_adb, daemon=True).start()
        self.pc_ip_input.text = "Discovering PC..."
        self.status_label.text = "Listening for PC broadcast..."
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
            sock.bind(("0.0.0.0", config["discovery_port"]))
            
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
                    app_log(f"Discovery receive error: {e}")
                    time.sleep(1)
        except Exception as e:
            app_log(f"Discovery socket failed: {e}")
        finally:
            sock.close()

    def start_heartbeat(self, pc_ip):
        self.pc_ip_input.text = pc_ip
        self.status_label.text = f"PC found! Initiating link..."
        self.pulse.set_state(True)
        if not self.sending:
            self.sending = True
            threading.Thread(target=self.heartbeat_loop, args=(pc_ip,), daemon=True).start()

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
        port = config["heartbeat_port"]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception:
            pass

        try:
            while self.sending:
                try:
                    phone_ip = self._get_phone_ip(target_ip)
                    msg = f"HELLO_USER|{phone_ip}|{config['adb_port']}"
                    sock.sendto(msg.encode('utf-8'), (target_ip, port))
                except Exception as e:
                    app_log(f"Heartbeat loop error: {e}")
                    try:
                        sock.close()
                    except Exception:
                        pass
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    except Exception:
                        pass
                time.sleep(4)
        finally:
            try:
                sock.close()
            except Exception:
                pass


class FileTransferScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        layout = ColoredBoxLayout(orientation='vertical', bg_color=DARK_BG, padding=dp(20), spacing=dp(16))
        
        title = Label(text="WiFi File Transfer Hub", font_size=sp(24), bold=True, color=ACCENT_PRIMARY, size_hint_y=None, height=dp(40))
        layout.add_widget(title)

        server_group = RoundedCard(orientation='vertical', padding=dp(16), spacing=dp(10), size_hint_y=None, height=dp(180))
        server_group.add_widget(Label(text="WiFi Receiver Status: ACTIVE", font_size=sp(16), bold=True, color=SUCCESS, halign='left', size_hint_y=None, height=dp(20)))
        
        self.serv_file_lbl = Label(text="Waiting for PC transfer...", font_size=sp(14), color=TEXT_PRIMARY, halign='center')
        self.serv_progress_lbl = Label(text="0%", font_size=sp(18), bold=True, color=ACCENT_PRIMARY, size_hint_y=None, height=dp(30))
        self.serv_progress = GradientBar(progress=0)
        self.serv_stats = Label(text="Speed: -- MB/s  |  ETA: --:--", font_size=sp(12), color=TEXT_SECONDARY, size_hint_y=None, height=dp(20))
        
        server_group.add_widget(self.serv_file_lbl)
        server_group.add_widget(self.serv_progress_lbl)
        server_group.add_widget(self.serv_progress)
        server_group.add_widget(self.serv_stats)

        sender_group = RoundedCard(orientation='vertical', padding=dp(16), spacing=dp(12), size_hint_y=None, height=dp(220))
        sender_group.add_widget(Label(text="Send Vault File to PC", font_size=sp(16), bold=True, color=ACCENT_PRIMARY, size_hint_y=None, height=dp(20)))
        
        self.file_chooser = FileChooserListView(path='/storage/emulated/0', size_hint_y=None, height=dp(250))
        self.send_progress_lbl = Label(text="Push speed: --  |  ETA: --", font_size=sp(14), color=TEXT_PRIMARY, size_hint_y=None, height=dp(30))
        self.send_bar = GradientBar(progress=0)
        self.send_btn = AnimatedButton(text="Push Selected File to PC", btn_color=ACCENT_TERTIARY, size_hint_y=None, height=dp(48))
        self.send_btn.bind(on_press=self.start_file_send_to_pc)

        sender_group.height = dp(400)
        sender_group.add_widget(self.file_chooser)
        sender_group.add_widget(self.send_progress_lbl)
        sender_group.add_widget(self.send_bar)
        sender_group.add_widget(self.send_btn)

        # ── 3. Send Clipboard to PC Card ──────────────────────────────
        clip_group = RoundedCard(orientation='vertical', padding=dp(16), spacing=dp(10), size_hint_y=None, height=dp(160))
        clip_group.add_widget(Label(text="Clipboard Sync (Phone \u2192 PC)", font_size=sp(16), bold=True, color=ACCENT_PRIMARY, size_hint_y=None, height=dp(20)))

        self.clip_preview_lbl = Label(text="Tap below to send phone clipboard to PC", font_size=sp(13), color=TEXT_SECONDARY, halign='center', size_hint_y=None, height=dp(30))
        self.clip_preview_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        self.clip_send_btn = AnimatedButton(text="\U0001f4cb Send Clipboard to PC", btn_color=ACCENT_SECONDARY, color=(0.02, 0.10, 0.06, 1), size_hint_y=None, height=dp(48))
        self.clip_send_btn.bind(on_press=self.send_clipboard_to_pc)

        clip_group.add_widget(self.clip_preview_lbl)
        clip_group.add_widget(self.clip_send_btn)

        scroll = ScrollView(size_hint=(1, 1))
        content = BoxLayout(orientation='vertical', spacing=dp(14), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))
        content.add_widget(server_group)
        content.add_widget(sender_group)
        content.add_widget(clip_group)
        scroll.add_widget(content)

        layout.add_widget(scroll)

        back_btn = AnimatedButton(text="Back to Home", btn_color=BUTTON_BG, color=(1, 1, 1, 1), size_hint_y=None, height=dp(50))
        back_btn.bind(on_press=self.go_back)
        layout.add_widget(back_btn)
        
        self.add_widget(layout)

    def send_clipboard_to_pc(self, instance):
        try:
            from kivy.core.clipboard import Clipboard
            clip_text = Clipboard.paste()
        except Exception:
            clip_text = ""
            
        if not clip_text:
            self.clip_preview_lbl.text = "\u26a0\ufe0f Phone clipboard is empty!"
            return

        main_screen = self.manager.get_screen('main')
        pc_ip = getattr(main_screen, 'discovered_pc_ip', None)
        if not pc_ip:
            self.clip_preview_lbl.text = "\u274c PC not linked yet! Please link first."
            return

        self.clip_preview_lbl.text = f"Sending {len(clip_text)} chars to PC..."
        threading.Thread(target=self._push_clipboard_thread, args=(pc_ip, clip_text), daemon=True).start()

    def _push_clipboard_thread(self, pc_ip, clip_text):
        try:
            data = clip_text.encode('utf-8')
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            s.connect((pc_ip, PORT_TCP_TRANSFER))
            
            header = f"FILE_SEND|clipboard.txt|{len(data)}\n"
            s.sendall(header.encode('utf-8'))
            time.sleep(0.1)
            s.sendall(data)
            s.close()
            Clock.schedule_once(lambda dt: setattr(self.clip_preview_lbl, 'text', "\u2705 Clipboard synced to PC!"))
        except Exception as e:
            Clock.schedule_once(lambda dt: setattr(self.clip_preview_lbl, 'text', f"\u274c Transfer error: {e}"))

    def go_back(self, instance):
        self.manager.current = 'main'

    def populate_vault_files(self, instance):
        try:
            files = sorted(os.listdir(VAULT_DIR))
            self.sender_spinner.values = [f for f in files if os.path.isfile(os.path.join(VAULT_DIR, f))]
        except OSError as e:
            app_log(f"Failed to list vault files: {e}")
            self.sender_spinner.values = []

    def start_file_send_to_pc(self, instance):
        selection = getattr(self, 'file_chooser', None)
        if not selection or not selection.selection:
            self.send_progress_lbl.text = "Please select a file first!"
            return
            
        filepath = selection.selection[0]
        filename = os.path.basename(filepath)
            
        main_screen = self.manager.get_screen('main')
        pc_ip = main_screen.discovered_pc_ip
        if not pc_ip:
            self.send_progress_lbl.text = "No discovered PC IP!"
            return

        self.send_btn.disabled = True
        self.send_progress_lbl.text = "Connecting to PC File server..."
        
        def _task():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            try:
                sock.connect((pc_ip, PORT_TCP_TRANSFER))
                filesize = os.path.getsize(filepath)
                header = f"FILE_SEND|{filename}|{filesize}\n"
                sock.sendall(header.encode('utf-8'))
                
                sent_bytes = 0
                start_time = time.time()
                last_progress_time = start_time
                last_bytes = 0
                
                with open(filepath, "rb") as f:
                    while sent_bytes < filesize:
                        chunk = f.read(65536)
                        if not chunk: break
                        sock.sendall(chunk)
                        sent_bytes += len(chunk)
                        
                        now = time.time()
                        if now - last_progress_time >= 0.5:
                            dt = now - last_progress_time
                            delta = sent_bytes - last_bytes
                            speed = (delta / dt) / (1024 * 1024) if dt > 0 else 0
                            percent = int((sent_bytes / filesize) * 100) if filesize > 0 else 0
                            eta = (filesize - sent_bytes) / (delta / dt) if delta > 0 else 0
                            
                            Clock.schedule_once(lambda dt, p=percent, s=speed, e=eta: self.update_send_ui(p, s, e))
                            
                            last_bytes = sent_bytes
                            last_progress_time = now
                
                sock.close()
                Clock.schedule_once(lambda dt: self.on_send_complete(True, f"Sent '{filename}' successfully!"))
            except Exception as e:
                try: sock.close()
                except OSError: pass
                Clock.schedule_once(lambda dt, err=str(e): self.on_send_complete(False, f"Push failed: {err}"))

        threading.Thread(target=_task, daemon=True).start()

    def update_send_ui(self, percent, speed, eta):
        self.send_bar.progress = percent
        self.send_progress_lbl.text = f"Progress: {percent}% | Speed: {speed:.1f} MB/s | ETA: {int(eta)}s"

    def on_send_complete(self, success, msg):
        self.send_btn.disabled = False
        self.send_progress_lbl.text = msg
        if success: self.send_bar.progress = 100

    def update_progress_from_server(self, percent, speed, eta, filename):
        def _update(dt):
            self.serv_file_lbl.text = f"Receiving: '{filename}'"
            self.serv_progress_lbl.text = f"{percent}%"
            self.serv_progress.progress = percent
            self.serv_stats.text = f"Speed: {speed:.1f} MB/s  |  ETA: {int(eta)}s"
        Clock.schedule_once(_update)

    def on_server_transfer_complete(self, success, details):
        def _update(dt):
            if success:
                self.serv_progress_lbl.text = "100%"
                self.serv_progress.progress = 100
            self.serv_file_lbl.text = f"Success: {details}" if success else f"Failed: {details}"
            self.serv_stats.text = "Done" if success else "Stopped"
        Clock.schedule_once(_update)


class LogsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = ColoredBoxLayout(orientation='vertical', bg_color=DARK_BG, padding=dp(20), spacing=dp(16))
        
        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(48), spacing=dp(8))
        title = Label(text="Live System Logs", font_size=sp(20), bold=True, color=ACCENT_PRIMARY, size_hint_x=0.45, halign='left', valign='middle')
        title.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        
        self.copy_btn = AnimatedButton(text="📋 Copy", btn_color=ACCENT_PRIMARY, size_hint_x=None, width=dp(95))
        self.copy_btn.bind(on_press=self.copy_logs)
        
        refresh_btn = AnimatedButton(text="Refresh", btn_color=ACCENT_TERTIARY, size_hint_x=None, width=dp(85))
        refresh_btn.bind(on_press=lambda x: self.load_logs())
        
        header.add_widget(title)
        header.add_widget(self.copy_btn)
        header.add_widget(refresh_btn)
        layout.add_widget(header)

        card = RoundedCard(orientation='vertical', padding=dp(10))
        self.scroll = ScrollView()
        self.log_label = Label(text="Loading system logs...", font_size=sp(12), color=TEXT_PRIMARY, size_hint_y=None, halign='left', valign='top')
        self.log_label.bind(width=lambda inst, val: setattr(inst, 'text_size', (val, None)))
        self.log_label.bind(texture_size=lambda inst, val: setattr(inst, 'height', val[1]))
        self.scroll.add_widget(self.log_label)
        card.add_widget(self.scroll)
        layout.add_widget(card)

        btn_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(50), spacing=dp(12))
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
        self.load_logs()

    def copy_logs(self, instance=None):
        try:
            from kivy.core.clipboard import Clipboard
            text = self.log_label.text
            Clipboard.copy(text)
            self.copy_btn.text = "✅ Copied!"
            Clock.schedule_once(lambda dt: setattr(self.copy_btn, 'text', '📋 Copy'), 1.5)
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


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = ColoredBoxLayout(orientation='vertical', bg_color=DARK_BG, padding=dp(16), spacing=dp(12))
        
        title = Label(text="App Configuration", font_size=sp(22), bold=True, color=ACCENT_PRIMARY, size_hint_y=None, height=dp(36))
        layout.add_widget(title)
        
        card = RoundedCard(orientation='vertical', padding=dp(16), spacing=dp(10), size_hint_y=None, height=dp(490))
        
        log_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(42))
        log_layout.add_widget(Label(text="Enable Session Logging", color=TEXT_PRIMARY, font_size=sp(15), halign='left', size_hint_x=0.7))
        self.log_switch = Switch(active=config.get("logging_enabled", True))
        self.log_switch.bind(active=self.on_log_switch)
        log_layout.add_widget(self.log_switch)
        card.add_widget(log_layout)
        
        self.add_port_spinner(card, "Heartbeat Port (Phone -> PC)", "heartbeat_port")
        self.add_port_spinner(card, "Discovery Port (PC Broadcast)", "discovery_port")
        self.add_port_spinner(card, "scrcpy ADB Port", "adb_port")

        # ── Liquid Glass Opacity Slider ──────────────────────────────────
        glass_val = float(config.get("glass_opacity", 0.33))
        self.glass_lbl = Label(text=f"Liquid Glass Opacity: {int(glass_val * 100)}%", color=TEXT_PRIMARY, font_size=sp(14), halign='left', size_hint_y=None, height=dp(20))
        self.glass_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        glass_slider = Slider(min=0.10, max=0.90, value=glass_val, step=0.01, size_hint_y=None, height=dp(32))
        glass_slider.bind(value=self.on_glass_slider)
        card.add_widget(self.glass_lbl)
        card.add_widget(glass_slider)

        # ── Wallpaper Dark Tint Slider ───────────────────────────────────
        tint_val = float(config.get("wallpaper_tint_opacity", 0.33))
        self.tint_lbl = Label(text=f"Wallpaper Dark Tint: {int(tint_val * 100)}%", color=TEXT_PRIMARY, font_size=sp(14), halign='left', size_hint_y=None, height=dp(20))
        self.tint_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
        tint_slider = Slider(min=0.10, max=0.90, value=tint_val, step=0.01, size_hint_y=None, height=dp(32))
        tint_slider.bind(value=self.on_tint_slider)
        card.add_widget(self.tint_lbl)
        card.add_widget(tint_slider)

        # ── Wallpaper Fit Mode Spinner (Stretch vs Zoom) ─────────────────
        fit_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(44))
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

        # ── Version Badge ────────────────────────────────────────────────
        ver_lbl = Label(text="CelSuite Mobile • Version v269.3.1", color=ACCENT_SECONDARY, font_size=sp(13), bold=True, halign='center', size_hint_y=None, height=dp(24))
        card.add_widget(ver_lbl)
        
        layout.add_widget(card)
        layout.add_widget(Widget())
        
        back_btn = AnimatedButton(text="Save & Return", btn_color=ACCENT_PRIMARY, font_size=sp(16), size_hint_y=None, height=dp(48))
        back_btn.bind(on_press=self.go_back)
        layout.add_widget(back_btn)
        
        self.add_widget(layout)

    def on_fit_change(self, instance, text):
        config["wallpaper_fit"] = text
        save_config(config)
        try:
            main_screen = self.manager.get_screen('main')
            if hasattr(main_screen, '_update_bg'):
                main_screen._update_bg()
        except Exception:
            pass

    def on_glass_slider(self, instance, value):
        self.glass_lbl.text = f"Liquid Glass Opacity: {int(value * 100)}%"
        config["glass_opacity"] = round(value, 2)
        save_config(config)

    def on_tint_slider(self, instance, value):
        self.tint_lbl.text = f"Wallpaper Dark Tint: {int(value * 100)}%"
        config["wallpaper_tint_opacity"] = round(value, 2)
        save_config(config)

    def go_back(self, instance):
        self.manager.current = 'main'

    def add_port_spinner(self, layout, label_text, config_key):
        box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(44))
        lbl = Label(text=label_text, color=TEXT_PRIMARY, font_size=sp(13), halign='left', size_hint_x=0.6)
        lbl.bind(size=lbl.setter('text_size'))
        box.add_widget(lbl)
        spinner = Spinner(text=str(config.get(config_key)), values=[str(p) for p in range(5550, 5560)], background_color=INPUT_BG, color=TEXT_PRIMARY, size_hint_x=0.4)
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


class HelpScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = ColoredBoxLayout(orientation='vertical', bg_color=DARK_BG, padding=dp(20), spacing=dp(16))
        
        title = Label(text="Help & Setup Manual", color=ACCENT_PRIMARY, font_size=sp(24), bold=True, size_hint_y=None, height=dp(40))
        layout.add_widget(title)
        
        card = RoundedCard(orientation='vertical', padding=dp(16))
        scroll = ScrollView()
        content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(12))
        content.bind(minimum_height=content.setter('height'))
        
        guide_text = (
            "[b]CelSuite - Scrcpy Heartbeat v269.11.0[/b]\n\n"
            "[b]Quick Launch Instructions:[/b]\n"
            "1. Link phone and PC to the same WiFi/hotspot.\n"
            "2. Open the PC PySide6 CelSuite client, then open this app on your phone.\n"
            "3. High-performance scrcpy mirroring session starts instantly!\n\n"
            "[b]Shizuku Wireless Setup:[/b]\n"
            "• Execute: [color=10B981]rish -c 'adb tcpip 5555'[/color]\n\n"
            "[b]Bidirectional Clipboard Sync:[/b]\n"
            "• Turn on auto-sync on the PC app for seamless, instant, zero-delay copying across systems!\n\n"
            "[b]WiFi File Transfer Hub:[/b]\n"
            "• Uses dedicated, multi-megabyte TCP file protocol. Super fast and bypasses restrictive ADB permission pipelines."
        )
        
        guide_label = Label(text=guide_text, markup=True, color=TEXT_PRIMARY, font_size=sp(14), halign='left', valign='top', size_hint_y=None)
        guide_label.bind(width=lambda inst, val: setattr(inst, 'text_size', (val, None)))
        guide_label.bind(texture_size=lambda inst, val: setattr(inst, 'height', val[1]))
        
        content.add_widget(guide_label)
        scroll.add_widget(content)
        card.add_widget(scroll)
        layout.add_widget(card)
        
        back_btn = AnimatedButton(text="Back to Home", btn_color=BUTTON_BG, font_size=sp(16), size_hint_y=None, height=dp(50))
        back_btn.bind(on_press=self.go_back)
        layout.add_widget(back_btn)
        
        self.add_widget(layout)

    def go_back(self, instance):
        self.manager.current = 'main'


class VaultScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = ColoredBoxLayout(orientation='vertical', bg_color=DARK_BG, padding=dp(20), spacing=dp(16))
        
        header = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(48))
        title = Label(text="Vault Files", color=ACCENT_PRIMARY, font_size=sp(24), bold=True)
        refresh_btn = AnimatedButton(text="Refresh", btn_color=ACCENT_TERTIARY, size_hint_x=None, width=dp(100))
        refresh_btn.bind(on_press=lambda x: self.refresh_vault())
        header.add_widget(title)
        header.add_widget(refresh_btn)
        layout.add_widget(header)
        
        self.card = RoundedCard(orientation='vertical', padding=dp(10))
        self.scroll = ScrollView()
        self.file_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8))
        self.file_list.bind(minimum_height=self.file_list.setter('height'))
        self.scroll.add_widget(self.file_list)
        self.card.add_widget(self.scroll)
        layout.add_widget(self.card)
        
        self.empty_label = Label(text="No files found in Vault.\nTry pushing files from your PC wirelessly!", color=TEXT_SECONDARY, font_size=sp(14), halign='center', size_hint_y=None, height=dp(60))
        self.empty_label.opacity = 0
        layout.add_widget(self.empty_label)
        
        back_btn = AnimatedButton(text="Back to Home", btn_color=BUTTON_BG, font_size=sp(16), size_hint_y=None, height=dp(50))
        back_btn.bind(on_press=self.go_back)
        layout.add_widget(back_btn)
        
        self.add_widget(layout)

    def go_back(self, instance):
        self.manager.current = 'main'
    
    def on_enter(self):
        self.refresh_vault()
    
    def refresh_vault(self):
        self.file_list.clear_widgets()
        try:
            files = sorted(os.listdir(VAULT_DIR))
            received_files = [f for f in files if os.path.isfile(os.path.join(VAULT_DIR, f))]
            
            if not received_files:
                self.empty_label.opacity = 1
                self.card.opacity = 0
                return
            
            self.empty_label.opacity = 0
            self.card.opacity = 1
            
            for filename in received_files:
                filepath = os.path.join(VAULT_DIR, filename)
                size = os.path.getsize(filepath)
                
                row = RoundedCard(orientation='horizontal', size_hint_y=None, height=dp(56), padding=dp(10), spacing=dp(10))
                
                name_label = Label(text=filename, color=TEXT_PRIMARY, font_size=sp(14), halign='left')
                name_label.bind(width=lambda i, v: setattr(i, 'text_size', (v, None)))
                
                size_label = Label(text=f"{size / (1024*1024):.1f} MB" if size >= 1024*1024 else f"{size/1024:.1f} KB", color=TEXT_SECONDARY, font_size=sp(12), size_hint_x=None, width=dp(70))
                
                share_btn = AnimatedButton(text="Share", btn_color=ACCENT_SECONDARY, size_hint_x=None, width=dp(80))
                share_btn.bind(on_press=lambda btn, path=filepath: self.share_file(path))
                
                row.add_widget(name_label)
                row.add_widget(size_label)
                row.add_widget(share_btn)
                self.file_list.add_widget(row)
        except OSError as e:
            app_log(f"Vault refresh failed: {e}")
    
    def share_file(self, file_path):
        try:
            from jnius import autoclass, cast
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            File = autoclass('java.io.File')
            
            context = PythonActivity.mActivity
            file_obj = File(file_path)
            uri = Uri.fromFile(file_obj)
            
            intent = Intent(Intent.ACTION_SEND)
            intent.setType("*/*")
            intent.putExtra(Intent.EXTRA_STREAM, cast('android.os.Parcelable', uri))
            
            String = autoclass('java.lang.String')
            chooser = Intent.createChooser(intent, cast('java.lang.CharSequence', String("Share File via:")))
            context.startActivity(chooser)
        except Exception as e:
            app_log(f"Share trigger failed: {e}")


class HeartbeatApp(App):
    """The main application class for CelS - Scrcpy Heartbeat."""
    title = "CelS - Scrcpy Heartbeat"
    icon = "icon_mobile.png"

    def build(self):
        Window.bind(on_keyboard=self.on_keyboard)
        
        # Request standard runtime permissions on startup
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE, 
                Permission.WRITE_EXTERNAL_STORAGE
            ])
            app_log("Requested Storage permissions from OS.")
        except Exception as e:
            app_log(f"Permissions request skipped: {e}")
            
        app_log(f"Storage mode: {'External (/sdcard)' if CAN_WRITE_EXTERNAL else 'Internal App Data'}")
        app_log(f"Log path: {LOG_FILE}")


        server = TCPFileServerThread()
        server.start()

        self.root_sm = ScreenManager(transition=FadeTransition())
        self.root_sm.add_widget(MainScreen(name='main'))
        self.root_sm.add_widget(FileTransferScreen(name='transfer'))
        self.root_sm.add_widget(VaultScreen(name='vault'))
        self.root_sm.add_widget(LogsScreen(name='logs'))
        self.root_sm.add_widget(SettingsScreen(name='settings'))
        self.root_sm.add_widget(HelpScreen(name='help'))
        
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
                    if active and not self.heartbeat_running:
                        self.toggle_heartbeat(None)
                    elif not active and self.heartbeat_running:
                        self.toggle_heartbeat(None)
            
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
            app_log("System broadcast receiver bound successfully.")
        except Exception as e:
            app_log(f"System receiver bind failed: {e}")
            
        return self.root_sm

    def on_start(self):
        if "--auto-screenshot" in sys.argv:
            def capture_and_quit(dt):
                from kivy.core.window import Window
                target_path = "/home/henry/.gemini/antigravity/brain/be570357-94fb-45bb-87f4-e9b546ad673b/cels_mobile_preview.png"
                for arg in sys.argv:
                    if arg.startswith("--screenshot-path="):
                        target_path = arg.split("=", 1)[1]
                Window.screenshot(name=target_path)
                app_log(f"Auto screenshot saved to {target_path}")
                Clock.schedule_once(lambda d: App.get_running_app().stop(), 1)

            app_log("Auto-screenshot mode active: capturing in 2 seconds...")
            Clock.schedule_once(capture_and_quit, 2)

    def on_keyboard(self, window, key, scancode, codepoint, modifier):
        if key == 27:
            if self.root_sm.current != 'main':
                self.root_sm.current = 'main'
                return True
        return False

    def set_local_clipboard(self, text):
        try:
            from jnius import autoclass
            Context = autoclass('android.content.Context')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE)
            ClipData = autoclass('android.content.ClipData')
            clip = ClipData.newPlainText("scrcpy", text)
            clipboard.setPrimaryClip(clip)
            app_log("Successfully updated local device clipboard.")
        except Exception as e:
            app_log(f"Failed to write device clipboard: {e}")

    def send_local_clipboard_to_pc(self):
        try:
            from jnius import autoclass
            Context = autoclass('android.content.Context')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE)
            if clipboard.hasPrimaryClip():
                clip_data = clipboard.getPrimaryClip()
                if clip_data.getItemCount() > 0:
                    text = clip_data.getItemAt(0).coerceToText(activity).toString()
                    main_screen = self.root_sm.get_screen('main')
                    pc_ip = main_screen.discovered_pc_ip
                    if pc_ip:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        sock.sendto(f"HELLO_CLIPBOARD|{text}".encode('utf-8'), (pc_ip, config["heartbeat_port"]))
                        sock.close()
        except Exception as e:
            app_log(f"Failed to fetch device clipboard: {e}")

if __name__ == "__main__":
    try:
        app_log("Launcher initializing...")
        HeartbeatApp().run()
    except Exception as e:
        app_log(f"CRASH ENCOUNTERED: {traceback.format_exc()}")
