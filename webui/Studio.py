"""Videogen: a no-paid-provider studio built on MoneyPrinterTurbo."""
# Streamlit executes this file with webui/ as the script root.
# ruff: noqa: E402

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
sys.path.insert(0, str(ROOT))

from app.config import config
from app.models import const
from app.models.schema import MaterialInfo, VideoParams
from app.services import freellm, llm, material_upload, webui_task
from app.services import state as sm
from app.services.studio_editor import EditOptions, edit_video, probe_video


st.set_page_config(
    page_title="Videogen · Create your next story", page_icon="✦", layout="wide"
)
st.markdown(
    f"<style>{(ROOT / 'webui/studio.css').read_text()}</style>", unsafe_allow_html=True
)


def provider_config():
    return dict(config.app, llm_provider="freellm")


def exports():
    results = []
    for file in (ROOT / "storage/tasks").glob("*/final-*.mp4"):
        if not file.is_file() or file.stat().st_size == 0:
            continue
        title = "Untitled video"
        try:
            metadata = json.loads((file.parent / "script.json").read_text())
            title = metadata.get("params", {}).get("video_subject", title)
        except (OSError, ValueError, TypeError):
            pass
        results.append((title, file))
    for file in (ROOT / "storage/studio_edits").glob("*/edited.mp4"):
        results.append(("Edited video", file))
    return sorted(results, key=lambda item: item[1].stat().st_mtime, reverse=True)


def persist_upload(upload):
    digest = hashlib.sha256(upload.getbuffer()).hexdigest()
    cache = st.session_state.setdefault("upload_cache", {})
    identity = f"{upload.name}:{digest}"
    if identity not in cache:
        saved = material_upload.save_material_upload(upload.name, upload)
        cache[identity] = str(Path(material_upload.uploaded_material_dir()) / saved)
    return cache[identity]


def download(file, key):
    with open(file, "rb") as media:
        st.download_button(
            "Download MP4",
            media,
            file_name=Path(file).name,
            mime="video/mp4",
            key=key,
            use_container_width=True,
        )


def empty_preview():
    st.markdown(
        """<div class="preview-empty"><div class="preview-orb"></div>
        <span class="preview-spark">✦</span><h2>A little idea.<br>A whole new story.</h2>
        <p>Your video will appear here.<br>Start with a script and your own footage.</p>
        <span class="preview-label">MADE WITH VIDEOGEN</span></div>""",
        unsafe_allow_html=True,
    )


@st.fragment(run_every="2s")
def generation_result():
    task_id = st.session_state.get("generation_task")
    if not task_id:
        empty_preview()
        return
    task = sm.state.get_task(task_id) or {}
    status = task.get("state")
    if status == const.TASK_STATE_COMPLETE:
        videos = task.get("videos") or []
        if videos and Path(videos[0]).is_file():
            st.success("Your video is ready")
            st.video(videos[0])
            download(videos[0], f"generated-{task_id}")
            st.caption("Open Edit video to refine this export.")
        else:
            st.warning(
                "The task completed without a playable export. Check the render log."
            )
    elif status == const.TASK_STATE_FAILED:
        st.error(task.get("error", "Video generation failed. Check the render log."))
    else:
        st.info("Building your video… You can leave this page while it renders.")
        st.progress(min(100, max(0, int(task.get("progress", 0)))))
    if task.get("warnings"):
        st.warning("Some requested effects could not be applied. See the render log.")
    with st.expander("Render log"):
        st.code(
            "\n".join(webui_task.get_task_logs(task_id)[-25:])
            or "Waiting for the renderer…",
            language=None,
        )


