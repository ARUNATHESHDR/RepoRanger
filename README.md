# 🤖 GitHub Repo Agent

An autonomous AI engineering assistant that tracks, indexes, and reviews your personal GitHub repositories. It uses a **LangGraph-powered agent** with **Google Gemini Flash** to let you chat with your codebase, get proactive improvement suggestions, and even create GitHub issues — all with human-in-the-loop approval before any write action.

---

## 🚀 What It Does

| Feature | Description |
|---|---|
| **Repo Syncing** | Fetches all your GitHub repositories, skipping forks/archived based on settings |
| **Code Indexing (RAG)** | Splits code into language-aware chunks, embeds them locally via ChromaDB (`all-MiniLM-L6`) for fast semantic search |
| **Proactive Reviewer** | Automatically checks repo health — missing tests, CI, README, license, stale repos — and queues actionable suggestions |
| **AI Chat Agent** | LangGraph state machine powered by **Google Gemini Flash** (`gemini-3.8-flash`). Chat naturally about your code |
| **Human-in-the-Loop** | Write actions (like creating issues) pause and require your explicit approval before executing |
| **Parallel Sync** | Repos indexed in parallel (4 at a time), files fetched in parallel (8 at a time) — significantly faster than sequential |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Language** | Python 3.10+ |
| **Web Framework** | FastAPI + Uvicorn |
| **Primary LLM** | Google Gemini Flash (`gemini-3.8-flash`) via `langchain-google-genai` |
| **Fallback LLM** | Groq (`llama-3.3-70b-versatile`) — used if no Google key is set |
| **AI Agent Framework** | LangChain + LangGraph |
| **Vector Store** | ChromaDB with local ONNX embeddings (no API key needed, ~80 MB download once) |
| **Database** | SQLite — relational data, LLM summaries, suggestions, LangGraph checkpointer |
| **Background Jobs** | APScheduler — auto-syncs every 6 hours |
| **GitHub API Client** | `httpx` — thin async-friendly REST wrapper |

---

## 🔄 How It Works (Architecture)

```
User Chat (browser)
       │
       ▼
  FastAPI /api/chat
       │
       ▼
 LangGraph Agent ──── System prompt + message history
       │
       ├─ Read tool call ──► tools node ──► GitHub / ChromaDB / SQLite
       │
       └─ Write tool call ─► interrupt() ──► User approval required
                                               │
                                               ▼
                                         /api/approve
                                               │
                                               ▼
                                         Issue created on GitHub
```

### Sync Pipeline (runs on startup & every 6 hours)

```
GitHub API
    │
    ├── list_repos()      → SQLite (repo metadata)
    │
    ├── get_tree()        → filter files → parallel fetch (8 threads)
    │         │
    │         └── chunk code → embed → ChromaDB
    │
    ├── get_commits()     → embed → ChromaDB
    │
    ├── compute_stats()   → reviewer.py → SQLite (suggestions)
    │
    └── refresh_summary() → Gemini Flash → SQLite (LLM repo summary)
```

---

## 📁 Folder Structure

```
github-agent/
│
├── app/                    # Main application package
│   ├── agent.py            # LangGraph state machine — chat, tools, human-in-the-loop interrupt
│   ├── config.py           # All env vars loaded from .env (GOOGLE_API_KEY, GITHUB_TOKEN, etc.)
│   ├── db.py               # SQLite operations — repos, suggestions, summaries
│   ├── github_client.py    # Thin GitHub REST API wrapper using httpx
│   ├── indexer.py          # Parallel sync pipeline — fetch, chunk, embed into ChromaDB
│   ├── llm.py              # LLM factory — picks Gemini (primary) or Groq (fallback)
│   ├── main.py             # FastAPI app, all API endpoints, APScheduler setup
│   ├── memory.py           # Long-term semantic memory — LLM-generated summaries per repo
│   ├── reviewer.py         # Deterministic repo health checks (CI, tests, license...)
│   └── tools.py            # LangChain @tool functions the agent can call
│
├── data/                   # Auto-created at runtime
│   ├── agent.db            # SQLite: repo facts + suggestions
│   ├── checkpoints.db      # SQLite: LangGraph conversation state
│   └── chroma/             # ChromaDB vector store (code embeddings)
│
├── scripts/
│   ├── sync.py             # CLI: python -m scripts.sync [--force]
│   └── chat_cli.py         # CLI: terminal chat (for testing without browser)
│
├── static/                 # Frontend HTML/JS/CSS
├── .env                    # Your secrets (never commit this)
├── .env.example            # Template — copy to .env and fill in
├── requirements.txt        # All Python dependencies
└── run.py                  # Entry point: starts Uvicorn on http://127.0.0.1:8000
```

