# Claude Code Traffic Light Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop traffic light indicator that shows Claude Code's running status via a floating capsule widget and system tray icon.

**Architecture:** Claude Code Hooks write a JSON status file. A Python app monitors this file via watchdog, then updates a tkinter floating capsule, system tray icon, plays sounds, and shows Windows notifications based on the state.

**Tech Stack:** Python 3.8+, tkinter, pystray, Pillow, watchdog, win10toast, winsound

---

## File Structure

```
green/
├── traffic_light.py          # Main single-file application
├── requirements.txt          # pip dependencies
├── docs/
│   └── superpowers/
│       ├── specs/2026-05-29-traffic-light-design.md
│       └── plans/2026-05-29-traffic-light-plan.md
└── .claude/
    └── settings.json         # Hooks config (user copies to their own .claude/)
```

---

### Task 1: Project scaffold and dependencies

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
pystray>=0.19.5
Pillow>=10.0.0
watchdog>=3.0.0
win10toast>=0.9
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

- [ ] **Step 3: Verify imports work**

Run: `python -c "import pystray, PIL, watchdog, win10toast; print('OK')"`
Expected: `OK`

---

### Task 2: Status file infrastructure

**Files:**
- Create: `traffic_light.py` (initial version with status file constants only)

This task establishes the status file path and format, plus a standalone test script to verify hooks can write the file.

- [ ] **Step 1: Create traffic_light.py with constants and status file path**

```python
import json
import os
import time

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

if __name__ == "__main__":
    # Quick smoke test: write and read back
    write_status("coding", "test")
    result = read_status()
    assert result["state"] == "coding"
    print(f"Status file OK: {STATUS_FILE}")
    print(f"Result: {result}")
```

- [ ] **Step 2: Run smoke test**

Run: `python traffic_light.py`
Expected: Prints `Status file OK: <path>` and `Result: {'state': 'coding', ...}`

- [ ] **Step 3: Commit**

```bash
git init
git add requirements.txt traffic_light.py
git commit -m "feat: project scaffold with status file infrastructure"
```

---

### Task 3: Floating capsule widget (tkinter)

**Files:**
- Modify: `traffic_light.py` — add Tkinter UI class

- [ ] **Step 1: Add imports and TkinterApp class to traffic_light.py**

Add these imports at the top:

```python
import tkinter as tk
import math
```

Add the TkinterApp class after the `write_status` function:

```python
class TkinterApp:
    def __init__(self, on_drag_end=None):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="white")

        self._setup_styles()
        self._create_widgets()

        # Drag state
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._on_drag_end = on_drag_end

        # Position
        self._position_window(default=True)

        # Bind drag events
        self.frame.bind("<ButtonPress-1>", self._on_drag_start)
        self.frame.bind("<B1-Motion>", self._on_drag_motion)
        self.frame.bind("<ButtonRelease-1>", self._on_drag_release)

        # Animation state
        self._breath_phase = 0.0
        self._breath_job = None
        self._timer_job = None
        self._current_state = None
        self._state_start = None
        self._session_start = None
        self._speed_multiplier = 1.0  # 0.5=fast, 1.0=medium, 2.0=slow

    def _setup_styles(self):
        self.frame_bg = "#ffffff"
        self.font_label = ("Microsoft YaHei UI", 10, "bold")
        self.font_time = ("Consolas", 9)
        self.colors = STATE_COLORS

    def _create_widgets(self):
        self.frame = tk.Frame(self.root, bg=self.frame_bg, padx=10, pady=6,
                              highlightbackground="#e0e0e0", highlightthickness=1)
        self.frame.pack()

        # Rounded appearance via a canvas for the dot
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
            # Default: top-right corner with 20px margin
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

    def _start_animation(self, state):
        if self._breath_job:
            self.root.after_cancel(self._breath_job)
            self._breath_job = None
        if state == "done":
            return  # Solid, no animation
        self._breath_phase = 0.0
        self._breathe(state)

    def set_speed_multiplier(self, multiplier):
        self._speed_multiplier = multiplier
        if self._current_state and self._current_state != "done":
            self._start_animation(self._current_state)

    def _breathe(self, state):
        base_period = 2000 if state == "coding" else 1000  # ms
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
```

- [ ] **Step 2: Add a manual test block at the bottom of the file**

Replace the existing `if __name__` block with:

```python
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test-ui":
        app = TkinterApp()
        app.update_state("coding")
        app.root.after(5000, lambda: app.update_state("waiting"))
        app.root.after(10000, lambda: app.update_state("done"))
        app.run()
    else:
        result = read_status()
        print(f"Status file: {STATUS_FILE}")
        print(f"Current status: {result}")
```

