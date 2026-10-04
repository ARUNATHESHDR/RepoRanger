"""Tools the agent can call. Read tools run freely; WRITE_TOOLS pause for your approval (see agent.py)."""
from langchain_core.tools import tool

from . import db, github_client, memory
from .indexer import get_store


@tool
def list_repos() -> str:
    """List all tracked repositories with language, last push date and open issue count."""
    rows = db.list_repos()
    if not rows:
        return "No repos synced yet. Ask the user to run a sync."
    return "\n".join(
        f"- {r['name']} ({r['language'] or 'n/a'}) last push {r['pushed_at'][:10]}, {r['open_issues']} open issues: {r['description']}"
        for r in rows
    )


@tool
def get_repo_overview(repo: str) -> str:
    """Get the stored summary, health stats and earlier suggestions for one repo. Use this first when asked about a project."""
    r = db.get_repo(repo)
    if not r:
        return f"Unknown repo '{repo}'. Call list_repos to see valid names."
    return (
        f"# {r['name']}\n{r['summary'] or '(no summary yet)'}\n\n"
        f"Stats: {r['stats']}\nURL: {r['html_url']}\n\n"
        f"Earlier suggestions:\n{memory.past_suggestions_text(repo)}"
    )


@tool
def search_code(query: str, repo: str = "") -> str:
    """Semantic search over indexed code, docs and commits. Pass repo to restrict to one project. Returns file paths with snippets."""
    flt = {"repo": repo} if repo else None
    docs = get_store().similarity_search(query, k=6, filter=flt)
    if not docs:
        return "No results."
    return "\n\n".join(f"[{d.metadata['repo']}/{d.metadata['path']}]\n{d.page_content[:900]}" for d in docs)


@tool
def read_file(repo: str, path: str) -> str:
    """Read a file from a repo (default branch) with line numbers. Use it to cite exact lines."""
    r = db.get_repo(repo)
    try:
        text = github_client.get_file(repo, path, ref=r["default_branch"] if r else None)
    except Exception as e:  # noqa: BLE001
        return f"Could not read {repo}/{path}: {e}"
    lines = text.splitlines()[:400]
    return "\n".join(f"{i + 1:4d} | {ln}" for i, ln in enumerate(lines))


@tool
def get_recent_commits(repo: str, limit: int = 10) -> str:
    """Recent commits (sha, date, message) for a repo."""
    cs = github_client.get_commits(repo, min(limit, 30))
    return "\n".join(f"{c['sha']} {c['date'][:10]} {c['message']}" for c in cs) or "No commits."


@tool
def list_issues(repo: str, state: str = "open") -> str:
    """List issues/PRs of a repo. state: open | closed | all."""
    items = github_client.get_issues(repo, state)
    return "\n".join(f"#{i['number']} [{'PR' if i['is_pr'] else 'issue'}] {i['title']} (updated {i['updated_at'][:10]})" for i in items) or "None."


@tool
def get_open_suggestions(repo: str = "") -> str:
    """Improvement suggestions the reviewer has queued (status=open). Optionally filter by repo."""
    rows = db.list_suggestions(repo=repo or None, status="open")
    return "\n".join(f"#{r['id']} {r['repo']}: {r['title']} - {r['detail']}" for r in rows) or "No open suggestions."


@tool
def create_issue(repo: str, title: str, body: str) -> str:
    """Create a GitHub issue in one of the user's repos. REQUIRES USER APPROVAL before it runs."""
    res = github_client.create_issue(repo, title, body)
    return f"Created issue #{res['number']}: {res['url']}"


READ_TOOLS = [list_repos, get_repo_overview, search_code, read_file, get_recent_commits, list_issues, get_open_suggestions]
WRITE_TOOLS = [create_issue]
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS
WRITE_TOOL_NAMES = {t.name for t in WRITE_TOOLS}
