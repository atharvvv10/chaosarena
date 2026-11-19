"""Runs an attack and guarantees cleanup.

Safety has three layers:
  1. build_manifest() rejects any target outside the hard allowlist;
  2. Chaos Mesh gets a `duration`, so the fault stops even if we crash;
  3. cleanup runs in a `finally` block and again via `atexit`.

Cleanup only deletes objects carrying the project label, so it can never remove
an experiment created by someone else.
"""
from __future__ import annotations

import atexit
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from . import kubectl as k8s
from .allowlist import LABEL_SELECTOR, validate_namespace
from .specs import ATTACKS, build_manifest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AttackResult:
    name: str
    manifest_name: str
    target: str
    namespace: str
    started_at: str
    ended_at: str | None = None
    cleanup_ok: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.cleanup_ok


class ChaosRunner:
    """Apply one chaos resource, hold it briefly, then always clean it up."""

    def __init__(self, namespace: str = "shop-test") -> None:
        validate_namespace(namespace)
        self.namespace = namespace
        self._exit_hook_registered = False

    def cleanup(self) -> list[str]:
        """Delete every labelled chaos object in the allowed namespace."""
        names = k8s.active_names(self.namespace, LABEL_SELECTOR)
        return k8s.delete_names(names, self.namespace)

    def launch(
        self,
        name: str,
        target: str | None = None,
        duration: int | None = None,
        peer: str | None = None,
        hold: int | None = None,
    ) -> AttackResult:
        manifest = build_manifest(name, target=target, duration=duration, peer=peer)
        spec = ATTACKS[name]
        target = target or spec.default_target
        if duration is None:
            duration = spec.default_duration
        seconds = spec.default_duration if hold is None else hold

        result = AttackResult(
            name=name,
            manifest_name=manifest["metadata"]["name"],
            target=target,
            namespace=self.namespace,
            started_at=_now(),
        )

        # Register before applying: even an exception during apply triggers it.
        self._exit_hook_registered = True
        atexit.register(self.cleanup)

        try:
            k8s.apply_manifest(manifest)
            if seconds > 0:
                time.sleep(seconds)
        except Exception as exc:  # noqa: BLE001 - cleanup must run for any error
            result.error = str(exc)
        finally:
            try:
                self.cleanup()
                result.cleanup_ok = True
            except Exception as exc:  # noqa: BLE001
                result.cleanup_ok = False
                result.error = f"cleanup failed: {exc}"
            result.ended_at = _now()
            if self._exit_hook_registered:
                atexit.unregister(self.cleanup)
                self._exit_hook_registered = False

        return result
