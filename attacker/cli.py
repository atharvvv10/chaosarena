"""Command line entry point: python -m attacker.cli <command>."""
from __future__ import annotations

import argparse
import json
import sys

from . import kubectl as k8s
from .allowlist import ALLOWED_NAMESPACES, ALLOWED_SERVICES, LABEL_SELECTOR
from .runner import ChaosRunner
from .specs import ATTACKS, build_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m attacker.cli",
        description="Phase 2 attacker: seven allowlisted Chaos Mesh attacks.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list the seven attacks and their defaults")

    show = sub.add_parser("show", help="print a generated manifest without applying it")
    show.add_argument("attack", choices=sorted(ATTACKS))
    show.add_argument("--target")
    show.add_argument("--duration", type=int)
    show.add_argument("--peer")

    attack = sub.add_parser("attack", help="apply an attack, hold it, then clean up")
    attack.add_argument("attack", choices=sorted(ATTACKS))
    attack.add_argument("--target")
    attack.add_argument("--duration", type=int)
    attack.add_argument("--peer")
    attack.add_argument("--hold", type=int, help="seconds to wait before cleanup")

    sub.add_parser("cleanup", help="force-delete all chaosarena-labelled chaos objects")
    sub.add_parser("status", help="show active chaos objects and pod phases")

    sub.add_parser("guard", help="print the hard allowlist")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    namespace = next(iter(ALLOWED_NAMESPACES))
    runner = ChaosRunner(namespace)

    if args.command == "list":
        for name, spec in ATTACKS.items():
            print(
                f"{name:18} {spec.kind:14} target={spec.default_target:16} "
                f"duration={spec.default_duration}s  {spec.description}"
            )
        return 0

    if args.command == "guard":
        print(json.dumps({
            "allowed_namespaces": sorted(ALLOWED_NAMESPACES),
            "allowed_services": sorted(ALLOWED_SERVICES),
            "cleanup_label": LABEL_SELECTOR,
        }, indent=2))
        return 0

    if args.command == "show":
        print(json.dumps(
            build_manifest(
                args.attack,
                target=args.target,
                duration=args.duration,
                peer=args.peer,
                suffix="preview",
            ),
            indent=2,
        ))
        return 0

    if args.command == "attack":
        result = runner.launch(
            args.attack,
            target=args.target,
            duration=args.duration,
            peer=args.peer,
            hold=args.hold,
        )
        print(json.dumps({
            "name": result.name,
            "manifest": result.manifest_name,
            "target": result.target,
            "namespace": result.namespace,
            "started_at": result.started_at,
            "ended_at": result.ended_at,
            "cleanup_ok": result.cleanup_ok,
            "error": result.error,
            "ok": result.ok,
        }, indent=2))
        return 0 if result.ok else 1

    if args.command == "cleanup":
        deleted = runner.cleanup()
        print(json.dumps({"deleted": deleted, "remaining": k8s.active_names(namespace, LABEL_SELECTOR)}, indent=2))
        return 0

    if args.command == "status":
        print(json.dumps({
            "namespace": namespace,
            "chaos_objects": k8s.active_names(namespace, LABEL_SELECTOR),
            "pods": k8s.pod_states(namespace),
        }, indent=2))
        return 0

    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