---

## ⚡ Quick Start

### 1. Prerequisites

- Python 3.10+
- A **Google AI Studio API key** (free) → [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
- A **GitHub fine-grained token** → [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens)
  - Required permissions: **Contents** (read), **Metadata** (read), **Issues** (read + write), **Actions** (read)

---

### 2. Set Up the Project

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate          # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Copy the env template
copy .env.example .env
```

---

### 3. Fill in `.env`

Open `.env` and fill in your keys:

```env
GOOGLE_API_KEY=your_google_ai_studio_key   # Primary LLM (Gemini Flash)
GEMINI_MODEL=gemini-3.8-flash

GITHUB_TOKEN=your_github_fine_grained_token
GITHUB_USERNAME=your_github_username

# Optional — limit to 1-2 repos for a fast first test
ONLY_REPOS=
MAX_FILES_PER_REPO=50
```

> **Tip:** Set `ONLY_REPOS=my-project-name` during your first run to finish in ~30 seconds instead of minutes.

---

### 4. Run the First Sync

This downloads repo metadata, indexes your code into ChromaDB, and generates AI summaries.

```powershell
python -m scripts.sync
```

> On first run this downloads the ~80 MB local embedding model. Subsequent runs skip repos that haven't changed.

---

### 5. Start the Web Server

```powershell
python run.py
```

Open your browser at **http://127.0.0.1:8000**

---

### 6. (Optional) Test via Terminal Chat

```powershell
python -m scripts.chat_cli
```

Try: *"which of my repos needs the most work?"* then *"create an issue in \<repo\> to add tests"*. You'll see an approval prompt before anything is written to GitHub.

---

## 🔑 Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | Yes | — | Google AI Studio key (Gemini Flash) |
| `GEMINI_MODEL` | No | `gemini-3.8-flash` | Gemini model name |
| `GROQ_API_KEY` | No | — | Fallback LLM if no Google key |
| `GITHUB_TOKEN` | Yes | — | Fine-grained GitHub PAT |
| `GITHUB_USERNAME` | Yes | — | Your GitHub username |
| `INCLUDE_FORKS` | No | `false` | Index forked repos too |
| `MAX_FILES_PER_REPO` | No | `50` | Limit files indexed per repo |
| `SYNC_INTERVAL_HOURS` | No | `6` | How often to auto-sync |
| `ONLY_REPOS` | No | *(all)* | Comma-separated repo names to limit sync |

---

## ♻️ Code Reusability & Design Patterns

- **`@tool` decorator pattern** — `tools.py` exposes plain Python functions wrapped with `@tool`. The agent calls them automatically; they can also be tested in isolation.
- **Database abstraction** — `db.py` owns all SQL. Every other module calls functions like `get_repo()` or `add_suggestion()` — never raw SQL.
- **LLM factory with fallback** — `llm.py` returns the best available LLM (Gemini → Groq) based on which keys are set. Swapping providers requires zero changes to callers.
- **Incremental indexing** — `indexer.py` checks `pushed_at` timestamps; repos that haven't changed are skipped entirely. Only new/updated repos are re-indexed.
- **Decoupled pipeline** — Indexing, reviewing, memory, and the agent are independent modules connected only through the shared SQLite database.

---

## 🐛 Common Issues

| Problem | Fix |
|---|---|
| `gemini-2.0-flash is no longer available` | Set `GEMINI_MODEL=gemini-3.8-flash` in `.env` |
| `rate_limit_exceeded` from Groq (413) | Context too large — switch to Gemini (set `GOOGLE_API_KEY`) |
| Sync is slow | Set `ONLY_REPOS=repo1` and `MAX_FILES_PER_REPO=50` in `.env` |
| `No LLM API key found` | Fill in `GOOGLE_API_KEY` in `.env` with your AI Studio key |
| `404 Not Found` on favicon | Harmless — add a `favicon.ico` to `/static/` to fix |
