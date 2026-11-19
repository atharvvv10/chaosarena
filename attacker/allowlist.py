"""Hard safety boundary for the attacker.

Nothing in this module ever talks to Kubernetes. Its only job is to reject any
target that is not explicitly listed here. The allowlist is deliberately
hard-coded: an attack string cannot widen it, and environment variables cannot
override it.
"""
from __future__ import annotations

from collections.abc import Mapping

# The ONLY namespace the attacker is permitted to touch. shop-prod is absent
# on purpose; production must never be reachable from the attacker role.
ALLOWED_NAMESPACES: frozenset[str] = frozenset({"shop-test"})

# The ONLY pods that may be selected inside that namespace.
ALLOWED_SERVICES: frozenset[str] = frozenset(
    {
        "user-service",
        "product-service",
        "cart-service",
        "order-service",
        "payment-service",
        "loadgen",
        "postgres",
        "redis",
    }
)

# Every chaos object created by this project carries this label so cleanup is
# deterministic and cannot delete somebody else's chaos experiments.
LABEL_KEY = "chaosarena.io/attack"
LABEL_VALUE = "true"
LABEL_SELECTOR = f"{LABEL_KEY}={LABEL_VALUE}"


class AttackRejected(ValueError):
    """Raised when an attack targets anything outside the allowlist."""


def validate_namespace(namespace: str | None) -> None:
    if namespace not in ALLOWED_NAMESPACES:
        raise AttackRejected(
            f"namespace {namespace!r} is not allowed; permitted: {sorted(ALLOWED_NAMESPACES)}"
        )


def validate_target(namespace: str, service: str) -> None:
    """Validate an (namespace, service) pair before any manifest is built."""
    validate_namespace(namespace)
    if service not in ALLOWED_SERVICES:
        raise AttackRejected(
            f"service {service!r} is not allowed; permitted: {sorted(ALLOWED_SERVICES)}"
        )


def _selector_services(selector: Mapping) -> list[str]:
    labels = selector.get("labelSelectors") or {}
    app = labels.get("app")
    return [app] if app else []


def validate_manifest(manifest: Mapping) -> None:
    """Reject a manifest unless it is safely scoped and labelled for cleanup."""
    try:
        metadata = manifest["metadata"]
        spec = manifest["spec"]
    except KeyError as exc:
        raise AttackRejected(f"manifest is missing {exc.args[0]!r}") from exc

    # 1. The object itself must live in the allowed namespace.
    validate_namespace(metadata.get("namespace"))

    # 2. It must carry the cleanup label, otherwise cleanup cannot find it.
    labels = metadata.get("labels") or {}
    if labels.get(LABEL_KEY) != LABEL_VALUE:
        raise AttackRejected(f"manifest must carry {LABEL_KEY}={LABEL_VALUE}")

    # 3. Every selector namespace and service must also be on the allowlist.
    for key in ("selector", "target"):
        section = spec.get(key)
        if not section:
            continue
        for namespace in section.get("namespaces") or []:
            validate_namespace(namespace)
        for service in _selector_services(section):
            if service not in ALLOWED_SERVICES:
                raise AttackRejected(
                    f"service {service!r} in {key} selector is not allowed"
                )
