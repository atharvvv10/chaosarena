"""Capture NEW v1.2 AI battle media without touching earlier assets.

Optional developer utility, not part of CI. Requires Playwright, Pillow,
imageio-ffmpeg and Microsoft Edge. It mocks the gate API in the browser, so it
needs no cluster, no running API and no keys. It records the opt-in **AI battle**
flow: checkbox off → checkbox on → fresh Groq/Gemini notes in the AI Reasoning
panel.

This writes only ``v12_ai_battle_*`` files. The frozen v1.1 media and the
earlier ``v12_dashboard.png`` / ``v12_ai_reasoning.png`` / ``v12_demo.*`` are
never overwritten.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
FRAMES = SHOTS / "_v12_ai_battle_frames"
VIDEO_TMP = SHOTS / "_v12_ai_battle_video"
BASE = "http://127.0.0.1:5173"

FORM_PNG = SHOTS / "v12_ai_battle_form.png"
CHECKBOX_PNG = SHOTS / "v12_ai_battle_checkbox.png"
AI_PNG = SHOTS / "v12_ai_battle_reasoning.png"
DASH_PNG = SHOTS / "v12_ai_battle_dashboard.png"
GIF = SHOTS / "v12_ai_battle_demo.gif"
MP4 = SHOTS / "v12_ai_battle_demo.mp4"

NOTE = "Advisory only; the CLI allowlist and classical detector own the real loop."

SAVED_AI = {
    "available": True,
    "source": "saved-validation",
    "generated_at": "2026-11-25T09:30:00+00:00",
    "note": NOTE,
    "battle": {
        "version": "v1.2-deep-aiml", "attack": "pod-kill", "target": "order-service",
        "verdict": "PROMOTE", "score": 100, "detected": True,
        "detection_seconds": 15.8, "recovery_seconds": 53.1,
    },
    "attacker": {
        "role": "attacker_strategist", "ok": True, "latency_ms": 1066.1,
        "result": {
            "source": "groq", "attack": "pod-kill", "target": "order-service",
            "duration": 30, "rationale": "Saved Groq idea from the isolated v1.2 live battle.",
        },
    },
    "defender_preflight": {
        "role": "defender_analyst", "ok": True, "latency_ms": 6973.2,
        "result": {
            "source": "gemini", "category": "chaos-engineering", "confidence": 1.0,
            "rationale": "Saved Gemini preflight for the controlled pod-kill.",
            "recommended_action": "Monitor order-service recovery metrics.",
        },
    },
    "dqn": {
        "role": "dqn_attacker", "ok": True, "latency_ms": 27.4,
        "result": [{"action": "pod-kill@order-service", "q": 4.881329}],
    },
    "defender_post": {
        "role": "defender_post_analysis", "ok": True, "latency_ms": 1468.9,
        "result": {
            "source": "gemini", "category": "resilience_failure", "confidence": 1.0,
            "rationale": "Saved Gemini post-battle reading after 15.8 s detection.",
            "recommended_action": "Review recovery timing before promotion.",
        },
    },
    "report": {"backend": "groq", "chars": 1302, "saved_to": "ml/deep/live/incident_report.md"},
}

FRESH_AI = {
    **SAVED_AI,
    "source": "fresh-battle",
    "generated_at": "2026-11-25T10:00:00+00:00",
    "battle": {
        "version": "release-candidate", "attack": "network-latency",
        "target": "payment-service", "verdict": "PROMOTE", "score": 100,
        "detected": True, "detection_seconds": 13.3, "recovery_seconds": 76.2,
    },
    "attacker": {
        "role": "attacker_strategist", "ok": True, "latency_ms": 842.3,
        "result": {
            "source": "groq", "attack": "network-latency", "target": "payment-service",
            "duration": 30, "rationale": "Fresh Groq idea from the AI battle just completed.",
        },
    },
    "defender_preflight": {
        "role": "defender_analyst", "ok": True, "latency_ms": 1210.5,
        "result": {
            "source": "gemini", "category": "latency_spike", "confidence": 0.97,
            "rationale": "Fresh Gemini preflight for the selected allowlisted fault.",
            "recommended_action": "Watch payment-service latency during the inject window.",
        },
    },
    "dqn": {
        "role": "dqn_attacker", "ok": True, "latency_ms": 19.8,
        "result": [{"action": "network-latency@payment-service", "q": 4.64}],
    },
    "defender_post": {
        "role": "defender_post_analysis", "ok": True, "latency_ms": 998.7,
        "result": {
            "source": "gemini", "category": "latency_spike", "confidence": 0.99,
            "rationale": "Fresh Gemini defence reading: detected in 13.3 s with cleanup ok.",
            "recommended_action": "Keep the baseline; recovery timing was measured, not penalised.",
        },
    },
    "report": {"backend": "groq", "chars": 1288, "saved_to": "ml/deep/live/runtime/incident_report.md"},
}


def _read_json(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _evidence() -> dict[str, Any]:
    return {
        "last_battle": _read_json("ml/last_battle.json"),
        "rl_benchmark": _read_json("ml/rl_benchmark.json"),
        "defender_benchmark": _read_json("ml/defender_benchmark.json"),
        "no_defender_baseline": _read_json("ml/no_defender_baseline.json"),
        "bad_release_experiment": _read_json("ml/bad_release_experiment.json"),
    }


def _policy() -> dict[str, Any]:
    payload = _read_json("ml/rl_q_table.json")
    states = {}
    for state, values in payload.get("states", {}).items():
        ranked = sorted(values.items(), key=lambda item: item[1], reverse=True)[:3]
        states[state] = [
            {"action": action, "q": round(float(score), 4)}
            for action, score in ranked
        ]
    return {"available": bool(states), "epsilon": payload.get("epsilon"), "states": states}


def reset_capture_dirs() -> None:
    """Never mix frames or raw video from an earlier AI battle capture."""
    shutil.rmtree(FRAMES, ignore_errors=True)
    shutil.rmtree(VIDEO_TMP, ignore_errors=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    VIDEO_TMP.mkdir(parents=True, exist_ok=True)


def frame(page, name: str) -> None:
    page.screenshot(path=str(FRAMES / f"{name}.png"))
    print(f"  frame: {name}", flush=True)


def _fulfill(route, payload: dict[str, Any]) -> None:
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(payload),
    )


def mock_api(page, captured: dict[str, Any]) -> None:
    """Serve safe, committed evidence plus a mocked AI battle result."""
    last = _read_json("ml/last_battle.json")
    report_path = ROOT / "ml" / "incident_report.md"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else "# Incident Report\n"

    page.route("**/health", lambda route: _fulfill(route, {"status": "ok", "service": "chaosarena-gate"}))
    page.route("**/lab/status", lambda route: _fulfill(route, {
        "ready": True,
        "kubernetes": {"ready": True, "detail": "shop-test ready"},
        "prometheus": {"ready": True, "detail": "prometheus ready"},
    }))
    page.route("**/evidence", lambda route: _fulfill(route, _evidence()))
    page.route("**/gate/last*", lambda route: _fulfill(route, last))
    page.route("**/gate/history*", lambda route: _fulfill(route, {
        "decisions": [
            {
                "version": "release-candidate", "attack": "network-latency",
                "target": "payment-service", "score": 100, "grade": "A",
                "verdict": "PROMOTE",
            },
            {
                "version": "v1.2-deep-aiml", "attack": "pod-kill",
                "target": "order-service", "score": 100, "grade": "A",
                "verdict": "PROMOTE",
            },
        ],
    }))
    page.route("**/report/latest", lambda route: _fulfill(route, {
        "file": str(report_path), "text": report_text,
    }))
    page.route("**/rl/policy", lambda route: _fulfill(route, _policy()))

    def evaluate_route(route) -> None:
        captured["evaluate"] = json.loads(route.request.post_data or "{}")
        response = dict(last)
        response["ai"] = {"available": True, "source": "fresh-battle"}
        response["report"] = {"file": "ml/deep/live/runtime/incident_report.md", "backend": "groq", "text": report_text}
        _fulfill(route, response)

    def ai_route(route) -> None:
        _fulfill(route, FRESH_AI if captured.get("evaluate") else SAVED_AI)

    page.route("**/gate/evaluate", evaluate_route)
    page.route("**/ai/reasoning", ai_route)


def wait_until_ready(page) -> None:
    page.goto(BASE, wait_until="networkidle", timeout=60000)
    page.wait_for_selector("text=Release gate", timeout=30000)
    page.wait_for_function(
        "() => { const m = document.querySelector('.topright .mode')?.textContent || ''; "
        "return m && !m.includes('CHECKING'); }",
        timeout=30000,
    )
    status = page.locator(".topright .mode").inner_text()
    if "API ONLINE · LAB READY" not in status:
        raise RuntimeError(f"refusing to capture an unready dashboard: {status}")
    page.wait_for_function(
        "() => document.querySelector('#aireasoning .right')?.textContent.includes('LIVE EVIDENCE')",
        timeout=30000,
    )
    print(f"  dashboard status: {status}", flush=True)
    page.wait_for_timeout(1200)


def build_gif() -> Path:
    paths = sorted(FRAMES.glob("*.png"))
    images = [Image.open(path).convert("RGB").resize((960, 600)) for path in paths]
    if not images:
        raise RuntimeError("no AI battle frames captured")
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
    """Write the new AI battle GIF and MP4 from this run only."""
    video = page.video
    page.context.close()
    webm = Path(video.path()) if video else None

    gif = build_gif()
    print(f"GIF: {gif} ({gif.stat().st_size // 1024} KiB)", flush=True)
    if webm and webm.exists():
        mp4 = convert_video(webm)
        if mp4:
            print(f"VIDEO: {mp4} ({mp4.stat().st_size // 1024} KiB)", flush=True)


def capture_ai_battle_ui(browser) -> None:
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        record_video_dir=str(VIDEO_TMP),
        record_video_size={"width": 1440, "height": 900},
    )
    page = context.new_page()
    captured: dict[str, Any] = {}
    mock_api(page, captured)
    wait_until_ready(page)

    page.locator("#battle").scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    frame(page, "01_ai_battle_checkbox_off")

    checkbox = page.locator("#aiEnabled")
    assert not checkbox.is_checked()
    checkbox.check()
    assert checkbox.is_checked()
    page.wait_for_timeout(700)
    frame(page, "02_ai_battle_checkbox_on")
    page.locator("#battle").screenshot(path=str(FORM_PNG))
    checkbox.locator("xpath=..").screenshot(path=str(CHECKBOX_PNG))
    frame(page, "02b_ai_battle_checkbox_focus")
    print(f"FORM: {FORM_PNG} ({FORM_PNG.stat().st_size // 1024} KiB)", flush=True)
    print(f"CHECKBOX: {CHECKBOX_PNG} ({CHECKBOX_PNG.stat().st_size // 1024} KiB)", flush=True)

    page.get_by_role("button", name="Run battle").click()
    page.wait_for_function(
        "() => document.querySelector('#aireasoning .right')?.textContent.includes('FRESH BATTLE NOTES')",
        timeout=30000,
    )
    assert captured["evaluate"]["ai_enabled"] is True
    assert "aiEnabled" not in captured["evaluate"]
    frame(page, "03_fresh_battle_notes")

    page.locator("#aireasoning").scroll_into_view_if_needed()
    page.wait_for_timeout(1200)
    frame(page, "04_ai_reasoning_fresh")
    page.locator("#aireasoning").screenshot(path=str(AI_PNG))
    print(f"AI PANEL: {AI_PNG} ({AI_PNG.stat().st_size // 1024} KiB)", flush=True)

    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(900)
    page.screenshot(path=str(DASH_PNG), full_page=True)
    print(f"DASHBOARD: {DASH_PNG} ({DASH_PNG.stat().st_size // 1024} KiB)", flush=True)

    finish_recording(page)


def main() -> None:
    reset_capture_dirs()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            capture_ai_battle_ui(browser)
        finally:
            browser.close()
    shutil.rmtree(FRAMES, ignore_errors=True)
    shutil.rmtree(VIDEO_TMP, ignore_errors=True)
    print("V12 AI BATTLE MEDIA CAPTURE COMPLETE", flush=True)


if __name__ == "__main__":
    main()
