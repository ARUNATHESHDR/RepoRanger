"""Sync pipeline: GitHub -> SQLite (facts) + Chroma (code chunks) + LLM repo summary (memory).

RAG concepts you will meet here:
  * code-aware chunking (split on function/class boundaries, not fixed size)
  * metadata on every chunk (repo, path, language) so retrieval can filter
  * incremental indexing (skip repos whose pushed_at has not changed)
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from . import db, github_client
from .config import settings

log = logging.getLogger("indexer")

CODE_EXT = {
    ".py": Language.PYTHON, ".js": Language.JS, ".jsx": Language.JS, ".ts": Language.TS,
    ".tsx": Language.TS, ".java": Language.JAVA, ".go": Language.GO, ".rs": Language.RUST,
    ".cpp": Language.CPP, ".c": Language.CPP, ".md": Language.MARKDOWN, ".html": Language.HTML,
}
TEXT_EXT = {".json", ".yml", ".yaml", ".toml", ".txt", ".sql", ".sh", ".css", ".env.example"}
SKIP_DIRS = ("node_modules/", "dist/", "build/", ".next/", "venv/", ".venv/", "__pycache__/", "vendor/", "coverage/")
SKIP_FILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock")
MAX_FILE_BYTES = 80_000


class ChromaDefaultEmbeddings(Embeddings):
    """Local embeddings (all-MiniLM-L6 via ONNX) - no API key needed. Downloads ~80MB on first use."""

    def __init__(self):
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        self._fn = DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._fn(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


_store: Chroma | None = None


def get_store() -> Chroma:
    global _store
    if _store is None:
        _store = Chroma(
            collection_name="repos",
            embedding_function=ChromaDefaultEmbeddings(),
            persist_directory=settings.chroma_dir,
        )
    return _store


def _ext(path: str) -> str:
    return "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""


def _wanted(item: dict) -> bool:
    p = item["path"]
    if any(d in p for d in SKIP_DIRS) or p.endswith(SKIP_FILES):
        return False
    if item.get("size", 0) > MAX_FILE_BYTES:
        return False
    return _ext(p) in CODE_EXT or _ext(p) in TEXT_EXT


def _priority(item: dict) -> tuple:
    """README first, then shallow files, then smaller files - so the cap keeps the important stuff."""
    p = item["path"].lower()
    return (0 if p.startswith("readme") else 1, p.count("/"), item.get("size", 0))


def _split(path: str, text: str) -> list[str]:
    lang = CODE_EXT.get(_ext(path))
    if lang:
        splitter = RecursiveCharacterTextSplitter.from_language(lang, chunk_size=1200, chunk_overlap=120)
    else:
        splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=120)
    return splitter.split_text(text)


def compute_stats(tree: list[dict]) -> dict:
    paths = [t["path"].lower() for t in tree]
    return {
        "file_count": len(tree),
        "has_tests": any(re.search(r"(^|/)(tests?|__tests__|spec)/|test_.*\.py$|\.(test|spec)\.[jt]sx?$", p) for p in paths),
        "has_ci": any(p.startswith(".github/workflows/") for p in paths),
        "has_license": any(p.split("/")[-1].startswith("license") for p in paths),
        "has_readme": any(p == "readme.md" or p.startswith("readme") for p in paths),
        "has_gitignore": ".gitignore" in paths,
        "has_dockerfile": any(p.endswith("dockerfile") for p in paths),
    }


def _fetch_file(repo: str, f: dict, branch: str) -> tuple | None:
    """Fetch one file; returns (file_info, text) or None on error. Called in parallel threads."""
    try:
        text = github_client.get_file(repo, f["path"], ref=branch)
        if not text.strip():
            return None
        return f, text
    except Exception as e:  # noqa: BLE001
        log.warning("skip %s/%s: %s", repo, f["path"], e)
        return None


def index_repo(meta: dict, force: bool = False) -> dict:
    """Index one repo: fetch files in parallel, embed chunks, store in Chroma."""
    name, branch = meta["name"], meta["default_branch"]
    existing = db.get_repo(name)
    if not force and existing and existing.get("indexed_pushed_at") == meta["pushed_at"] and existing["summary"]:
        return {"repo": name, "skipped": True}

    tree = github_client.get_tree(name, branch)
    stats = compute_stats(tree)
    files = sorted((t for t in tree if _wanted(t)), key=_priority)[: settings.max_files_per_repo]

    docs: list[Document] = []
    todo_count = 0
    readme_len = 0

    # ── Parallel file fetching: fetch up to 8 files simultaneously ──
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_file, name, f, branch): f for f in files}
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                continue
            f, text = result
            todo_count += len(re.findall(r"\b(TODO|FIXME|HACK|XXX)\b", text))
            if f["path"].lower().startswith("readme"):
                readme_len = len(text)
            for i, chunk in enumerate(_split(f["path"], text)):
                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={"repo": name, "path": f["path"], "chunk": i, "kind": "code", "ext": _ext(f["path"])},
                    )
                )

    for cm in github_client.get_commits(name, 30):
        docs.append(
            Document(
                page_content=f"Commit {cm['sha']} by {cm['author']} on {cm['date']}: {cm['message']}",
                metadata={"repo": name, "path": "commits", "chunk": 0, "kind": "commit", "ext": ""},
            )
        )

    stats.update({"todo_count": todo_count, "readme_len": readme_len, "indexed_files": len(files)})

    store = get_store()
    store._collection.delete(where={"repo": name})  # replace old chunks for this repo
    for i in range(0, len(docs), 100):              # batch to keep memory low
        store.add_documents(docs[i : i + 100])

    db.mark_indexed(name, meta["pushed_at"], stats)
    return {"repo": name, "chunks": len(docs), "files": len(files), "skipped": False}


def sync_all(force: bool = False) -> list[dict]:
    """Full sync: fetch repos -> index changed ones (in parallel) -> refresh summaries -> run review."""
    from . import memory, reviewer  # local import avoids a cycle

    metas = github_client.list_repos()
    for m in metas:
        db.upsert_repo(m)

    results: list[dict] = []

    def _index_one(m: dict) -> dict:
        """Index one repo and refresh its LLM summary if changed."""
        try:
            res = index_repo(m, force=force)
            if not res["skipped"]:
                memory.refresh_summary(m["name"])
            return res
        except Exception as e:  # noqa: BLE001  one bad repo must not kill the sync
            log.exception("failed to index %s", m["name"])
            return {"repo": m["name"], "error": str(e)}

    # ── Parallel repo indexing: up to 4 repos indexed simultaneously ──
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_index_one, m): m for m in metas}
        for future in as_completed(futures):
            results.append(future.result())

    reviewer.run_review()
    return results
