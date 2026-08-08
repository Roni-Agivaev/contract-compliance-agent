"""FastAPI app for the Contract Compliance Agent (Vercel entry point).

Endpoints (names exact, per assignment):
  GET  /api/team_info
  GET  /api/agent_info
  GET  /api/model_architecture   -> image/png
  POST /api/execute              -> {status, error, response, steps}
  GET  /                         -> minimal no-auth GUI
"""
import json
import os
import sys

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

# make repo root importable (config.py, agent/) when run as api/index.py
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.agent_info import AGENT_INFO  # noqa: E402

app = FastAPI(title="Contract Compliance Agent")

STATIC_DIR = os.path.join(ROOT, "static")


# ── models ─────────────────────────────────────────────────────────────────────
class ExecuteRequest(BaseModel):
    prompt: str = ""


# ── endpoints ──────────────────────────────────────────────────────────────────
@app.get("/api/team_info")
def team_info():
    with open(os.path.join(ROOT, "team_info.json"), encoding="utf-8") as f:
        return JSONResponse(json.load(f))


@app.get("/api/agent_info")
def agent_info():
    return JSONResponse(AGENT_INFO)


@app.get("/api/model_architecture")
def model_architecture():
    png = os.path.join(STATIC_DIR, "architecture.png")
    if os.path.exists(png):
        return FileResponse(png, media_type="image/png")
    return JSONResponse(
        {"error": "architecture.png not found; run scripts/make_architecture.py"},
        status_code=404,
    )


@app.post("/api/execute")
def execute(req: ExecuteRequest):
    if not req.prompt or not req.prompt.strip():
        return JSONResponse({
            "status": "error",
            "error": "'prompt' must be a non-empty string.",
            "response": None,
            "steps": [],
        })
    try:
        from agent.supervisor import run_pipeline
        result = run_pipeline(req.prompt)
        # the pipeline returns an "error" key when it cannot serve the request
        # (e.g. a jurisdiction outside the indexed set)
        if result.get("error"):
            return JSONResponse({
                "status": "error",
                "error": result["error"],
                "response": None,
                "steps": result.get("steps", []),
            })
        return JSONResponse({
            "status": "ok",
            "error": None,
            "response": result["response"],
            "steps": result["steps"],
        })
    except Exception as e:  # pragma: no cover
        return JSONResponse({
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "response": None,
            "steps": [],
        })


@app.get("/", response_class=HTMLResponse)
def gui():
    html_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Contract Compliance Agent</h1><p>GUI missing.</p>")
