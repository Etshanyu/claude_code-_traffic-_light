# Claude Code Traffic Light - Windows Desktop Status Indicator

## Overview

A lightweight Windows desktop tool that displays Claude Code's running status as a traffic light indicator. Runs as a system tray app with a floating capsule-shaped widget, driven by Claude Code Hooks.

## Architecture

```
Claude Code Hooks (写入 status.json)
        ↓
  status.json  (状态桥梁文件)
        ↓
  traffic_light.py (watchdog 监听文件变化)
        ↓
  ├── tkinter 浮动胶囊窗口 (呼吸灯动画)
  ├── pystray 系统托盘图标 (变色)
  ├── winsound 声音提醒
  └── win10toast Windows 通知
```

## States

| State | Color | Label | Light Effect | Sound | Notification |
|-------|-------|-------|-------------|-------|-------------|
| `coding` | Green (#27ae60) | 编码中 | 呼吸灯慢闪(2s周期) | 无 | 无 |
| `waiting` | Yellow (#f39c12) | 等待操作 | 呼吸灯快闪(1s周期) | Asterisk系统音 | "Claude Code 需要你的操作" |
| `done` | Red (#e74c3c) | 编码完成 | 常亮 | Exclamation系统音 | "Claude Code 编码完成，耗时 XX:XX" |

## Claude Code Hooks Configuration

Hooks are configured in `.claude/settings.json`. Each hook writes a JSON status file.

### Hook events

- **PostToolUse** → state: `coding` (Claude is actively working)
- **Notification** → state: `waiting` (needs user action)
- **Stop** → state: `done` (task complete)

### Status file format

Path: `~/.claude-traffic-light-status.json`

```json
{
  "state": "coding",
  "timestamp": 1780031425,
  "message": "optional context"
}
```

Each hook executes a simple command that writes this file:

```json
{
  "hooks": {
    "PostToolUse": [{
      "command": "python -c \"import json,time; open('%USERPROFILE%/.claude-traffic-light-status.json','w').write(json.dumps({'state':'coding','timestamp':int(time.time())}))\""
    }],
    "Notification": [{
      "command": "python -c \"import json,time; open('%USERPROFILE%/.claude-traffic-light-status.json','w').write(json.dumps({'state':'waiting','timestamp':int(time.time())}))\""
    }],
    "Stop": [{
      "command": "python -c \"import json,time; open('%USERPROFILE%/.claude-traffic-light-status.json','w').write(json.dumps({'state':'done','timestamp':int(time.time())}))\""
    }]
  }
}
```

## UI Design

### Floating Capsule Widget

- Style: Minimal capsule (pill shape), white background, light shadow
- Layout: `[colored dot] [status text] [elapsed time]`
- Size: Compact, ~160x36px
- Position: Default top-right corner of screen
- Draggable: Yes, user can drag to any position
- Position persistence: Saved to config file, restored on restart
- Always on top: Yes
- Frameless: Yes (no title bar)

### Breathing Light Animation

- Implemented via tkinter's `after()` method cycling the dot's opacity
- coding: slow breathe (2s period)
- waiting: fast breathe (1s period)
- done: solid (no animation)
- Frequency adjustable via tray menu (fast/medium/slow presets)

### System Tray

- Icon color matches current state (green/yellow/red dot)
- Right-click menu:
  - Current status display (disabled item)
  - Sound: On/Off toggle
  - Notification: On/Off toggle
  - Blink speed: Fast / Medium / Slow
  - Exit

### Elapsed Timer

- App maintains a `session_start` timestamp, set when first `coding` event is received after launch or after a `done` state
- Displays current state duration in MM:SS format next to status text
- On `done` state: shows total session time (`session_start` → now)

## Sound & Notifications

- Sound: `winsound.MessageBeep()` — Asterisk for waiting, Exclamation for done
- Notifications: `win10toast.ToastNotifier` — 3 second duration
- Both toggleable via tray menu
- No sound or notification on `coding` state

## Dependencies

- Python 3.8+
- `tkinter` (built-in) — UI
- `pystray` — system tray icon
- `Pillow` — generate tray icon images programmatically
- `watchdog` — file change monitoring
- `win10toast` — Windows toast notifications
- `winsound` (built-in) — system sounds

## File Structure

Single file: `traffic_light.py`

```
green/
├── traffic_light.py          # Main application (single file)
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-05-29-traffic-light-design.md
├── README.md                 # Usage instructions
└── requirements.txt          # pip dependencies
```

## Distribution

- Run directly: `python traffic_light.py`
- Package as exe: `pyinstaller --onefile --noconsole traffic_light.py`
- No external assets needed (tray icons generated in code)
