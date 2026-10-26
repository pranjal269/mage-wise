from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import core, indexer

app = FastAPI(title="Magewise")


class IndexReq(BaseModel):
    repo: str
    since: str | None = None
    limit: int = 300


class ResolveReq(BaseModel):
    repo: str
    file_path: str
    conflict_markers: str
    pr_number: int | None = None


@app.post("/index")
def index(req: IndexReq):
    return {"status": "indexed", "documents_count": indexer.index_repo(req.repo, req.since, req.limit)}


@app.post("/resolve")
def resolve(req: ResolveReq):
    try:
        return core.resolve(req.repo, req.file_path, req.conflict_markers, req.pr_number)
    except ValueError as e:
        raise HTTPException(422, str(e))
