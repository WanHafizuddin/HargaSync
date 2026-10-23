import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import warnings

# Starlette's TestClient warns about its httpx backend; it is test-only and not actionable here.
warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")
