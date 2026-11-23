"""Capture real dashboard/Grafana screenshots, a demo GIF and a battle video.

Optional developer utility. Not part of CI and not needed to run the project.
Requires: pip install playwright Pillow imageio-ffmpeg, plus Microsoft Edge.

By default this records a live battle and the live Grafana dashboard, so it
needs the Kind lab and Prometheus port-forward. ``--offline`` refreshes the
dashboard PNG, GIF and MP4 from the committed evidence in the running UI
instead; it never runs a battle and never fabricates metrics.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
FRAMES = SHOTS / "_frames"
VIDEO_TMP = SHOTS / "_video"
BASE = "http://127.0.0.1:5173"
GRAFANA = "http://127.0.0.1:3000"

SHOTS.mkdir(parents=True, exist_ok=True)
FRAMES.mkdir(exist_ok=True)
VIDEO_TMP.mkdir(exist_ok=True)


def frame(page, name: str) -> None:
    page.screenshot(path=str(FRAMES / f"{name}.png"))
    print(f"  frame: {name}", flush=True)


def fill_battle_form(page) -> None:
    # network-latency is the sustained fault the Defender reliably detects, so
    # the recording shows a real detect -> diagnose -> repair -> PROMOTE loop.
    page.locator("select").first.select_option("network-latency")
    inputs = page.locator("input")
    inputs.nth(0).fill("payment-service")   # target
    inputs.nth(1).fill("30")                # duration
    inputs.nth(2).fill("45")                # settle
    inputs.nth(3).fill("70")                # threshold (PROMOTE boundary)
    inputs.nth(4).fill("release-candidate")  # version


def wait_for_battle(page) -> None:
    page.wait_for_function(
        "() => { const b = [...document.querySelectorAll('button')]"
        ".find(x => x.textContent.includes('Run battle')); return b && !b.disabled; }",
        timeout=180000,
    )
    page.wait_for_selector("text=Last battle:", timeout=15000)


def build_gif() -> Path:
    paths = sorted(FRAMES.glob("*.png"))
    images = [Image.open(path).convert("RGB").resize((960, 600)) for path in paths]
    if not images:
        raise RuntimeError("no frames captured")
    out = SHOTS / "demo.gif"
    images[0].save(
        out,
        save_all=True,
        append_images=images[1:],
        duration=1600,
        loop=0,
        optimize=True,
    )
    return out


def convert_video(webm: Path) -> Path | None:
    import imageio_ffmpeg

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    out = SHOTS / "demo.mp4"
    for codec in (["-c:v", "libx264", "-pix_fmt", "yuv420p"], ["-c:v", "mpeg4"]):
        result = subprocess.run(
            [exe, "-y", "-loglevel", "error", "-i", str(webm), *codec,
             "-movflags", "+faststart", str(out)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return out
    print("  video conversion failed:", result.stderr[-400:])
    return None


def capture_grafana(browser) -> Path:
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    page.goto(f"{GRAFANA}/login", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("input[name=user]", timeout=30000)
    page.fill("input[name=user]", "admin")
    page.fill("input[name=password]", "admin")
    page.get_by_role("button", name="Log in").click()
    skip = page.get_by_role("button", name="Skip")
    if skip.count():
        skip.click()
    page.wait_for_timeout(2000)

    page.goto(f"{GRAFANA}/api/search?query=ChaosArena", wait_until="load", timeout=30000)
    results = json.loads(page.locator("body").inner_text())
    match = next((r for r in results if r.get("title") == "ChaosArena - ShopApp Live"), results[0])
    uid = match["uid"]
    print(f"  grafana dashboard uid: {uid}", flush=True)

    page.goto(
        f"{GRAFANA}/d/{uid}/shopapp?from=now-1h&to=now&kiosk=tv",
        wait_until="networkidle",
        timeout=60000,
    )
    page.wait_for_timeout(8000)
    out = SHOTS / "grafana.png"
    page.screenshot(path=str(out), full_page=True)
    context.close()
    return out


def reset_capture_dirs() -> None:
    """Never mix frames or raw recordings from an earlier capture."""
    shutil.rmtree(FRAMES, ignore_errors=True)
    shutil.rmtree(VIDEO_TMP, ignore_errors=True)
    FRAMES.mkdir(exist_ok=True)
    VIDEO_TMP.mkdir(exist_ok=True)


def finish_recording(page) -> None:
    """Write the GIF and MP4 from this run's frames and raw video."""
    video = page.video
    page.context.close()
    webm = Path(video.path()) if video else None

    gif = build_gif()
    print(f"GIF: {gif} ({gif.stat().st_size // 1024} KiB)", flush=True)
    if webm and webm.exists():
        mp4 = convert_video(webm)
        if mp4:
            print(f"VIDEO: {mp4} ({mp4.stat().st_size // 1024} KiB)", flush=True)
        shutil.rmtree(VIDEO_TMP, ignore_errors=True)


