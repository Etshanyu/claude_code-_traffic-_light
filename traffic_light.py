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

STATE_COLORS = {
    "coding": "#00e676",
    "waiting": "#ffd740",
    "done": "#ff5252",
}

STATE_LABELS = {
    "coding": "CODING",
    "waiting": "WAITING",
    "done": "COMPLETE",
}

STATE_LABELS_ZH = {
    "coding": "编码中",
    "waiting": "等待操作",
    "done": "编码完成",
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

        # Top scan line
        self._scan_line = self.canvas.create_line(10, 2, 210, 2, fill="", width=1)

        # Diamond indicator
        cx, cy = 24, 26
        s = 7
        self._diamond = self.canvas.create_polygon(
            cx, cy - s, cx + s, cy, cx, cy + s, cx - s, cy,
            fill="#00e676", outline=""
        )
        # Diamond glow ring
        self._diamond_ring = self.canvas.create_polygon(
            cx, cy - s - 3, cx + s + 3, cy, cx, cy + s + 3, cx - s - 3, cy,
            fill="", outline=self._dim_color("#00e676", 0.25), width=1
        )

        # Vertical separator line below diamond
        self.canvas.create_line(cx, cy + s + 5, cx, cy + s + 10,
                                fill=self._dim_color("#00e676", 0.3), width=1)

        # STATUS label
        self._status_label = self.canvas.create_text(
            46, 18, text="STATUS", anchor="w",
            font=("Consolas", 9), fill=self._dim_color("#00e676", 0.45)
        )

        # Main state text
        self._state_text = self.canvas.create_text(
            46, 34, text="INIT...", anchor="w",
            font=("Consolas", 13, "bold"), fill="#00e676"
        )

        # Timer text
        self._timer_text = self.canvas.create_text(
            172, 34, text="", anchor="w",
            font=("Consolas", 10), fill=self._dim_color("#00e676", 0.5)
        )

        # Right side vertical label
        self.canvas.create_text(
            212, 26, text="SYS", anchor="e",
            font=("Consolas", 7), fill=self._dim_color("#00e676", 0.2)
        )

        # Bottom edge glow line
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
        r2 = int(br + (r - br) * alpha)
        g2 = int(bg_ + (g - bg_) * alpha)
        b2 = int(bb + (b - bb) * alpha)
        return f"#{r2:02x}{g2:02x}{b2:02x}"

    def _position_window(self, default=False):
        pos = None
        if not default:
            pos = self._load_position()
        if pos:
            x, y = pos
        else:
            screen_w = self.root.winfo_screenwidth()
            x = screen_w - 240
            y = 20
        self.root.geometry(f"+{x}+{y}")

    def _load_position(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("window_x"), cfg.get("window_y")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    def _save_position(self):
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            cfg = {}
        cfg["window_x"] = x
        cfg["window_y"] = y
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

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
        self.canvas.itemconfig(self._state_text, text=f"{label}", fill=color)
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
        blended = self._blend(color, alpha)

        self.canvas.itemconfig(self._diamond, fill=blended)
        self._breath_job = self.root.after(interval, lambda: self._breathe(state))

    def _start_scan_line(self, color):
        if self._scan_job:
            self.root.after_cancel(self._scan_job)
            self._scan_job = None
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
            self._timer_job = None
        self._tick_timer(state)

    def _tick_timer(self, state):
        if self._state_start is None:
            return
        elapsed = int(time.time() - self._state_start)
        text = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
        self.canvas.itemconfig(self._timer_text, text=text)

        if state != "done":
            self._timer_job = self.root.after(1000, lambda: self._tick_timer(state))

    def run(self):
        self.root.mainloop()

    def set_opacity(self, opacity):
        self.root.attributes("-alpha", max(0.2, min(1.0, opacity)))

    def set_click_through(self, enabled):
        self._click_through = enabled
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            if enabled:
                style |= 0x00080020  # WS_EX_TRANSPARENT | WS_EX_LAYERED
            else:
                style &= ~0x00080020
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass

    def quit(self):
        if self._breath_job:
            self.root.after_cancel(self._breath_job)
        if self._timer_job:
            self.root.after_cancel(self._timer_job)
        if self._scan_job:
            self.root.after_cancel(self._scan_job)
        self.root.quit()
        self.root.destroy()


class StatusWatcher(FileSystemEventHandler):
    def __init__(self, file_path, callback):
        self._file_path = os.path.abspath(file_path)
        self._callback = callback
        self._observer = Observer()
        watch_dir = os.path.dirname(self._file_path)
        self._observer.schedule(self, watch_dir, recursive=False)

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


class TrayIcon:
    def __init__(self, on_quit, on_toggle_sound, on_toggle_notification,
                 on_set_speed, on_toggle_sonar, on_show_window,
                 on_set_opacity, on_toggle_click_through):
        self._on_quit = on_quit
        self._on_toggle_sound = on_toggle_sound
        self._on_toggle_notification = on_toggle_notification
        self._on_set_speed = on_set_speed
        self._on_toggle_sonar = on_toggle_sonar
        self._on_show_window = on_show_window
        self._on_set_opacity = on_set_opacity
        self._on_toggle_click_through = on_toggle_click_through
        self._current_state = "coding"
        self._sound_on = True
        self._notification_on = True
        self._sonar_on = True
        self._click_through = False
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
            pystray.MenuItem(
                lambda text: f"声音: {'开启' if self._sound_on else '关闭'}",
                self._toggle_sound
            ),
            pystray.MenuItem(
                lambda text: f"通知: {'开启' if self._notification_on else '关闭'}",
                self._toggle_notification
            ),
            pystray.MenuItem(
                lambda text: f"声纳: {'开启' if self._sonar_on else '关闭'}",
                self._toggle_sonar
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("闪烁速度: 快", lambda _: self._on_set_speed("fast")),
            pystray.MenuItem("闪烁速度: 中", lambda _: self._on_set_speed("medium")),
            pystray.MenuItem("闪烁速度: 慢", lambda _: self._on_set_speed("slow")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("透明度: 100%", lambda _: self._on_set_opacity(1.0)),
            pystray.MenuItem("透明度: 80%", lambda _: self._on_set_opacity(0.8)),
            pystray.MenuItem("透明度: 60%", lambda _: self._on_set_opacity(0.6)),
            pystray.MenuItem("透明度: 40%", lambda _: self._on_set_opacity(0.4)),
            pystray.MenuItem(
                lambda text: f"点击穿透: {'开启' if self._click_through else '关闭'}",
                self._toggle_click_through
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("显示窗口", lambda _: self._on_show_window()),
            pystray.MenuItem("退出", self._quit),
        )

    def update_state(self, state):
        self._current_state = state
        color = STATE_COLORS.get(state, "#999999")
        self._icon.icon = self._create_icon_image(color)
        self._icon.title = f"Claude Code: {STATE_LABELS_ZH.get(state, '未知')}"
        self._icon.menu = self._build_menu()

    def _toggle_sound(self, icon, item):
        self._sound_on = not self._sound_on
        self._on_toggle_sound(self._sound_on)
        self._icon.menu = self._build_menu()

    def _toggle_notification(self, icon, item):
        self._notification_on = not self._notification_on
        self._on_toggle_notification(self._notification_on)
        self._icon.menu = self._build_menu()

    def _toggle_sonar(self, icon, item):
        self._sonar_on = not self._sonar_on
        self._on_toggle_sonar(self._sonar_on)
        self._icon.menu = self._build_menu()

    def _toggle_click_through(self, icon, item):
        self._click_through = not self._click_through
        self._on_toggle_click_through(self._click_through)
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
                self._toaster.show_toast(
                    "Claude Code Traffic Light",
                    "Claude Code 需要你的操作",
                    duration=3, threaded=True
                )
        elif state == "done":
            if self.sound_on:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            if self.notification_on:
                time_str = elapsed_text or "已结束"
                self._toaster.show_toast(
                    "Claude Code Traffic Light",
                    f"Claude Code 编码完成，耗时 {time_str}",
                    duration=3, threaded=True
                )


class TrafficLightApp:
    def __init__(self):
        self.alerter = Alerter()
        self.sonar = SonarPlayer()
        self.tkinter_app = TkinterApp(on_drag_end=self._on_drag_end)
        self.tray_icon = TrayIcon(
            on_quit=self.quit,
            on_toggle_sound=self._toggle_sound,
            on_toggle_notification=self._toggle_notification,
            on_set_speed=self._set_blink_speed,
            on_toggle_sonar=self._toggle_sonar,
            on_show_window=self._show_window,
            on_set_opacity=self._set_opacity,
            on_toggle_click_through=self._toggle_click_through,
        )
        self.watcher = StatusWatcher(STATUS_FILE, self._on_status_change)

    def _on_status_change(self, status):
        state = status.get("state", "done")
        # Schedule UI update on the main thread via tkinter's after()
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

    def _toggle_sound(self, on):
        self.alerter.sound_on = on

    def _toggle_notification(self, on):
        self.alerter.notification_on = on

    def _toggle_sonar(self, on):
        self.sonar.sonar_on = on
        if on and self.tkinter_app._current_state == "coding":
            self.sonar.start()

    def _get_elapsed_text(self):
        start = self.tkinter_app._session_start
        if start is None:
            return ""
        elapsed = int(time.time() - start)
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

    def _set_blink_speed(self, speed):
        multiplier = {"fast": 0.5, "medium": 1.0, "slow": 2.0}.get(speed, 1.0)
        self.tkinter_app.set_speed_multiplier(multiplier)

    def _set_opacity(self, opacity):
        self.tkinter_app.set_opacity(opacity)

    def _toggle_click_through(self, enabled):
        self.tkinter_app.set_click_through(enabled)

    def run(self):
        # Load initial status silently (no alert for stale state)
        status = read_status()
        if status:
            state = status.get("state", "done")
            self.tkinter_app.update_state(state)
            self.tray_icon.update_state(state)
            self.alerter._last_state = state  # suppress stale alert

        self.watcher.start()

        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

        self.tkinter_app.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
        self.tkinter_app.run()

    def _minimize_to_tray(self):
        self.tkinter_app.root.withdraw()

    def _show_window(self):
        self.tkinter_app.root.deiconify()

    def quit(self):
        self.sonar.stop()
        self.watcher.stop()
        self.tkinter_app.quit()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test-ui":
        app = TkinterApp()

        def on_status(status):
            app.update_state(status["state"])

        watcher = StatusWatcher(STATUS_FILE, on_status)
        watcher.start()
        app.root.protocol("WM_DELETE_WINDOW", lambda: (watcher.stop(), app.quit()))
        app.run()
    else:
        app = TrafficLightApp()
        app.run()
