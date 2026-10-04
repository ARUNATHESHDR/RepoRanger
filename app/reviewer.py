"""Proactive review pass. Cheap, deterministic signals first - no LLM opinion needed to flag them.

Each finding has a stable `key`, so the agent never repeats itself and never nags
about something you already dismissed (that is the episodic memory at work).
"""
from datetime import datetime, timezone

from . import db, github_client


def _days_since(iso: str) -> int | None:
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).days


def review_repo(repo: dict) -> list[tuple[str, str, str]]:
    s, name = repo["stats"], repo["name"]
    out: list[tuple[str, str, str]] = []
    if not s:  # not indexed yet
        return out
    if not s.get("has_tests"):
        out.append(("no-tests", "Add automated tests", "No test files were found. Start with tests for the core logic and one smoke test."))
    if not s.get("has_ci"):
        out.append(("no-ci", "Add a CI workflow", "No .github/workflows found. A basic lint + test workflow catches regressions on every push."))
    if not s.get("has_readme") or s.get("readme_len", 0) < 400:
        out.append(("weak-readme", "Improve the README", "README is missing or very short. Add: what it does, setup, usage, screenshots, architecture."))
    if not s.get("has_license"):
        out.append(("no-license", "Add a LICENSE", "No license file. Without one, others cannot legally reuse the code."))
    if not s.get("has_gitignore"):
        out.append(("no-gitignore", "Add a .gitignore", "No .gitignore found; risk of committing secrets or build artifacts."))
    if s.get("todo_count", 0) >= 10:
        out.append(("todo-pile", f"Triage {s['todo_count']} TODO/FIXME comments", "Turn the important ones into issues and delete the rest."))
    age = _days_since(repo.get("pushed_at", ""))
    if age is not None and age > 60:
        out.append(("stale", f"Repo untouched for {age} days", "Decide: continue, archive, or write down why it paused."))
    try:
        ci = github_client.get_ci_status(name)
        if ci.get("conclusion") == "failure":
            out.append(("ci-failing", "Latest CI run is failing", f"Workflow '{ci['name']}' failed: {ci['url']}"))
    except Exception:  # noqa: BLE001
        pass
    return out


def run_review() -> int:
    """Create new suggestions for every repo. Returns how many new ones were added."""
    new = 0
    for repo in db.list_repos():
        for key, title, detail in review_repo(repo):
            if db.add_suggestion(repo["name"], key, title, detail, source="review"):
                new += 1
    return new
