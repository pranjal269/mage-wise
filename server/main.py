from fastapi import FastAPI
from pydantic import BaseModel

from . import classifier, indexer, resolver, retriever, test_runner, writeback

app = FastAPI(title="Magewise")


class IndexReq(BaseModel):
    repo: str
    since: str | None = None


class ResolveReq(BaseModel):
    repo: str
    pr_number: int
    file_path: str
    conflict_markers: str


@app.post("/index")
def index(req: IndexReq):
    return {"status": "indexed", "documents_count": indexer.index_repo(req.repo, req.since)}


@app.post("/resolve")
def resolve(req: ResolveReq):
    ctx = retriever.retrieve(req.repo, req.file_path, req.conflict_markers)
    verdict = classifier.classify(req.conflict_markers, ctx)
    textual = verdict["label"] == "textual-only"

    resolution = resolver.propose(req.conflict_markers, ctx, verdict) if textual else None
    test_result, test_output = (
        test_runner.run(req.repo, req.pr_number, req.file_path, resolution)
        if resolution
        else ("not_run", "")
    )
    reasoning = verdict["reason"]
    action = writeback.apply(
        req.repo, req.pr_number, req.file_path, resolution, reasoning, test_result, test_output
    )
    return {
        "classification": verdict["label"],
        "resolution": resolution,
        "reasoning": reasoning,
        "test_result": test_result,
        "action_taken": action,
    }
