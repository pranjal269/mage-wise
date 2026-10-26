from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import core, indexer

app = FastAPI(title="Magewise")


class IndexReq(BaseModel):
    repo: str
    since: str | None = None
    limit: int = 500


class ResolveReq(BaseModel):
    repo: str
    pr_number: int | None = None  # None for historical merges with no PR (eval harness)
    file_path: str
    conflict_markers: str
    dry_run: bool = True  # skip test + write-back; the eval harness always uses this


@app.post("/index")
def index(req: IndexReq):
    return {"status": "indexed", "documents_count": indexer.index_repo(req.repo, req.since, req.limit)}


@app.post("/resolve")
def resolve(req: ResolveReq):
    try:
        return core.resolve(req.repo, req.file_path, req.conflict_markers, req.pr_number, req.dry_run)
    except ValueError as e:
        raise HTTPException(422, str(e))
