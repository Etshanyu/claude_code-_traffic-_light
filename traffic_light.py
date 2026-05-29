import ctypes
import json
import math
import os
import sys
import threading
import time
import tkinter as tk
import winsound

import pystray
import pygame
from PIL import Image, ImageDraw
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from win10toast import ToastNotifier

STATUS_FILE = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), ".claude-traffic-light-status.json")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".claude-traffic-light-config.json")
CLAUDE_SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")

STATE_COLORS = {
    "thinking": "#40c4ff",
    "coding": "#00e676",
    "waiting": "#ffd740",
    "done": "#ff5252",
}

STATE_LABELS = {
    "thinking": "THINKING",
    "coding": "CODING",
    "waiting": "WAITING",
    "done": "COMPLETE",
}

STATE_LABELS_ZH = {
    "thinking": "思考中",
    "coding": "编码中",
    "waiting": "等待操作",
    "done": "编码完成",
}

HOOKS_CONFIG = {
    "UserPromptSubmit": [{"matcher": "", "hooks": [{"type": "command", "command": "python -c \"import json,time,os; open(os.path.join(os.environ['USERPROFILE'],'.claude-traffic-light-status.json'),'w').write(json.dumps({'state':'thinking','timestamp':int(time.time())}))\""}]}],
    "PostToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "python -c \"import json,time,os; open(os.path.join(os.environ['USERPROFILE'],'.claude-traffic-light-status.json'),'w').write(json.dumps({'state':'coding','timestamp':int(time.time())}))\""}]}],
    "Notification": [{"matcher": "", "hooks": [{"type": "command", "command": "python -c \"import json,time,os; open(os.path.join(os.environ['USERPROFILE'],'.claude-traffic-light-status.json'),'w').write(json.dumps({'state':'waiting','timestamp':int(time.time())}))\""}]}],
    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "python -c \"import json,time,os; open(os.path.join(os.environ['USERPROFILE'],'.claude-traffic-light-status.json'),'w').write(json.dumps({'state':'done','timestamp':int(time.time())}))\""}]}],
}


