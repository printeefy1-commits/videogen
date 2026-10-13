import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.studio_editor import EditOptions, edit_video, probe_video
from app.utils import utils


@pytest.fixture
def source_video(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and FFprobe are required for video behavior tests")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        timeout=30,
    )
    monkeypatch.setattr(
        utils, "storage_dir", lambda sub_dir="", create=False: str(tmp_path / sub_dir)
    )
    return source


def test_trim_speed_crop_audio_and_overlay_are_real(source_video):
    original = source_video.read_bytes()
    output = edit_video(
        source_video,
        EditOptions(
            start=0.5,
            end=2.5,
            speed=2,
            aspect="1:1",
            caption="100% free: it's your story",
            saturation=0.5,
        ),
    )
    info = probe_video(output)
    assert info["width"] == info["height"] == 240
    assert info["duration"] == pytest.approx(1.0, abs=0.15)
    assert info["audio"]
    assert source_video.read_bytes() == original
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"],
        check=True,
        timeout=30,
    )
    assert not (output.parent / "caption.txt").exists()


def test_mute_and_slow_export(source_video):
    output = edit_video(
        source_video, EditOptions(start=0, end=1, speed=0.25, mute=True)
    )
    info = probe_video(output)
    assert not info["audio"]
    assert info["duration"] == pytest.approx(4.0, abs=0.2)


def test_out_of_bounds_and_external_file_are_rejected(source_video, tmp_path):
    with pytest.raises(ValueError, match="within"):
        edit_video(source_video, EditOptions(end=10))
    with pytest.raises(ValueError):
        edit_video(Path("/etc/passwd"), EditOptions())
    assert not list(tmp_path.glob("studio_edits/*/edited.mp4"))


@pytest.mark.parametrize(
    "options",
    [
        {"start": 2, "end": 1},
        {"speed": float("nan")},
        {"end": float("inf")},
        {"speed": 0},
        {"caption": "x" * 181},
    ],
)
def test_invalid_options(options):
    with pytest.raises(ValidationError):
        EditOptions(**options)
