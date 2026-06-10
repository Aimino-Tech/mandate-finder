from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from market_intelligence.api import router

app = FastAPI(title="Market Intelligence API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

_DASHBOARD_HTML: str | None = None


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> HTMLResponse:
    global _DASHBOARD_HTML
    if _DASHBOARD_HTML is None:
        _DASHBOARD_HTML = Path(__file__).resolve().parent.parent.parent.joinpath("templates", "market_intelligence.html").read_text(encoding="utf-8")
    return HTMLResponse(content=_DASHBOARD_HTML)
