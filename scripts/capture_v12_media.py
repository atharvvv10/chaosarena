"""Capture NEW v1.2 dashboard media without touching the v1.1 assets.

Optional developer utility. Not part of CI. Requires the same local tools as
``scripts/capture_demo.py``: Playwright, Pillow, imageio-ffmpeg and Microsoft
Edge, plus the running gate API on 127.0.0.1:8080 and dashboard on 5173.

This is an offline capture: it records the current UI from committed evidence,
never runs a battle and never calls an LLM. It writes only ``v12_*`` files so
the frozen v1.1 ``demo.gif``, ``demo.mp4``, ``dashboard.png`` and
``grafana.png`` remain untouched.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
FRAMES = SHOTS / "_v12_frames"
VIDEO_TMP = SHOTS / "_v12_video"
BASE = "http://127.0.0.1:5173"

DASH_PNG = SHOTS / "v12_dashboard.png"
AI_PNG = SHOTS / "v12_ai_reasoning.png"
GIF = SHOTS / "v12_demo.gif"
MP4 = SHOTS / "v12_demo.mp4"


def reset_capture_dirs() -> None:
    """Never mix frames or raw video from an earlier v1.2 capture."""
    shutil.rmtree(FRAMES, ignore_errors=True)
    shutil.rmtree(VIDEO_TMP, ignore_errors=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    VIDEO_TMP.mkdir(parents=True, exist_ok=True)


def frame(page, name: str) -> None:
    page.screenshot(path=str(FRAMES / f"{name}.png"))
    print(f"  frame: {name}", flush=True)


def wait_until_ready(page) -> None:
    page.goto(BASE, wait_until="networkidle", timeout=60000)
    page.wait_for_selector("text=Release gate", timeout=30000)
    page.wait_for_function(
        "() => { const m = document.querySelector('.topright .mode')?.textContent || ''; "
        "return m && !m.includes('CHECKING'); }",
        timeout=30000,
    )
    status = page.locator(".topright .mode").inner_text()
    if "API ONLINE" not in status:
        raise RuntimeError(f"refusing to capture an offline dashboard: {status}")
    page.wait_for_function(
        "() => document.querySelector('#aireasoning')?.innerText.includes('LIVE EVIDENCE')",
        timeout=30000,
    )
    print(f"  dashboard status: {status}", flush=True)
    page.wait_for_timeout(1200)


def build_gif() -> Path:
    paths = sorted(FRAMES.glob("*.png"))
    images = [Image.open(path).convert("RGB").resize((960, 600)) for path in paths]
    if not images:
        raise RuntimeError("no v1.2 frames captured")
    images[0].save(
        GIF,
        save_all=True,
        append_images=images[1:],
        duration=1500,
        loop=0,
        optimize=True,
    )
    return GIF


def convert_video(webm: Path) -> Path | None:
    import imageio_ffmpeg

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    for codec in (["-c:v", "libx264", "-pix_fmt", "yuv420p"], ["-c:v", "mpeg4"]):
        result = subprocess.run(
            [exe, "-y", "-loglevel", "error", "-i", str(webm), *codec,
             "-movflags", "+faststart", str(MP4)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return MP4
    print("  video conversion failed:", result.stderr[-400:])
    return None


def finish_recording(page) -> None:
    """Write the v1.2 GIF and MP4 from this run only."""
    video = page.video
    page.context.close()
    webm = Path(video.path()) if video else None

    gif = build_gif()
    print(f"GIF: {gif} ({gif.stat().st_size // 1024} KiB)", flush=True)
    if webm and webm.exists():
        mp4 = convert_video(webm)
        if mp4:
            print(f"VIDEO: {mp4} ({mp4.stat().st_size // 1024} KiB)", flush=True)


def capture_v12_ui(browser) -> None:
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        record_video_dir=str(VIDEO_TMP),
        record_video_size={"width": 1440, "height": 900},
    )
    page = context.new_page()
    wait_until_ready(page)

    frame(page, "01_v12_overview")
    page.screenshot(path=str(DASH_PNG), full_page=True)
    print(f"DASHBOARD: {DASH_PNG} ({DASH_PNG.stat().st_size // 1024} KiB)", flush=True)

    page.locator("#battle").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    frame(page, "02_v12_battle")

    page.locator("#evidence").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    frame(page, "03_v12_evidence")

    page.locator("#aireasoning").scroll_into_view_if_needed()
    page.wait_for_timeout(1200)
    frame(page, "04_v12_ai_reasoning")
    page.locator("#aireasoning").screenshot(path=str(AI_PNG))
    print(f"AI PANEL: {AI_PNG} ({AI_PNG.stat().st_size // 1024} KiB)", flush=True)

    page.locator("#history").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    frame(page, "05_v12_history")

    page.locator(".report").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    frame(page, "06_v12_report")

    finish_recording(page)


def main() -> None:
    reset_capture_dirs()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            capture_v12_ui(browser)
        finally:
            browser.close()
    shutil.rmtree(FRAMES, ignore_errors=True)
    shutil.rmtree(VIDEO_TMP, ignore_errors=True)
    print("V12 MEDIA CAPTURE COMPLETE", flush=True)


if __name__ == "__main__":
    main()
