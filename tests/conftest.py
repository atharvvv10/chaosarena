"""Make the shared `common` package and each service importable during tests."""
import sys
from pathlib import Path

SERVICES = Path(__file__).resolve().parents[1] / "services"
if str(SERVICES) not in sys.path:
    sys.path.insert(0, str(SERVICES))
