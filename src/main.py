"""Application entry point: `python src/main.py` (used by Replit's Run button)."""

import os

import uvicorn

from hargasync.app import create_app


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
