"""Real local video edits using FFmpeg, with no external provider calls."""

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from app.utils import file_security, utils


class EditOptions(BaseModel):
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    speed: float = Field(default=1, ge=0.25, le=4, allow_inf_nan=False)
    aspect: Literal["Original", "9:16", "16:9", "1:1"] = "Original"
    brightness: float = Field(default=0, ge=-0.5, le=0.5, allow_inf_nan=False)
    saturation: float = Field(default=1, ge=0, le=2, allow_inf_nan=False)
    volume: float = Field(default=1, ge=0, le=2, allow_inf_nan=False)
    mute: bool = False
    caption: str = Field(default="", max_length=180)
    caption_position: Literal["Top", "Center", "Bottom"] = "Bottom"

    @model_validator(mode="after")
    def validate_range(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError("Trim end must be after trim start")
        return self


def probe_video(source: str | Path) -> dict:
    executable = shutil.which("ffprobe")
    if not executable:
        raise RuntimeError("FFprobe is required; install the FFmpeg system package")
    result = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise ValueError("The file could not be read as a video")
    payload = json.loads(result.stdout)
    stream = next(
        (s for s in payload.get("streams", []) if s.get("codec_type") == "video"), None
    )
    if not stream:
        raise ValueError("The file has no video track")
    duration = float(
        payload.get("format", {}).get("duration") or stream.get("duration") or 0
    )
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("The video must have a finite, positive duration")
    width, height = int(stream["width"]), int(stream["height"])
    rotation = next(
        (
            s.get("rotation", 0)
            for s in stream.get("side_data_list", [])
            if "rotation" in s
        ),
        0,
    )
    if abs(int(rotation)) % 180 == 90:
        width, height = height, width
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "audio": any(
            s.get("codec_type") == "audio" for s in payload.get("streams", [])
        ),
    }


def _tempo_filters(speed: float) -> list[str]:
    filters = []
    while speed < 0.5:
        filters.append("atempo=0.5")
        speed /= 0.5
    while speed > 2:
        filters.append("atempo=2")
        speed /= 2
    filters.append(f"atempo={speed:.6f}")
    return filters


def _filter_path(path: Path) -> str:
    # All captions/fonts are server-chosen paths, never text interpolated into a filter.
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "'\\''")


def edit_video(
    source: str | Path, options: EditOptions, output_root: Path | None = None
) -> Path:
    storage = utils.storage_dir()
    source = file_security.resolve_path_within_directory(storage, str(source))
    info = probe_video(source)
    end = options.end if options.end is not None else info["duration"]
    if end > info["duration"] + 0.05 or options.start >= info["duration"]:
        raise ValueError("Trim range must be within the source video")
    duration = min(end, info["duration"]) - options.start
    if duration > 300:
        raise ValueError("Please trim to five minutes or less for each export")
    output_root = output_root or Path(utils.storage_dir("studio_edits"))
    job_dir = output_root / uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=False)
    pending = job_dir / "pending.mp4"
    output = job_dir / "edited.mp4"
    filters = [f"setpts=(PTS-STARTPTS)/{options.speed:.6f}"]
    width, height = info["width"], info["height"]
    if options.aspect != "Original":
        horizontal, vertical = map(int, options.aspect.split(":"))
        ratio = horizontal / vertical
        if width / height > ratio:
            width = int(height * ratio)
        else:
            height = int(width / ratio)
        width, height = max(2, width // 2 * 2), max(2, height // 2 * 2)
        filters.append(f"crop={width}:{height}")
    scale = min(1.0, 1920 / max(width, height))
    width, height = (
        max(2, int(width * scale) // 2 * 2),
        max(2, int(height * scale) // 2 * 2),
    )
    filters.extend(
        [
            f"scale={width}:{height}",
            "setsar=1",
            f"eq=brightness={options.brightness:.3f}:saturation={options.saturation:.3f}",
        ]
    )
    if options.caption.strip():
        text_file = job_dir / "caption.txt"
        text_file.write_text(options.caption.strip(), encoding="utf-8")
        font = Path(utils.root_dir()) / "resource/fonts/BeVietnamPro-Bold.ttf"
        y = {"Top": "h*0.1", "Center": "(h-text_h)/2", "Bottom": "h-text_h-h*0.1"}[
            options.caption_position
        ]
        filters.append(
            f"drawtext=fontfile='{_filter_path(font)}':textfile='{_filter_path(text_file)}':expansion=none:"
            f"fontsize={max(14, int(width * 0.045))}:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=12:x=(w-text_w)/2:y={y}"
        )
    command = [
        utils.get_ffmpeg_binary() or "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-ss",
        f"{options.start:.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        source,
        "-map",
        "0:v:0",
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-threads",
        "2",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-movflags",
        "+faststart",
    ]
    if info["audio"] and not options.mute:
        command.extend(
            [
                "-map",
                "0:a:0",
                "-af",
                ",".join(
                    _tempo_filters(options.speed) + [f"volume={options.volume:.3f}"]
                ),
                "-c:a",
                "aac",
                "-b:a",
                "128k",
            ]
        )
    else:
        command.append("-an")
    command.append(str(pending))
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=600, check=False
        )
        if result.returncode:
            raise RuntimeError(
                "FFmpeg could not export this edit. " + result.stderr[-1200:]
            )
        probe_video(pending)
        pending.replace(output)
        return output
    except Exception:
        pending.unlink(missing_ok=True)
        raise
    finally:
        (job_dir / "caption.txt").unlink(missing_ok=True)
