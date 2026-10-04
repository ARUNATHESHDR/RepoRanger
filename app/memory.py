"""Long-term memory layer.

Semantic memory : a living summary per repo (what it is, stack, state, problems, next steps)
Episodic memory : the `suggestions` table - what was proposed and whether you accepted/dismissed it
Short-term      : the LangGraph checkpointer (see agent.py)
"""
from . import db, github_client
from .llm import get_llm, llm_text

SUMMARY_PROMPT = """You maintain a concise engineering memory for one GitHub repository.
Write an updated summary in Markdown with exactly these sections:
**What it is** (1-2 sentences) / **Stack** / **Current state** / **Known problems** / **Suggested next steps**.
Be specific, base everything on the data below, and do not invent features. Max 180 words.

Repository: {name}
Description: {description}
Primary language: {language}
Stats: {stats}
Recent commits:
{commits}
Previous summary (update it, keep what is still true):
{previous}

README / key excerpts:
{excerpts}
"""


def _readme_excerpt(name: str) -> str:
    from .indexer import get_store

    docs = get_store().similarity_search("what is this project, setup and features", k=4, filter={"repo": name})
    return "\n---\n".join(f"[{d.metadata['path']}]\n{d.page_content[:700]}" for d in docs) or "(none)"


def refresh_summary(name: str) -> str:
    repo = db.get_repo(name)
    if not repo:
        return ""
    commits = "\n".join(f"- {c['date'][:10]} {c['message']}" for c in github_client.get_commits(name, 10)) or "(none)"
    prompt = SUMMARY_PROMPT.format(
        name=name,
        description=repo["description"],
        language=repo["language"],
        stats=repo["stats"],
        commits=commits,
        previous=repo["summary"] or "(none)",
        excerpts=_readme_excerpt(name),
    )
    summary = llm_text(get_llm(0.2).invoke(prompt))
    db.set_summary(name, summary)
    return summary


def past_suggestions_text(repo: str) -> str:
    rows = db.list_suggestions(repo=repo)
    if not rows:
        return "No earlier suggestions for this repo."
    return "\n".join(f"- #{r['id']} [{r['status']}] {r['title']}" for r in rows[:25])