- [ ] **Step 3: Test the floating capsule manually**

Run: `python traffic_light.py --test-ui`
Expected: A white capsule appears at top-right, green dot breathing "编码中", after 5s turns yellow breathing "等待操作", after 10s turns red solid "编码完成". Window is draggable.

- [ ] **Step 4: Commit**

```bash
git add traffic_light.py
git commit -m "feat: floating capsule widget with breathing animation and drag"
```

---

### Task 4: File watcher (watchdog integration)

**Files:**
- Modify: `traffic_light.py` — add StatusWatcher class

- [ ] **Step 1: Add watchdog imports and StatusWatcher class**

Add this import at the top:

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
```

Add the StatusWatcher class before the `if __name__` block:

```python
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
```

- [ ] **Step 2: Test watchdog with manual status writes**

Update the `--test-ui` branch in the `if __name__` block:

```python
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
```

- [ ] **Step 3: Test by running UI and writing status from another terminal**

Terminal 1: `python traffic_light.py --test-ui`
Terminal 2: `python -c "import traffic_light; traffic_light.write_status('coding')"`
Terminal 2: `python -c "import traffic_light; traffic_light.write_status('waiting')"`
Terminal 2: `python -c "import traffic_light; traffic_light.write_status('done')"`
Expected: Capsule updates state in real-time as status file changes.

- [ ] **Step 4: Commit**

```bash
git add traffic_light.py
git commit -m "feat: status file watcher with watchdog"
```

---

### Task 5: System tray icon

**Files:**
- Modify: `traffic_light.py` — add TrayIcon class

- [ ] **Step 1: Add pystray and Pillow imports, TrayIcon class**

Add these imports at the top:

```python
import pystray
from PIL import Image, ImageDraw
import threading
```

Add the TrayIcon class before the `if __name__` block:

```python
class TrayIcon:
    def __init__(self, on_quit, on_toggle_sound, on_toggle_notification,
                 on_set_speed, get_sound_state, get_notification_state):
        self._on_quit = on_quit
        self._on_toggle_sound = on_toggle_sound
        self._on_toggle_notification = on_toggle_notification
        self._on_set_speed = on_set_speed
        self._get_sound_state = get_sound_state
        self._get_notification_state = get_notification_state
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
            pystray.MenuItem("闪烁速度: 快", lambda: self._on_set_speed("fast")),
            pystray.MenuItem("闪烁速度: 中", lambda: self._on_set_speed("medium")),
            pystray.MenuItem("闪烁速度: 慢", lambda: self._on_set_speed("slow")),
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
```

- [ ] **Step 2: Test tray icon standalone**

Temporarily add a test branch in the `if __name__` block (will be replaced in Task 7):

```python
elif len(sys.argv) > 1 and sys.argv[1] == "--test-tray":
    tray = TrayIcon(
        on_quit=lambda: None,
        on_toggle_sound=lambda v: print(f"Sound: {v}"),
        on_toggle_notification=lambda v: print(f"Notification: {v}"),
        on_set_speed=lambda s: print(f"Speed: {s}"),
        get_sound_state=lambda: True,
        get_notification_state=lambda: True,
    )
    tray.run()
