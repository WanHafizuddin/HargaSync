"""FastAPI application factory."""

import sqlite3

from fastapi import Depends, FastAPI, Form, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import (
    LoginRequired,
    get_db,
    start_session,
    verify_csrf,
    verify_password,
)
from .config import Settings, load_settings
from .db import connect, init_db
from .extraction import build_extractor
from .routes_invoices import router as invoices_router
from .seed import is_empty, seed_demo
from .web import PACKAGE_DIR, redirect, render


def create_app(settings: Settings | None = None, extractor=None) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db_path = settings.data_dir / "hargasync.db"
    conn = connect(db_path)
    try:
        init_db(conn)
        if settings.demo_seed and is_empty(conn):
            seed_demo(conn, settings.demo_password)
    finally:
        conn.close()

    app = FastAPI(title="HargaSync", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.db_path = db_path
    app.state.extractor = extractor or build_extractor(settings)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="hargasync_session",
        max_age=12 * 60 * 60,
        same_site="lax",
        https_only=settings.https_only,
    )
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    app.add_exception_handler(LoginRequired, lambda request, exc: redirect("/login"))

    @app.get("/login")
    def login_page(request: Request):
        if request.session.get("user_id"):
            return redirect("/")
        return render(request, "login.html")

    @app.post("/login")
    def login_submit(
        request: Request,
        username: str = Form(""),
        password: str = Form(""),
        csrf_token: str = Form(""),
        conn: sqlite3.Connection = Depends(get_db),
    ):
        verify_csrf(request, csrf_token)
        row = conn.execute("SELECT id, password_hash FROM users WHERE username = ?", (username.strip(),)).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            context = {"error": "Wrong username or password.", "username": username}
            return render(request, "login.html", context, status_code=401)
        start_session(request, row["id"])
        return redirect("/")

    @app.post("/logout")
    def logout(request: Request, csrf_token: str = Form("")):
        verify_csrf(request, csrf_token)
        request.session.clear()
        return redirect("/login")

    app.include_router(invoices_router)

    return app
