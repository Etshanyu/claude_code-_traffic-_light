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
    write_status("coding", "test")
    result = read_status()
    assert result["state"] == "coding"
    print(f"Status file OK: {STATUS_FILE}")
    print(f"Result: {result}")
