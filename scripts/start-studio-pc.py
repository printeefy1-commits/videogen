"""Start the studio on the same PC as a local model, on Windows/macOS/Linux."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(root / "webui/Studio.py"),
        "--server.address",
        os.getenv("STUDIO_HOST", "127.0.0.1"),
        "--server.port",
        os.getenv("STUDIO_PORT", "8501"),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--theme.base",
        "light",
        "--theme.primaryColor",
        "#7256ed",
    ]
    try:
        return subprocess.run(command, cwd=root, check=False).returncode
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
