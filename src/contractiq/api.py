"""Small HTTP API.  Run:  uvicorn contractiq.api:app --port 8000   (docs at /docs)"""
from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

from . import __version__
from .export import to_xlsx
from .pipeline import run
from .schema import Extraction

MAX_BYTES = 25 * 1024 * 1024
_CANDIDATES = [Path(__file__).resolve().parents[2] / "samples" / "fictional_rfp.pdf",
               Path.cwd() / "samples" / "fictional_rfp.pdf"]


def _sample_path() -> Path | None:
    return next((p for p in _CANDIDATES if p.is_file()), None)

app = FastAPI(title="ContractIQ", version=__version__,
              description="Extract requirements, dates, evaluation factors, CLINs and CDRLs from a solicitation PDF.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/extract", response_model=Extraction)
async def extract(file: UploadFile = File(...), mode: str = "rules", model: str | None = None) -> Extraction:
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File is larger than 25 MB.")
    if mode not in {"rules", "llm"}:
        raise HTTPException(400, "mode must be 'rules' or 'llm'.")
    try:
        return run(data, name=file.filename or "upload.pdf", mode=mode, model=model)
    except RuntimeError as e:  # missing key / SDK, all requests failed
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # unreadable or encrypted PDF
        raise HTTPException(422, f"Could not read this file: {type(e).__name__}") from e


@app.post("/extract.xlsx")
async def extract_xlsx(file: UploadFile = File(...), mode: str = "rules") -> Response:
    ex = await extract(file, mode)
    buf = io.BytesIO()
    to_xlsx(ex, buf)
    return Response(buf.getvalue(), headers={"Content-Disposition": 'attachment; filename="compliance_matrix.xlsx"'},
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/sample", response_model=Extraction)
def sample() -> Extraction:
    path = _sample_path()
    if path is None:
        raise HTTPException(404, "The sample file is only available in a source checkout (run from the repo folder).")
    return run(path)
