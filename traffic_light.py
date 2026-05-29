import json
import math
import os
import threading
import time
import tkinter as tk
import winsound

import pystray
from PIL import Image, ImageDraw
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from win10toast import ToastNotifier

STATUS_FILE = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), ".claude-traffic-light-status.json")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".claude-traffic-light-config.json")

STATE_COLORS = {
    "coding": "#27ae60",
    "waiting": "#f39c12",
    "done": "#e74c3c",
}

STATE_LABELS = {
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


class TkinterApp:
    def __init__(self, on_drag_end=None):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="white")

        self._setup_styles()
        self._create_widgets()

        self._drag_start_x = 0
        self._drag_start_y = 0
        self._on_drag_end = on_drag_end

        self._position_window(default=True)

        self.frame.bind("<ButtonPress-1>", self._on_drag_start)
        self.frame.bind("<B1-Motion>", self._on_drag_motion)
        self.frame.bind("<ButtonRelease-1>", self._on_drag_release)

        self._breath_phase = 0.0
        self._breath_job = None
        self._timer_job = None
        self._current_state = None
        self._state_start = None
        self._session_start = None
        self._speed_multiplier = 1.0

    def _setup_styles(self):
        self.frame_bg = "#ffffff"
        self.font_label = ("Microsoft YaHei UI", 10, "bold")
        self.font_time = ("Consolas", 9)
        self.colors = STATE_COLORS

    def _create_widgets(self):
        self.frame = tk.Frame(self.root, bg=self.frame_bg, padx=10, pady=6,
                              highlightbackground="#e0e0e0", highlightthickness=1)
        self.frame.pack()

        self.dot_canvas = tk.Canvas(self.frame, width=14, height=14,
                                    bg=self.frame_bg, highlightthickness=0)
        self.dot_canvas.pack(side=tk.LEFT, padx=(0, 8))
        self.dot = self.dot_canvas.create_oval(1, 1, 13, 13, fill="#999999", outline="")

        self.label = tk.Label(self.frame, text="等待中...", bg=self.frame_bg,
                              font=self.font_label, fg="#333333")
        self.label.pack(side=tk.LEFT, padx=(0, 8))

        self.time_label = tk.Label(self.frame, text="", bg=self.frame_bg,
                                   font=self.font_time, fg="#999999")
        self.time_label.pack(side=tk.LEFT)

    def _position_window(self, default=False):
        pos = None
        if not default:
            pos = self._load_position()
        if pos:
            x, y = pos
        else:
            screen_w = self.root.winfo_screenwidth()
            x = screen_w - 200
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

        color = self.colors.get(state, "#999999")
        label = STATE_LABELS.get(state, "未知")

        self.dot_canvas.itemconfig(self.dot, fill=color)
        self.label.config(text=label)

        self._start_animation(state)
        self._start_timer(state)

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
        alpha = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * self._breath_phase / steps))

        color = self.colors.get(state, "#999999")
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)

        bg_r, bg_g, bg_b = 255, 255, 255
        blend_r = int(bg_r + (r - bg_r) * alpha)
        blend_g = int(bg_g + (g - bg_g) * alpha)
        blend_b = int(bg_b + (b - bg_b) * alpha)
        blended = f"#{blend_r:02x}{blend_g:02x}{blend_b:02x}"

        self.dot_canvas.itemconfig(self.dot, fill=blended)
        self._breath_job = self.root.after(interval, lambda: self._breathe(state))

    def _start_timer(self, state):
        if self._timer_job:
            self.root.after_cancel(self._timer_job)
            self._timer_job = None
        self._tick_timer(state)

    def _tick_timer(self, state):
        if self._state_start is None:
            return
        elapsed = int(time.time() - self._state_start)
        prefix = "总 " if state == "done" else ""
        text = f"{prefix}{elapsed // 60:02d}:{elapsed % 60:02d}"
        self.time_label.config(text=text)

        if state != "done":
            self._timer_job = self.root.after(1000, lambda: self._tick_timer(state))

    def run(self):
        self.root.mainloop()

    def quit(self):
        if self._breath_job:
            self.root.after_cancel(self._breath_job)
        if self._timer_job:
            self.root.after_cancel(self._timer_job)
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
                 on_set_speed):
        self._on_quit = on_quit
        self._on_toggle_sound = on_toggle_sound
        self._on_toggle_notification = on_toggle_notification
        self._on_set_speed = on_set_speed
        self._current_state = "coding"
        self._sound_on = True
        self._notification_on = True
        self._icon = pystray.Icon(
            "traffic_light",
            self._create_icon_image("#27ae60"),
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
                lambda text: f"状态: {STATE_LABELS.get(self._current_state, '未知')}",
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
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("闪烁速度: 快", lambda _: self._on_set_speed("fast")),
            pystray.MenuItem("闪烁速度: 中", lambda _: self._on_set_speed("medium")),
            pystray.MenuItem("闪烁速度: 慢", lambda _: self._on_set_speed("slow")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._quit),
        )

    def update_state(self, state):
        self._current_state = state
        color = STATE_COLORS.get(state, "#999999")
        self._icon.icon = self._create_icon_image(color)
        self._icon.title = f"Claude Code: {STATE_LABELS.get(state, '未知')}"
        self._icon.menu = self._build_menu()

    def _toggle_sound(self, icon, item):
        self._sound_on = not self._sound_on
        self._on_toggle_sound(self._sound_on)
        self._icon.menu = self._build_menu()

    def _toggle_notification(self, icon, item):
        self._notification_on = not self._notification_on
        self._on_toggle_notification(self._notification_on)
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
        result = read_status()
        print(f"Status file: {STATUS_FILE}")
        print(f"Current status: {result}")
