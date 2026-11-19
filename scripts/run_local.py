"""Run all five ShopApp services on one machine with no Docker/Kubernetes.

Uses fakeredis over TCP instead of a Redis container and the sqlite fallback
in common/db.py instead of a Postgres container. Production behaviour in
Docker/Kubernetes is unchanged.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
PY = sys.executable

BASE_ENV = os.environ.copy()
BASE_ENV["PYTHONPATH"] = str(SERVICES)
BASE_ENV.setdefault("VERSION", "v1.0.0")
BASE_ENV.setdefault("PAYMENT_FAILURE_RATE", "0.01")
BASE_ENV.setdefault("LOAD_INTERVAL", "0.1")

processes: list[tuple[str, subprocess.Popen, object]] = []


def start(name: str, args: list[str], extra: dict[str, str] | None = None) -> None:
    env = BASE_ENV.copy()
    if extra:
        env.update(extra)
    log = (ROOT / f"{name}.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([PY, *args], env=env, stdout=log, stderr=subprocess.STDOUT)
    processes.append((name, proc, log))
    print(f"  started {name} (pid {proc.pid})")


def main() -> None:
    print("Starting local ShopApp stack...")
    start(
        "redis-stub",
        ["-c", "from fakeredis import TcpFakeServer; "
                "TcpFakeServer(('127.0.0.1',6379), server_type='redis').serve_forever()"],
    )
    time.sleep(1)

    urls = {
        "USER_URL": "http://127.0.0.1:8100",
        "PRODUCT_URL": "http://127.0.0.1:8101",
        "CART_URL": "http://127.0.0.1:8102",
        "PAYMENT_URL": "http://127.0.0.1:8103",
        "ORDER_URL": "http://127.0.0.1:8104",
    }
    start("user", ["-m", "uvicorn", "user.main:app", "--host", "127.0.0.1", "--port", "8100"])
    start("product", ["-m", "uvicorn", "product.main:app", "--host", "127.0.0.1", "--port", "8101"])
    start("cart", ["-m", "uvicorn", "cart.main:app", "--host", "127.0.0.1", "--port", "8102"],
          {"REDIS_HOST": "127.0.0.1", "REDIS_PORT": "6379"})
    start("payment", ["-m", "uvicorn", "payment.main:app", "--host", "127.0.0.1", "--port", "8103"])
    start("order", ["-m", "uvicorn", "order.main:app", "--host", "127.0.0.1", "--port", "8104"],
          {**urls, "PG_DRIVER": "sqlite"})
    start("loadgen", ["-m", "uvicorn", "loadgen.main:app", "--host", "127.0.0.1", "--port", "8090"],
          urls)

    print("\nServices:")
    for name, port in [("user", 8100), ("product", 8101), ("cart", 8102),
                       ("payment", 8103), ("order", 8104), ("loadgen", 8090)]:
        print(f"  {name:9s} http://127.0.0.1:{port}")
    print("\nPress Ctrl+C to stop everything. Logs are in chaosarena/*.log")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping all services...")
        for name, proc, log in processes:
            proc.terminate()
        for name, proc, log in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.close()
        print("Done.")


if __name__ == "__main__":
    main()