def capture_current_ui(browser) -> None:
    """Refresh the dashboard assets from committed evidence; no live battle."""
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        record_video_dir=str(VIDEO_TMP),
        record_video_size={"width": 1440, "height": 900},
    )
    page = context.new_page()
    page.goto(BASE, wait_until="networkidle", timeout=60000)
    page.wait_for_selector("text=Release gate", timeout=30000)
    page.wait_for_function(
        "() => { const m = document.querySelector('.topright .mode')?.textContent || ''; "
        "return m && !m.includes('CHECKING'); }",
        timeout=30000,
    )
    status = page.locator(".topright .mode").inner_text()
    print(f"  dashboard status: {status}", flush=True)
    if "API ONLINE" not in status:
        raise RuntimeError(f"refusing to capture an offline dashboard: {status}")
    page.wait_for_timeout(1200)

    frame(page, "01_current_overview")
    page.screenshot(path=str(SHOTS / "dashboard.png"), full_page=True)

    page.locator("#battle").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    frame(page, "02_current_battle")

    page.locator("#evidence").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    frame(page, "03_current_evidence")

    page.locator(".rl-panel").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    frame(page, "04_current_rl")

    page.locator("#history").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    frame(page, "05_current_history")

    page.locator(".report").scroll_into_view_if_needed()
    page.wait_for_timeout(900)
    frame(page, "06_current_report")

    finish_recording(page)


def capture_live_demo(browser) -> None:
    """Record a real battle and the live Grafana dashboard (needs the lab)."""
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        record_video_dir=str(VIDEO_TMP),
        record_video_size={"width": 1440, "height": 900},
    )
    page = context.new_page()
    page.goto(BASE, wait_until="networkidle", timeout=60000)
    page.wait_for_selector("text=Release gate", timeout=30000)
    page.wait_for_timeout(3000)

    frame(page, "01_dashboard")
    page.screenshot(path=str(SHOTS / "dashboard.png"), full_page=True)

    fill_battle_form(page)
    frame(page, "02_form_filled")
    page.get_by_role("button", name="Run battle").click()
    frame(page, "03_battling")

    for index in range(8):
        page.wait_for_timeout(7000)
        frame(page, f"04_battle_{index + 1}")

    wait_for_battle(page)
    page.wait_for_timeout(1500)
    frame(page, "05_result")

    page.locator("#evidence").scroll_into_view_if_needed()
    page.wait_for_timeout(1200)
    frame(page, "06_evidence")
    page.locator(".rl-panel").scroll_into_view_if_needed()
    page.wait_for_timeout(1200)
    frame(page, "07_rl_panel")
    page.locator("#history").scroll_into_view_if_needed()
    page.wait_for_timeout(1200)
    frame(page, "08_history")
    page.locator(".report").scroll_into_view_if_needed()
    page.wait_for_timeout(1200)
    frame(page, "09_report")

    finish_recording(page)

    grafana = capture_grafana(browser)
    print(f"GRAFANA: {grafana} ({grafana.stat().st_size // 1024} KiB)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="refresh dashboard PNG/GIF/MP4 from committed evidence (no battle, no Grafana)",
    )
    args = parser.parse_args()
    reset_capture_dirs()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        if args.offline:
            capture_current_ui(browser)
            print("OFFLINE CAPTURE COMPLETE", flush=True)
        else:
            capture_live_demo(browser)
            print("LIVE CAPTURE COMPLETE", flush=True)
        browser.close()

    shutil.rmtree(FRAMES, ignore_errors=True)


if __name__ == "__main__":
    main()