def create_page():
    st.markdown(
        '<p class="eyebrow">YOUR CREATIVE WORKSPACE</p>', unsafe_allow_html=True
    )
    st.title("Big ideas. Short videos.")
    st.markdown("Turn your words and footage into something worth watching.")
    st.markdown(
        '<div class="info-strip"><span>✦ FreeLLMAPI scripts</span><span>◈ Your own footage</span><span>↗ Local MP4 exports</span></div>',
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.subheader("01  Tell your story")
        topic = st.text_input(
            "Video topic",
            placeholder="A small adventure. A big discovery.",
            max_chars=250,
            key="video_topic",
        )
        template_cols = st.columns(3)
        topics = ["A travel story", "Three useful tips", "My product launch"]
        for column, text in zip(template_cols, topics):
            column.button(
                text,
                on_click=lambda value=text: st.session_state.update(video_topic=value),
                use_container_width=True,
            )
        language = st.selectbox(
            "Script language",
            ["English", "French", "Spanish", "Hindi", "Portuguese", "Arabic"],
        )
        if st.button(
            "✦ Write with FreeLLMAPI", use_container_width=True, key="write_script"
        ):
            try:
                status = freellm.configuration_status(provider_config())
                if not all(status.values()):
                    st.error(
                        "Open API settings and configure the FreeLLMAPI base URL, model, and key first. You can also write the script yourself."
                    )
                elif not topic.strip():
                    st.error("Add a video topic first.")
                else:
                    with st.spinner("Finding the right words…"):
                        script = llm.generate_script(
                            topic,
                            language=language,
                            paragraph_number=1,
                            video_script_prompt="Write a concise short-video script, 35 to 65 words. Return only the narration, with no stage directions.",
                            app_config=provider_config(),
                        )
                    if not script or script.startswith("Error:"):
                        st.error(
                            "The provider could not generate a script. Check the connection in API settings."
                        )
                    else:
                        st.session_state["video_script"] = script
            except ValueError as error:
                st.error(str(error))
        script = st.text_area(
            "Your script",
            height=155,
            placeholder="Write your narration here, or let FreeLLMAPI help you get started…",
            key="video_script",
            max_chars=3000,
        )
        st.caption(
            "AI writes the script. MoneyPrinterTurbo assembles your footage into the final video."
        )
        st.subheader("02  Make it yours")
        uploads = st.file_uploader(
            "Add footage or photos",
            type=["mp4", "mov", "webm", "mkv", "jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="generation_uploads",
        )
        st.caption(
            "Use media you own or have permission to use, at least 480 × 480 pixels. No footage API key is needed."
        )
        aspect = (
            st.segmented_control(
                "Video format",
                ["9:16", "16:9", "1:1"],
                default="9:16",
                selection_mode="single",
            )
            or "9:16"
        )
        first, second = st.columns(2)
        narration = first.selectbox(
            "Voiceover",
            [
                "No voice · works offline",
                "English · Aria (Edge TTS)",
                "English · Guy (Edge TTS)",
                "French · Denise (Edge TTS)",
            ],
        )
        subtitles = second.toggle("Add captions", value=True)
        st.caption(
            "Edge TTS requires internet access. Silent video and captions render locally."
        )
        active = sm.state.get_task(st.session_state.get("generation_task", "")) or {}
        busy = active.get("state") == const.TASK_STATE_PROCESSING
        if st.button(
            "Create video  →",
            type="primary",
            use_container_width=True,
            disabled=busy,
            key="create_video",
        ):
            if not script.strip():
                st.error("Write or generate a script first.")
            elif not uploads:
                st.error("Add at least one video or photo to create your video.")
            elif len(uploads) > 12:
                st.error("Use up to 12 media files per video.")
            else:
                try:
                    with st.spinner("Preparing your footage…"):
                        materials = [
                            MaterialInfo(provider="local", url=persist_upload(upload))
                            for upload in uploads
                        ]
                    voices = {
                        "No voice · works offline": "no-voice",
                        "English · Aria (Edge TTS)": "en-US-AriaNeural-Female",
                        "English · Guy (Edge TTS)": "en-US-GuyNeural-Male",
                        "French · Denise (Edge TTS)": "fr-FR-DeniseNeural-Female",
                    }
                    params = VideoParams(
                        video_subject=topic.strip() or script[:60],
                        video_script=script.strip(),
                        video_source="local",
                        video_materials=materials,
                        video_aspect=aspect,
                        video_concat_mode="sequential",
                        voice_name=voices[narration],
                        subtitle_enabled=subtitles,
                        subtitle_provider="edge",
                        auto_publish=False,
                        font_name="BeVietnamPro-Bold.ttf",
                        font_size=48,
                        bgm_type="",
                        bgm_volume=0,
                        n_threads=2,
                    )
                    task_id = str(uuid4())
                    webui_task.submit_generation(task_id, params)
                    st.session_state["generation_task"] = task_id
                except (ValueError, RuntimeError, OSError) as error:
                    st.error(str(error))
    with right:
        st.subheader("Your preview")
        generation_result()
        st.markdown(
            '<div class="small-note"><b>Your workflow, without paid add-ons.</b><br>Upload media → write a script → render locally → edit and download.</div>',
            unsafe_allow_html=True,
        )


def editor_page():
    st.markdown('<p class="eyebrow">THE FINISHING TOUCHES</p>', unsafe_allow_html=True)
    st.title("Make every frame yours.")
    st.write(
        "Trim, reframe, and fine-tune your video. Export a fresh MP4; your original stays intact."
    )
    library = exports()
    source_mode = st.radio(
        "Choose your source", ["Upload a video", "From my library"], horizontal=True
    )
    source = None
    if source_mode == "Upload a video":
        upload = st.file_uploader(
            "Drop your video here",
            type=["mp4", "mov", "webm", "mkv"],
            key="edit_upload",
        )
        if upload:
            try:
                source = persist_upload(upload)
            except (ValueError, RuntimeError) as error:
                st.error(str(error))
    elif library:
        chosen = st.selectbox(
            "Video",
            range(len(library)),
            format_func=lambda index: (
                f"{library[index][0]} · {library[index][1].parent.name[:8]}"
            ),
        )
        source = str(library[chosen][1])
    else:
        st.info("Your library is empty. Create a video first, or upload one here.")
    if not source:
        empty_preview()
        return
    try:
        info = probe_video(source)
    except (ValueError, RuntimeError) as error:
        st.error(str(error))
        return
    left, right = st.columns([1, 1.15], gap="large")
    with right:
        st.video(source)
        st.caption(
            f"{info['width']} × {info['height']}  ·  {info['duration']:.1f} seconds"
        )
    with left:
        with st.form("edit_form"):
            st.subheader("Trim & reframe")
            a, b = st.columns(2)
            start = a.number_input(
                "Start (seconds)",
                min_value=0.0,
                max_value=info["duration"],
                value=0.0,
                step=0.1,
            )
            end = b.number_input(
                "End (seconds)",
                min_value=0.1,
                max_value=max(0.1, info["duration"]),
                value=info["duration"],
                step=0.1,
            )
            aspect = st.selectbox("Crop format", ["Original", "9:16", "16:9", "1:1"])
            speed = st.select_slider(
                "Playback speed",
                options=[0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 4.0],
                value=1.0,
            )
            st.subheader("Color & sound")
            brightness = st.slider(
                "Brightness", min_value=-0.5, max_value=0.5, value=0.0, step=0.05
            )
            saturation = st.slider(
                "Saturation", min_value=0.0, max_value=2.0, value=1.0, step=0.1
            )
            mute = st.checkbox("Mute audio", value=not info["audio"])
            volume = st.slider(
                "Audio volume", min_value=0.0, max_value=2.0, value=1.0, step=0.1
            )
            caption = st.text_area(
                "Text overlay",
                placeholder="Add a title, message, or call to action…",
                max_chars=180,
                height=90,
            )
            position = st.selectbox("Text position", ["Bottom", "Center", "Top"])
            submitted = st.form_submit_button(
                "Export edited video  →", type="primary", use_container_width=True
            )
        if submitted:
            st.session_state.pop("edited_export", None)
            try:
                options = EditOptions(
                    start=start,
                    end=end,
                    aspect=aspect,
                    speed=speed,
                    brightness=brightness,
                    saturation=saturation,
                    mute=mute,
                    volume=volume,
                    caption=caption,
                    caption_position=position,
                )
                with st.spinner("Rendering your edit…"):
                    st.session_state["edited_export"] = str(edit_video(source, options))
            except (ValueError, RuntimeError, OSError) as error:
                st.error(str(error))
    output = st.session_state.get("edited_export")
    if output and Path(output).is_file():
        st.success("Your edited video is ready")
        st.video(output)
        download(output, "edited_download")


def library_page():
    st.markdown(
        '<p class="eyebrow">YOUR CREATIVE COLLECTION</p>', unsafe_allow_html=True
    )
    st.title("All your stories, in one place.")
    library = exports()
    if not library:
        st.info("No exports yet. Your created and edited videos will appear here.")
        empty_preview()
    for start in range(0, len(library), 3):
        for column, (title, file) in zip(st.columns(3), library[start : start + 3]):
            with column:
                st.subheader(title)
                st.video(str(file))
                download(file, f"library-{file.parent.name}-{file.name}")


def settings_page():
    st.markdown('<p class="eyebrow">YOUR API, YOUR CHOICE</p>', unsafe_allow_html=True)
    st.title("Connect FreeLLMAPI.")
    st.write(
        "Use your provider's OpenAI-compatible base URL and model ID. Local models must run on the same machine as this studio. Your key is used by the server to write scripts."
    )
    st.info(
        "FreeLLMAPI is a text-provider integration. Video assembly and editing run locally. Your provider's plan, limits, and hosting costs still apply."
    )
    env_bound = bool(os.getenv("FREELLM_API_KEY"))
    with st.form("freellm_settings"):
        base_url = st.text_input(
            "API base URL",
            value=os.getenv("FREELLM_BASE_URL")
            or config.app.get("freellm_base_url", ""),
            placeholder="Enter the API base URL shown by your model server",
            disabled=bool(os.getenv("FREELLM_BASE_URL")),
        )
        st.caption(
            "HTTP is supported for localhost or loopback IPs on this same machine. Remote providers require HTTPS. A model on your PC is not reachable through the cloud machine's localhost."
        )
        model = st.text_input(
            "Model ID",
            value=os.getenv("FREELLM_MODEL")
            or config.app.get("freellm_model_name", ""),
            placeholder="Exact model name from your provider",
            disabled=bool(os.getenv("FREELLM_MODEL")),
        )
        api_key = st.text_input(
            "API key",
            type="password",
            placeholder="Configured in server environment"
            if env_bound
            else "Leave blank to keep the saved key",
            disabled=env_bound,
        )
        st.caption(
            "The key is never included in exports or committed to Git. Saved keys belong in the private, ignored config.toml file."
        )
        if st.form_submit_button("Save connection", type="primary"):
            candidate = dict(
                config.app,
                freellm_base_url=base_url.strip(),
                freellm_model_name=model.strip(),
            )
            if api_key.strip():
                candidate["freellm_api_key"] = api_key.strip()
            try:
                status = freellm.configuration_status(candidate)
                if not all(status.values()):
                    st.error("A base URL, model ID, and API key are required.")
                else:
                    for name in (
                        "freellm_base_url",
                        "freellm_model_name",
                        "freellm_api_key",
                    ):
                        if name in candidate:
                            config.update_config_nonblocking(
                                config.app, name, candidate[name]
                            )
                    config.try_save_config()
                    st.success("Connection settings saved.")
            except ValueError as error:
                st.error(str(error))
    if st.button("Test connection", key="test_freellm"):
        with st.spinner("Checking the provider…"):
            response = llm._generate_response(
                "Reply with exactly: OK", app_config=provider_config()
            )
        if response.startswith("Error:"):
            st.error(response)
        else:
            st.success("Connection successful. Your provider returned a text response.")
    st.subheader("A free-service workflow")
    st.write(
        "Use your own videos or photos, write a script yourself or connect your free-tier LLM, and choose no voice for an offline render. Edge TTS is an optional online voiceover. The studio never routes to a paid video or image model."
    )
    st.caption(
        "This inherited application is a personal studio. Add access control before sharing a hosted instance with other people."
    )


with st.sidebar:
    st.markdown(
        '<div class="sidebar-logo">✦ <span>videogen</span><small>STUDIO</small></div>',
        unsafe_allow_html=True,
    )
    st.caption("A space for your next story.")
    page = st.radio(
        "Workspace",
        ["Create video", "Edit video", "My library", "API settings"],
        label_visibility="collapsed",
    )
    st.divider()
    st.markdown("**Made to be yours.**")
    st.caption("Open source. Local rendering. No paid video providers.")
    st.markdown(
        "[Built on MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)"
    )
    st.caption("MIT licensed · Harry & contributors")

{
    "Create video": create_page,
    "Edit video": editor_page,
    "My library": library_page,
    "API settings": settings_page,
}[page]()
