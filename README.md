# Claude Code Traffic Light

Windows 桌面上的 Claude Code 状态指示器，HUD 科幻面板风格。

![](https://img.shields.io/badge/platform-Windows-blue) ![](https://img.shields.io/badge/python-3.8+-green) ![](https://img.shields.io/badge/license-MIT-yellow)

## 预览

四种状态自动切换：

| 状态 | 颜色 | 触发时机 |
|------|------|---------|
| 思考中 | 蓝色 | 用户发送消息时 |
| 编码中 | 绿色 | Claude 调用工具时 |
| 等待操作 | 黄色 | 需要用户审批/输入时 |
| 完成 | 红色 | Claude 结束任务时 |

## 功能

- **HUD 科幻面板** — 菱形指示灯 + 扫描线动画 + 呼吸灯效果
- **系统托盘图标** — 颜色实时跟随状态变化
- **声纳音效** — 编码时循环播放潜水艇声纳声，离开电脑也能感知状态
- **Windows 通知** — 等待操作和完成时弹出通知 + 提示音
- **设置面板** — 透明度、闪烁速度、点击穿透、声音/通知/声纳开关
- **Hook 管理** — 一键安装/更新 Claude Code Hooks
- **拖拽定位** — 悬浮窗可拖到任意位置，位置自动保存
- **耗时统计** — 实时显示当前状态持续时间

## 快速开始

### 从源码运行

```bash
git clone https://github.com/Etshanyu/claude_code-_traffic-_light.git
cd claude-code-traffic-light
pip install -r requirements.txt
python traffic_light.py
```

### 直接下载 EXE

前往 [Releases](../../releases) 下载 `ClaudeTrafficLight.exe`，双击运行。

## 配置 Hooks

首次运行后，右键托盘图标 → **设置** → **Claude Code Hooks** 区域点击 **安装 Hooks**。

这会自动向 `~/.claude/settings.json` 写入以下 Hook 配置：

| Hook 事件 | 写入状态 |
|-----------|---------|
| `UserPromptSubmit` | thinking（思考中） |
| `PostToolUse` | coding（编码中） |
| `Notification` | waiting（等待操作） |
| `Stop` | done（完成） |

安装后，**所有项目**的 Claude Code 会话都会自动同步状态到指示器，无需逐个项目配置。

## 打包 EXE

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name "ClaudeTrafficLight" --add-data "sonar.wav;." traffic_light.py
```

生成的 exe 在 `dist/` 目录。

## 项目结构

```
├── traffic_light.py              # 主程序（单文件，约 600 行）
├── sonar.wav     # 声纳音效
├── requirements.txt              # Python 依赖
├── .gitignore
└── README.md
```

## 依赖

- Python 3.8+
- tkinter（Python 内置）
- winotify — Windows 通知（唯一外部依赖）
- ctypes / winsound（Python 内置）— Win32 托盘图标 + WAV 音效

## 原理

```
Claude Code Hooks（写入状态文件）
        ↓
~/.claude-traffic-light-status.json
        ↓
Python App（文件轮询监听）
        ↓
├── tkinter HUD 悬浮面板
├── Win32 API 系统托盘
├── winsound 声纳音效 + 提示音
└── winotify Windows 通知
```

## License

MIT
