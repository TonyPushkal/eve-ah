"""Local-first HTTP and browser surface."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from eve_ah.config import Settings, load_settings
from eve_ah.models import ChatRequest, ChatResponse, EveError

logger = logging.getLogger(__name__)
WEB = Path(__file__).parent / "web"


class BodyLimit:
    """Bound buffered request bodies before JSON parsing, including chunked requests."""

    def __init__(self, app, limit=128_000):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        messages, size = [], 0
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            size += len(event.get("body", b""))
            if size > self.limit:
                response = JSONResponse(
                    {"error": {"code": "body_too_large", "message": "Request exceeds 128 KB."}},
                    status_code=413,
                )
                return await response(scope, receive, send)
            messages.append(event)
            if not event.get("more_body", False):
                break
        iterator = iter(messages)

        async def replay():
            try:
                return next(iterator)
            except StopIteration:
                return await receive()

        await self.app(scope, replay, send)


def create_app(settings: Settings | None = None, knowledge=None, provider=None):
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app):
        from eve_ah.chat import ChatService
        from eve_ah.knowledge import Knowledge
        from eve_ah.providers import Provider

        app.state.ready = False
        app.state.reason = "Run eve-ah ingest, then restart the server."
        app.state.knowledge = knowledge or Knowledge(settings)
        app.state.provider = provider or Provider(settings)
        app.state.chat_limiter = anyio.CapacityLimiter(4)
        try:
            settings.require_key()
            await anyio.to_thread.run_sync(app.state.knowledge.load)
            app.state.ready = True
        except EveError as exc:
            app.state.reason = exc.message
        except ValueError:
            app.state.reason = "Check EVE_API_KEY and configuration, then restart the server."
        except Exception:
            app.state.reason = "Could not load the index. Run eve-ah ingest and check local setup."
            logger.error("Index initialization failed; no document or credential data logged.")
        app.state.chat = ChatService(settings, app.state.knowledge, app.state.provider)
        try:
            yield
        finally:
            await app.state.provider.aclose()

    app = FastAPI(title="eve-ah", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(BodyLimit)

    @app.exception_handler(EveError)
    async def eve_error(request: Request, exc: EveError):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {"error": {"code": "invalid_input", "message": "Check message and history limits."}},
            status_code=422,
        )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        if not app.state.ready:
            raise EveError(app.state.reason, code="not_ready")
        return {"status": "ready"}

    @app.get("/api/info")
    async def info():
        return {
            "name": settings.bot.name,
            "welcome": settings.bot.welcome,
            "mode": settings.bot.mode,
            "ready": app.state.ready,
            "provider": settings.provider,
            "model": settings.model,
        }

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        if not app.state.ready:
            raise EveError(app.state.reason, code="not_ready")
        try:
            app.state.chat_limiter.acquire_nowait()
        except anyio.WouldBlock:
            raise EveError("The server is busy. Please try again shortly.", 429, "busy") from None
        try:
            return await app.state.chat.answer(request)
        finally:
            app.state.chat_limiter.release()

    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(WEB / "index.html")

    return app
