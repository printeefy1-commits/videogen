"""Exercise upstream generation and new editing without internet/provider calls."""
# Make direct execution from scripts/ resolve the repository's app package.
# ruff: noqa: E402

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.schema import MaterialInfo, VideoParams
from app.services import llm, material_upload, task
from app.services.studio_editor import EditOptions, edit_video, probe_video
from app.utils import utils


def main():
    directory = Path(utils.storage_dir("studio_smoke", create=True))
    source = directory / "test-footage.mp4"
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
            "testsrc2=size=960x540:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:sample_rate=44100",
            "-t",
            "4",
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
    with source.open("rb") as upload:
        stored = material_upload.save_material_upload("test-footage.mp4", upload)
    source = Path(material_upload.uploaded_material_dir()) / stored
    task_id = f"studio-smoke-{uuid4().hex[:10]}"
    params = VideoParams(
        video_subject="Studio verification",
        video_script="Your story starts here. Make every frame count.",
        video_source="local",
        video_materials=[MaterialInfo(provider="local", url=str(source))],
        video_aspect="16:9",
        video_concat_mode="sequential",
        video_clip_duration=4,
        voice_name="no-voice",
        subtitle_enabled=True,
        subtitle_provider="edge",
        auto_publish=False,
        font_name="BeVietnamPro-Bold.ttf",
        font_size=48,
        bgm_type="",
        bgm_volume=0,
        n_threads=2,
    )

    # Any unexpected LLM invocation makes this supposedly offline workflow fail.
    def no_provider(*args, **kwargs):
        raise AssertionError("Offline generation unexpectedly called an LLM")

    original = llm._generate_response
    try:
        llm._generate_response = no_provider
        result = task.start(task_id, params)
    finally:
        llm._generate_response = original
    if not result or not result.get("videos"):
        raise RuntimeError(f"Generation did not produce a video: {result}")
    generated = Path(result["videos"][0])
    info = probe_video(generated)
    assert info["width"] == 1920 and info["height"] == 1080
    subtitle = Path(utils.task_dir(task_id)) / "subtitle.srt"
    assert subtitle.is_file() and "Your story" in subtitle.read_text()
    edited = edit_video(
        generated,
        EditOptions(
            start=0,
            end=2,
            speed=2,
            aspect="1:1",
            mute=True,
            caption="Made with Videogen",
        ),
    )
    edited_info = probe_video(edited)
    assert edited_info["width"] == edited_info["height"]
    assert not edited_info["audio"] and 0.85 < edited_info["duration"] < 1.15
    for file in (generated, edited):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(file), "-f", "null", "-"],
            check=True,
            timeout=60,
        )
    print(
        json.dumps(
            {
                "generation": "passed",
                "captions": "passed",
                "editing": "passed",
                "full_decode": "passed",
                "generated": str(generated),
                "edited": str(edited),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
