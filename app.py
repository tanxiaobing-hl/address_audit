from __future__ import annotations
import os
from pathlib import Path
import dotenv
dotenv.load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from address_audit.config import load_config
from address_audit.pipeline import AddressGovernancePipeline

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
FRONTEND_DIR = ROOT / "frontend"

cfg = load_config(DATA_DIR / "config.default.json")
pipeline = AddressGovernancePipeline(cfg, str(DATA_DIR))

app = FastAPI(title="Address Comparison Service")


class CompareRequest(BaseModel):
    addr1: str
    addr2: str
    use_llm: bool = False


@app.post("/compare")
def compare_addresses(payload: CompareRequest):
    addr1 = payload.addr1.strip()
    addr2 = payload.addr2.strip()
    if not addr1 or not addr2:
        raise HTTPException(status_code=400, detail="addr1 和 addr2 不能为空")
    result = pipeline.compare_addresses(addr1, addr2, use_llm=payload.use_llm)
    result["use_llm"] = payload.use_llm
    return result


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    html_path = FRONTEND_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="前端页面缺失")
    return html_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8008"))
    uvicorn.run(app, host=host, port=port)
