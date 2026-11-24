from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent import DEFAULT_AUDIT_PATH, DEFAULT_TICKETS_PATH, process_email, run_batch
from app.models import EmailPayload, to_dict
from app.storage import AUDIT_HEADERS, TICKET_HEADERS, read_csv_rows

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Kesar & Co. AI Order-Support Copilot",
    description="Automated customer support triage, tool-calling order lookup, deduplicated ticketing, and HITL routing.",
    version="2.0.0",
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class BatchRequest(BaseModel):
    prompt_version: str = "v2"
    limit: int | None = None


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Dashboard UI not found")
    return FileResponse(str(index_file))


@app.get("/api/health")
def health() -> dict[str, Any]:
    provider = os.getenv("LLM_PROVIDER", "local").lower()
    has_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY"))
    return {
        "status": "ok",
        "mode": provider if (provider != "local" and has_key) else "local_deterministic_agent",
        "scenario_today": "2026-11-20",
    }


@app.post("/webhook/support-email")
def webhook_support_email(
    email: EmailPayload,
    x_webhook_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    expected_secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if expected_secret and x_webhook_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    res = process_email(email, prompt_version="v2")
    return to_dict(res)


@app.post("/api/run-batch")
def api_run_batch(req: BatchRequest) -> dict[str, Any]:
    only_ids = [f"E{i:02d}" for i in range(1, req.limit + 1)] if req.limit else None
    results = run_batch(prompt_version=req.prompt_version, only_ids=only_ids, reset_outputs=True)
    return {
        "processed": len(results),
        "prompt_version": req.prompt_version,
        "needs_human_count": sum(1 for r in results if r.needs_human),
        "tickets_linked": sum(1 for r in results if r.ticket_id),
        "results": [to_dict(r) for r in results],
    }


@app.get("/api/audit-log")
def get_audit_log() -> dict[str, Any]:
    rows = read_csv_rows(DEFAULT_AUDIT_PATH, AUDIT_HEADERS)
    return {"count": len(rows), "rows": rows}


@app.get("/api/tickets")
def get_tickets() -> dict[str, Any]:
    rows = read_csv_rows(DEFAULT_TICKETS_PATH, TICKET_HEADERS)
    return {"count": len(rows), "rows": rows}