def read_status():
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_status(state, message=""):
    data = {"state": state, "timestamp": int(time.time()), "message": message}
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def check_hooks_installed():
    try:
        with open(CLAUDE_SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
        hooks = settings.get("hooks", {})
        for event in HOOKS_CONFIG:
            if event not in hooks:
                return False
        return True
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def install_hooks():
    try:
        with open(CLAUDE_SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}
    if "hooks" not in settings:
        settings["hooks"] = {}
    for event, config in HOOKS_CONFIG.items():
        settings["hooks"][event] = config
    with open(CLAUDE_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


SONAR_FILE = _resource_path("submarine sonar_耳聆网.wav")

pygame.mixer.init()


class SonarPlayer:
    def __init__(self):
        self._playing = False
        self._sonar_on = True

    @property
    def sonar_on(self):
        return self._sonar_on

    @sonar_on.setter
    def sonar_on(self, value):
        self._sonar_on = value
        if not value:
            self.stop()

    def start(self):
        if self._playing or not self._sonar_on:
            return
        self._playing = True
        try:
            pygame.mixer.music.load(SONAR_FILE)
            pygame.mixer.music.play(loops=-1)
        except pygame.error:
            self._playing = False

    def stop(self):
        if self._playing:
            pygame.mixer.music.stop()
        self._playing = False


class TkinterApp:
    BG = "#0d0d1a"
    BG_RGB = (13, 13, 26)

    def __init__(self, on_drag_end=None):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=self.BG)

        self._on_drag_end = on_drag_end
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._click_through = False

        self._breath_phase = 0.0
        self._breath_job = None
        self._timer_job = None
        self._scan_job = None
        self._current_state = None
        self._state_start = None
        self._session_start = None
        self._speed_multiplier = 1.0
        self._scan_y = 0

        self._create_widgets()
        self._position_window(default=False)
        self._bind_drag_recursive(self.root)

    def _create_widgets(self):
        outer = tk.Frame(self.root, bg=self.BG, padx=2, pady=2)
        outer.pack()

        border_color = "#00e676"
        self.canvas = tk.Canvas(outer, width=220, height=52, bg=self.BG,
                                highlightthickness=1,
                                highlightbackground=self._dim_color(border_color, 0.3))
        self.canvas.pack()

        self._scan_line = self.canvas.create_line(10, 2, 210, 2, fill="", width=1)

        cx, cy = 24, 26
        s = 7
        self._diamond = self.canvas.create_polygon(
            cx, cy - s, cx + s, cy, cx, cy + s, cx - s, cy,
            fill="#00e676", outline=""
        )
        self._diamond_ring = self.canvas.create_polygon(
            cx, cy - s - 3, cx + s + 3, cy, cx, cy + s + 3, cx - s - 3, cy,
            fill="", outline=self._dim_color("#00e676", 0.25), width=1
        )
        self.canvas.create_line(cx, cy + s + 5, cx, cy + s + 10,
                                fill=self._dim_color("#00e676", 0.3), width=1)
        self._status_label = self.canvas.create_text(
            46, 18, text="STATUS", anchor="w",
            font=("Consolas", 9), fill=self._dim_color("#00e676", 0.45)
        )
        self._state_text = self.canvas.create_text(
            46, 34, text="INIT...", anchor="w",
            font=("Consolas", 13, "bold"), fill="#00e676"
        )
        self._timer_text = self.canvas.create_text(
            172, 34, text="", anchor="w",
            font=("Consolas", 10), fill=self._dim_color("#00e676", 0.5)
        )
        self.canvas.create_text(
            212, 26, text="SYS", anchor="e",
            font=("Consolas", 7), fill=self._dim_color("#00e676", 0.2)
        )
        self.canvas.create_line(10, 50, 210, 50,
                                fill=self._dim_color("#00e676", 0.15), width=1)

    @staticmethod
    def _dim_color(hex_color, factor):
        r = int(int(hex_color[1:3], 16) * factor)
        g = int(int(hex_color[3:5], 16) * factor)
        b = int(int(hex_color[5:7], 16) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _blend(hex_color, alpha):
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        br, bg_, bb = TkinterApp.BG_RGB
        return f"#{int(br + (r - br) * alpha):02x}{int(bg_ + (g - bg_) * alpha):02x}{int(bb + (b - bb) * alpha):02x}"

    def _position_window(self, default=False):
        pos = None
        if not default:
            cfg = load_config()
            wx, wy = cfg.get("window_x"), cfg.get("window_y")
            if wx is not None and wy is not None:
                pos = (wx, wy)
        if pos:
            x, y = pos
        else:
            x = self.root.winfo_screenwidth() - 240
            y = 20
        self.root.geometry(f"+{x}+{y}")

    def _save_position(self):
        cfg = load_config()
        cfg["window_x"] = self.root.winfo_x()
        cfg["window_y"] = self.root.winfo_y()
        save_config(cfg)

    def _bind_drag_recursive(self, widget):
        widget.bind("<ButtonPress-1>", self._on_drag_start)
        widget.bind("<B1-Motion>", self._on_drag_motion)
        widget.bind("<ButtonRelease-1>", self._on_drag_release)
        for child in widget.winfo_children():
            self._bind_drag_recursive(child)

    def _on_drag_start(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag_motion(self, event):
        x = self.root.winfo_x() + event.x - self._drag_start_x
        y = self.root.winfo_y() + event.y - self._drag_start_y
        self.root.geometry(f"+{x}+{y}")

    def _on_drag_release(self, event):
        self._save_position()
        if self._on_drag_end:
            self._on_drag_end(self.root.winfo_x(), self.root.winfo_y())

    def update_state(self, state):
        old_state = self._current_state
        self._current_state = state
        self._state_start = time.time()
        if state == "coding" and (old_state is None or old_state == "done"):
            self._session_start = time.time()
        color = STATE_COLORS.get(state, "#00e676")
        label = STATE_LABELS.get(state, "UNKNOWN")
        self.canvas.itemconfig(self._diamond, fill=color)
        self.canvas.itemconfig(self._diamond_ring, outline=self._dim_color(color, 0.25))
        self.canvas.itemconfig(self._state_text, text=label, fill=color)
        self.canvas.itemconfig(self._status_label, fill=self._dim_color(color, 0.45))
        self._start_animation(state)
        self._start_timer(state)
        self._start_scan_line(color)

    def set_speed_multiplier(self, multiplier):
        self._speed_multiplier = multiplier
        if self._current_state and self._current_state != "done":
            self._start_animation(self._current_state)

    def _start_animation(self, state):
        if self._breath_job:
            self.root.after_cancel(self._breath_job)
            self._breath_job = None
        if state == "done":
            return
        self._breath_phase = 0.0
        self._breathe(state)

    def _breathe(self, state):
        base_period = 2000 if state == "coding" else 1000
        period = int(base_period * self._speed_multiplier)
        steps = 20
        interval = period // steps
        self._breath_phase = (self._breath_phase + 1) % steps
        alpha = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(2 * math.pi * self._breath_phase / steps))
        color = STATE_COLORS.get(state, "#00e676")
        self.canvas.itemconfig(self._diamond, fill=self._blend(color, alpha))
        self._breath_job = self.root.after(interval, lambda: self._breathe(state))

    def _start_scan_line(self, color):
        if self._scan_job:
            self.root.after_cancel(self._scan_job)
        self._scan_y = 4
        self._scan_color = color
        self._animate_scan()

    def _animate_scan(self):
        self._scan_y = (self._scan_y + 1) if self._scan_y < 48 else 4
        alpha = 0.15 if self._current_state != "done" else 0.08
        self.canvas.itemconfig(self._scan_line, fill=self._dim_color(self._scan_color, alpha))
        self.canvas.coords(self._scan_line, 10, self._scan_y, 210, self._scan_y)
        self._scan_job = self.root.after(80, self._animate_scan)

    def _start_timer(self, state):
        if self._timer_job:
            self.root.after_cancel(self._timer_job)
        self._tick_timer(state)

    def _tick_timer(self, state):
        if self._state_start is None:
            return
        elapsed = int(time.time() - self._state_start)
        self.canvas.itemconfig(self._timer_text, text=f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        if state != "done":
            self._timer_job = self.root.after(1000, lambda: self._tick_timer(state))

    def run(self):
        self.root.mainloop()

    def set_opacity(self, opacity):
        self.root.attributes("-alpha", max(0.2, min(1.0, opacity)))

    def set_click_through(self, enabled):
        self._click_through = enabled
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            if enabled:
                style |= 0x00080020
            else:
                style &= ~0x00080020
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass

    def quit(self):
        for job in (self._breath_job, self._timer_job, self._scan_job):
            if job:
                self.root.after_cancel(job)
        self.root.quit()
        self.root.destroy()


class StatusWatcher(FileSystemEventHandler):
    def __init__(self, file_path, callback):
        self._file_path = os.path.abspath(file_path)
        self._callback = callback
        self._observer = Observer()
        self._observer.schedule(self, os.path.dirname(self._file_path), recursive=False)

    def on_modified(self, event):
        if os.path.abspath(event.src_path) == self._file_path:
            status = read_status()
            if status:
                self._callback(status)

    def start(self):
        self._observer.start()

    def stop(self):
        self._observer.stop()
        self._observer.join()


class SettingsWindow:
    BG = "#0d0d1a"
    FG = "#e0e0e0"
    ACCENT = "#00e676"
    DIM = "#1a1a3e"

    def __init__(self, parent_root, app):
        self._app = app
        self._window = tk.Toplevel(parent_root)
        self._window.title("Claude Code Traffic Light - Settings")
        self._window.configure(bg=self.BG)
        self._window.geometry("420x520")
        self._window.resizable(False, False)
        self._window.attributes("-topmost", True)
        self._window.protocol("WM_DELETE_WINDOW", self._window.destroy)

        self._build_ui()
        self._refresh_hook_status()

    def _section(self, parent, title):
        frame = tk.Frame(parent, bg=self.BG)
        frame.pack(fill="x", padx=16, pady=(12, 0))
        label = tk.Label(frame, text=f"▸ {title}", bg=self.BG, fg=self.ACCENT,
                         font=("Consolas", 11, "bold"), anchor="w")
        label.pack(fill="x")
        sep = tk.Frame(frame, bg=self._dim_color(self.ACCENT, 0.25), height=1)
        sep.pack(fill="x", pady=(2, 6))
        content = tk.Frame(frame, bg=self.BG)
        content.pack(fill="x")
        return content

    def _toggle_row(self, parent, label_text, initial, command):
        row = tk.Frame(parent, bg=self.BG)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label_text, bg=self.BG, fg=self.FG,
                 font=("Microsoft YaHei UI", 10), anchor="w").pack(side="left")
        var = tk.BooleanVar(value=initial)
        cb = tk.Checkbutton(row, variable=var, command=lambda: command(var.get()),
                            bg=self.BG, fg=self.ACCENT, selectcolor=self.DIM,
                            activebackground=self.BG, activeforeground=self.ACCENT,
                            font=("Consolas", 10))
        cb.pack(side="right")
        return var

    def _slider_row(self, parent, label_text, initial, from_, to_, resolution, command):
        row = tk.Frame(parent, bg=self.BG)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=label_text, bg=self.BG, fg=self.FG,
                 font=("Microsoft YaHei UI", 10), anchor="w").pack(side="left")
        slider = tk.Scale(row, from_=from_, to=to_, resolution=resolution,
                          orient="horizontal", length=180, command=command,
                          bg=self.BG, fg=self.ACCENT, troughcolor=self.DIM,
                          highlightthickness=0, font=("Consolas", 9), activebackground=self.ACCENT)
        slider.set(initial)
        slider.pack(side="right")
        return slider

    def _build_ui(self):
        # Header
        header = tk.Frame(self._window, bg=self.BG)
        header.pack(fill="x", padx=16, pady=(16, 0))
        tk.Label(header, text="⚙  SETTINGS", bg=self.BG, fg=self.ACCENT,
                 font=("Consolas", 16, "bold")).pack(side="left")

        # --- Notifications ---
        sec = self._section(self._window, "通知与声音")
        cfg = load_config()
        self._var_sound = self._toggle_row(sec, "状态提示音", cfg.get("sound_on", True), self._on_sound)
        self._var_notif = self._toggle_row(sec, "Windows 通知", cfg.get("notification_on", True), self._on_notif)
        self._var_sonar = self._toggle_row(sec, "编码声纳声", cfg.get("sonar_on", True), self._on_sonar)

        # --- Display ---
        sec = self._section(self._window, "显示")
        self._slider_row(sec, "透明度", cfg.get("opacity", 1.0), 0.2, 1.0, 0.1, self._on_opacity)
        speed_map = {"fast": 0, "medium": 1, "slow": 2}
        current_speed = cfg.get("blink_speed", "medium")
        self._slider_row(sec, "闪烁速度", speed_map.get(current_speed, 1), 0, 2, 1, self._on_speed)
        self._var_clickthrough = self._toggle_row(sec, "点击穿透", cfg.get("click_through", False), self._on_clickthrough)

        # --- Hooks ---
        sec = self._section(self._window, "Claude Code Hooks")
        self._hook_status_label = tk.Label(sec, text="", bg=self.BG, fg=self.FG,
                                           font=("Microsoft YaHei UI", 10), anchor="w")
        self._hook_status_label.pack(fill="x", pady=2)

        self._hook_btn = tk.Button(sec, text="", command=self._on_install_hooks,
                                   bg=self.DIM, fg=self.ACCENT,
                                   font=("Consolas", 10, "bold"),
                                   activebackground=self._dim_color(self.ACCENT, 0.3),
                                   activeforeground=self.ACCENT,
                                   relief="flat", padx=16, pady=4, cursor="hand2")
        self._hook_btn.pack(pady=(4, 0))

        # --- Footer ---
        footer = tk.Frame(self._window, bg=self.BG)
        footer.pack(side="bottom", fill="x", padx=16, pady=12)
        tk.Label(footer, text="Claude Code Traffic Light v1.0", bg=self.BG,
                 fg=self._dim_color(self.ACCENT, 0.3), font=("Consolas", 8)).pack()

    def _refresh_hook_status(self):
        installed = check_hooks_installed()
        if installed:
            self._hook_status_label.config(text="● Hooks 已安装，所有 Claude Code 会话将自动同步状态", fg="#00e676")
            self._hook_btn.config(text="重新安装 Hooks")
        else:
            self._hook_status_label.config(text="○ Hooks 未安装，状态将无法自动同步", fg="#ffd740")
            self._hook_btn.config(text="安装 Hooks")

    def _on_sound(self, val):
        self._app.alerter.sound_on = val
        cfg = load_config()
        cfg["sound_on"] = val
        save_config(cfg)

    def _on_notif(self, val):
        self._app.alerter.notification_on = val
        cfg = load_config()
        cfg["notification_on"] = val
        save_config(cfg)

    def _on_sonar(self, val):
        self._app.sonar.sonar_on = val
        if val and self._app.tkinter_app._current_state == "coding":
            self._app.sonar.start()
        cfg = load_config()
        cfg["sonar_on"] = val
        save_config(cfg)

    def _on_opacity(self, val):
        self._app.tkinter_app.set_opacity(float(val))
        cfg = load_config()
        cfg["opacity"] = float(val)
        save_config(cfg)

    def _on_speed(self, val):
        speed = {0: "fast", 1: "medium", 2: "slow"}.get(int(float(val)), "medium")
        multiplier = {"fast": 0.5, "medium": 1.0, "slow": 2.0}[speed]
        self._app.tkinter_app.set_speed_multiplier(multiplier)
        cfg = load_config()
        cfg["blink_speed"] = speed
        save_config(cfg)

    def _on_clickthrough(self, val):
        self._app.tkinter_app.set_click_through(val)
        cfg = load_config()
        cfg["click_through"] = val
        save_config(cfg)

    def _on_install_hooks(self):
        install_hooks()
        self._refresh_hook_status()

    @staticmethod
    def _dim_color(hex_color, factor):
        r = int(int(hex_color[1:3], 16) * factor)
        g = int(int(hex_color[3:5], 16) * factor)
        b = int(int(hex_color[5:7], 16) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"


class TrayIcon:
    def __init__(self, on_quit, on_show_window, on_show_settings):
        self._on_quit = on_quit
        self._on_show_window = on_show_window
        self._on_show_settings = on_show_settings
        self._current_state = "coding"
        self._icon = pystray.Icon(
            "traffic_light",
            self._create_icon_image(STATE_COLORS["coding"]),
            "Claude Code: 编码中",
            menu=self._build_menu()
        )

    def _create_icon_image(self, color):
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([8, 8, size - 8, size - 8], fill=color)
        return image

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                lambda text: f"状态: {STATE_LABELS_ZH.get(self._current_state, '未知')}",
                None, enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("设置", lambda _: self._on_show_settings()),
            pystray.MenuItem("显示窗口", lambda _: self._on_show_window()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._quit),
        )

    def update_state(self, state):
        self._current_state = state
        self._icon.icon = self._create_icon_image(STATE_COLORS.get(state, "#999999"))
        self._icon.title = f"Claude Code: {STATE_LABELS_ZH.get(state, '未知')}"
        self._icon.menu = self._build_menu()

    def _quit(self, icon, item):
        self._icon.stop()
        self._on_quit()

    def run(self):
        self._icon.run()

    def stop(self):
        self._icon.stop()


class Alerter:
    def __init__(self):
        self.sound_on = True
        self.notification_on = True
        self._toaster = ToastNotifier()
        self._last_state = None

    def alert(self, state, elapsed_text=""):
        if state == self._last_state:
            return
        self._last_state = state
        if state == "waiting":
            if self.sound_on:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            if self.notification_on:
                self._toaster.show_toast("Claude Code Traffic Light", "Claude Code 需要你的操作",
                                         duration=3, threaded=True)
        elif state == "done":
            if self.sound_on:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            if self.notification_on:
                self._toaster.show_toast("Claude Code Traffic Light",
                                         f"Claude Code 编码完成，耗时 {elapsed_text or '已结束'}",
                                         duration=3, threaded=True)


class TrafficLightApp:
    def __init__(self):
        cfg = load_config()

        self.alerter = Alerter()
        self.alerter.sound_on = cfg.get("sound_on", True)
        self.alerter.notification_on = cfg.get("notification_on", True)

        self.sonar = SonarPlayer()
        self.sonar._sonar_on = cfg.get("sonar_on", True)

        self.tkinter_app = TkinterApp(on_drag_end=self._on_drag_end)
        self.tkinter_app.set_opacity(cfg.get("opacity", 1.0))
        if cfg.get("click_through", False):
            self.tkinter_app.set_click_through(True)
        speed = cfg.get("blink_speed", "medium")
        self.tkinter_app.set_speed_multiplier({"fast": 0.5, "medium": 1.0, "slow": 2.0}.get(speed, 1.0))

        self.tray_icon = TrayIcon(
            on_quit=self.quit,
            on_show_window=self._show_window,
            on_show_settings=self._show_settings,
        )
        self.watcher = StatusWatcher(STATUS_FILE, self._on_status_change)
        self._settings_window = None

    def _on_status_change(self, status):
        state = status.get("state", "done")
        self.tkinter_app.root.after(0, self._apply_state_change, state)

    def _apply_state_change(self, state):
        self.tkinter_app.update_state(state)
        self.tray_icon.update_state(state)
        elapsed_text = self._get_elapsed_text()
        self.alerter.alert(state, elapsed_text)
        if state == "coding":
            self.sonar.start()
        else:
            self.sonar.stop()

    def _on_drag_end(self, x, y):
        pass

    def _get_elapsed_text(self):
        start = self.tkinter_app._session_start
        if start is None:
            return ""
        elapsed = int(time.time() - start)
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

    def _show_window(self):
        self.tkinter_app.root.deiconify()

    def _show_settings(self):
        if self._settings_window is not None:
            try:
                self._settings_window._window.focus_force()
                return
            except tk.TclError:
                pass
        self._settings_window = SettingsWindow(self.tkinter_app.root, self)

    def run(self):
        status = read_status()
        if status:
            state = status.get("state", "done")
            self.tkinter_app.update_state(state)
            self.tray_icon.update_state(state)
            self.alerter._last_state = state

        self.watcher.start()
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        self.tkinter_app.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
        self.tkinter_app.run()

    def _minimize_to_tray(self):
        self.tkinter_app.root.withdraw()

    def quit(self):
        self.sonar.stop()
        self.watcher.stop()
        self.tkinter_app.quit()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test-ui":
        app = TkinterApp()
        watcher = StatusWatcher(STATUS_FILE, lambda s: app.update_state(s["state"]))
        watcher.start()
        app.root.protocol("WM_DELETE_WINDOW", lambda: (watcher.stop(), app.quit()))
        app.run()
    else:
        TrafficLightApp().run()