```

Run: `python traffic_light.py --test-tray`
Expected: Green dot appears in system tray, right-click shows menu with status/toggle/exit items.

- [ ] **Step 3: Commit**

```bash
git add traffic_light.py
git commit -m "feat: system tray icon with menu"
```

---

### Task 6: Sound and notifications

**Files:**
- Modify: `traffic_light.py` — add Alerter class

- [ ] **Step 1: Add Alerter class with winsound and win10toast**

Add these imports at the top (platform-safe):

```python
import platform
import winsound
```

Add `from win10toast import ToastNotifier` at the top.

Add the Alerter class before the `if __name__` block:

```python
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
```

- [ ] **Step 2: Quick test**

Run: `python -c "from traffic_light import Alerter; a=Alerter(); a.alert('waiting')"`
Expected: System sound plays and Windows notification appears "Claude Code 需要你的操作".

- [ ] **Step 3: Commit**

```bash
git add traffic_light.py
git commit -m "feat: sound and Windows notification alerts"
```

---

### Task 7: Wire everything together (main application)

**Files:**
- Modify: `traffic_light.py` — add TrafficLightApp class and update `if __name__`

- [ ] **Step 1: Add the main TrafficLightApp class**

Add this class before the `if __name__` block:

```python
class TrafficLightApp:
    def __init__(self):
        self.alerter = Alerter()
        self.tkinter_app = TkinterApp(on_drag_end=self._on_drag_end)
        self.tray_icon = TrayIcon(
            on_quit=self.quit,
            on_toggle_sound=self._toggle_sound,
            on_toggle_notification=self._toggle_notification,
            on_set_speed=self._set_blink_speed,
            get_sound_state=lambda: self.alerter.sound_on,
            get_notification_state=lambda: self.alerter.notification_on,
        )
        self.watcher = StatusWatcher(STATUS_FILE, self._on_status_change)

    def _on_status_change(self, status):
        state = status.get("state", "done")
        self.tkinter_app.update_state(state)
        self.tray_icon.update_state(state)
        elapsed_text = self._get_elapsed_text()
        self.alerter.alert(state, elapsed_text)

    def _on_drag_end(self, x, y):
        pass  # Position already saved by TkinterApp

    def _toggle_sound(self, on):
        self.alerter.sound_on = on

    def _toggle_notification(self, on):
        self.alerter.notification_on = on

    def _get_elapsed_text(self):
        start = self.tkinter_app._session_start
        if start is None:
            return ""
        elapsed = int(time.time() - start)
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

    def _set_blink_speed(self, speed):
        multiplier = {"fast": 0.5, "medium": 1.0, "slow": 2.0}.get(speed, 1.0)
        self.tkinter_app.set_speed_multiplier(multiplier)

    def run(self):
        # Load initial status
        status = read_status()
        if status:
            self._on_status_change(status)

        # Start watcher
        self.watcher.start()

        # Start tray in background thread
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

        # Handle window close
        self.tkinter_app.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)

        # Run tkinter mainloop (blocks)
        self.tkinter_app.run()

    def _minimize_to_tray(self):
        self.tkinter_app.root.withdraw()

    def quit(self):
        self.watcher.stop()
        self.tkinter_app.quit()
```

- [ ] **Step 2: Update the `if __name__` block**

Replace the entire `if __name__` block:

```python
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test-ui":
        app = TkinterApp()
        app.update_state("coding")
        app.root.after(5000, lambda: app.update_state("waiting"))
        app.root.after(10000, lambda: app.update_state("done"))
        app.run()
    else:
        app = TrafficLightApp()
        app.run()
```

- [ ] **Step 3: Full integration test**

Run: `python traffic_light.py`
Expected: Capsule appears in top-right, green "编码中" breathing. Tray icon is green dot.

Then from another terminal simulate state changes:
```bash
python -c "import traffic_light; traffic_light.write_status('waiting')"
python -c "import traffic_light; traffic_light.write_status('done')"
python -c "import traffic_light; traffic_light.write_status('coding')"
```
Expected: Capsule and tray icon update. Sound plays on waiting/done. Notifications appear.

Right-click tray icon to toggle sound/notifications and test Exit.

- [ ] **Step 4: Commit**

```bash
git add traffic_light.py
git commit -m "feat: wire all components together in TrafficLightApp"
```

---

### Task 8: Claude Code hooks configuration

**Files:**
- Create: `.claude/settings.json` (example for user reference)

- [ ] **Step 1: Create example hooks settings**

Create `.claude/settings.json` with the hooks configuration:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python -c \"import json,time,os; open(os.path.join(os.environ['USERPROFILE'],'.claude-traffic-light-status.json'),'w').write(json.dumps({'state':'coding','timestamp':int(time.time())}))\""
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python -c \"import json,time,os; open(os.path.join(os.environ['USERPROFILE'],'.claude-traffic-light-status.json'),'w').write(json.dumps({'state':'waiting','timestamp':int(time.time())}))\""
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python -c \"import json,time,os; open(os.path.join(os.environ['USERPROFILE'],'.claude-traffic-light-status.json'),'w').write(json.dumps({'state':'done','timestamp':int(time.time())}))\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add .claude/settings.json
git commit -m "feat: example Claude Code hooks configuration"
```

---

### Task 9: Final integration test and cleanup

**Files:**
- Review: `traffic_light.py` (final review)
- Remove: any leftover test branches

- [ ] **Step 1: End-to-end test with actual Claude Code hooks**

1. Copy hooks from `.claude/settings.json` into the user's actual Claude Code settings
2. Start traffic light: `python traffic_light.py`
3. Run a Claude Code session
4. Verify: green when coding, yellow when waiting for input, red when done
5. Verify: sound plays, notifications appear, timer counts up
6. Verify: dragging position persists after restart
7. Verify: tray menu toggles work

- [ ] **Step 2: Remove any test-only code branches**

Clean up the `--test-ui` and `--test-tray` branches if desired, or keep them for future debugging.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup and integration test"
```
