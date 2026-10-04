"""SQLite storage: structured repo data + the agent's long-term memory.

repos        -> facts about each repo (semantic memory: summary, stats)
suggestions  -> things the agent proposed and what you did with them (episodic memory)
"""
# Import the standard library 'json' module to serialize/deserialize dictionaries to/from strings.
import json
# Import the standard library 'sqlite3' module to interact with the SQLite database.
import sqlite3
# Import the 'contextmanager' decorator from the standard library 'contextlib' to create resource-managing context managers.
from contextlib import contextmanager
# Import 'datetime' and 'timezone' from the standard library 'datetime' to handle timestamp generation.
from datetime import datetime, timezone

# Import the 'settings' object from the local 'config' module to access configuration variables like the database path.
from .config import settings

# Define a multi-line string containing the SQL schema to initialize the database tables.
SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    name TEXT PRIMARY KEY,
    description TEXT,
    language TEXT,
    default_branch TEXT,
    pushed_at TEXT,
    stars INTEGER DEFAULT 0,
    open_issues INTEGER DEFAULT 0,
    html_url TEXT,
    indexed_at TEXT,
    indexed_pushed_at TEXT,
    stats_json TEXT DEFAULT '{}',
    summary TEXT DEFAULT '',
    summary_updated_at TEXT
);
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo TEXT NOT NULL,
    key TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT DEFAULT '',
    source TEXT DEFAULT 'review',
    status TEXT DEFAULT 'open',
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(repo, key)
);
"""
# A comment indicating the possible values for the 'status' column in the 'suggestions' table: open | accepted | dismissed | done

# Define a function to get the current timestamp in ISO 8601 format.
def now() -> str:
    # Use datetime.now with timezone.utc to get the current UTC time, and format it as an ISO string down to the seconds.
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Use the @contextmanager decorator to create a context manager for database connections, ensuring they are closed properly.
@contextmanager
def conn():
    # Open a connection to the SQLite database using the path specified in the settings (sqlite3 library).
    c = sqlite3.connect(settings.sqlite_path)
    # Set the row_factory to sqlite3.Row so that rows are returned as dictionary-like objects instead of tuples.
    c.row_factory = sqlite3.Row
    # Start a try block to yield the connection and handle committing changes.
    try:
        # Yield the connection object to the caller inside a 'with' block.
        yield c
        # If no exceptions were raised during the 'with' block, commit the transaction to save changes.
        c.commit()
    # Start a finally block to ensure the connection is closed regardless of success or failure.
    finally:
        # Close the SQLite database connection to free up resources.
        c.close()


# Define a function to initialize the database schema.
def init_db() -> None:
    # Open a database connection context using the 'conn()' context manager.
    with conn() as c:
        # Execute the SQL script defined in the SCHEMA string to create the tables if they don't exist.
        c.executescript(SCHEMA)


# ---------- repos ----------
# Define a function to insert or update a repository's metadata in the database.
def upsert_repo(meta: dict) -> None:
    # Open a database connection context.
    with conn() as c:
        # Execute an INSERT statement with an ON CONFLICT (UPSERT) clause to update the row if the repo name already exists.
        c.execute(
            """INSERT INTO repos (name, description, language, default_branch, pushed_at, stars, open_issues, html_url)
               VALUES (:name, :description, :language, :default_branch, :pushed_at, :stars, :open_issues, :html_url)
               ON CONFLICT(name) DO UPDATE SET description=excluded.description, language=excluded.language,
               default_branch=excluded.default_branch, pushed_at=excluded.pushed_at, stars=excluded.stars,
               open_issues=excluded.open_issues, html_url=excluded.html_url""",
            # Pass the 'meta' dictionary to provide the values for the named placeholders (e.g., :name).
            meta,
        )


# Define a helper function to convert an sqlite3.Row object into a standard Python dictionary and parse JSON fields.
def _repo_dict(row) -> dict:
    # Convert the sqlite3.Row object into a standard dictionary.
    d = dict(row)
    # Pop the 'stats_json' string from the dictionary, parse it using the json library, and store it as a 'stats' dict.
    d["stats"] = json.loads(d.pop("stats_json") or "{}")
    # Return the processed dictionary.
    return d


# Define a function to fetch a specific repository by its name.
def get_repo(name: str) -> dict | None:
    # Open a database connection context.
    with conn() as c:
        # Execute a SELECT query to find the repository by name, and fetch the first matching row.
        row = c.execute("SELECT * FROM repos WHERE name=?", (name,)).fetchone()
    # If a row was found, convert it using _repo_dict; otherwise, return None.
    return _repo_dict(row) if row else None


# Define a function to fetch all repositories from the database, ordered by their last pushed date.
def list_repos() -> list[dict]:
    # Open a database connection context.
    with conn() as c:
        # Execute a SELECT query to get all repositories, ordered by 'pushed_at' in descending order, and fetch all rows.
        rows = c.execute("SELECT * FROM repos ORDER BY pushed_at DESC").fetchall()
    # Convert each fetched row into a dictionary using a list comprehension and return the list.
    return [_repo_dict(r) for r in rows]


# Define a function to update a repository's indexing metadata after its code chunks are stored.
def mark_indexed(name: str, pushed_at: str, stats: dict) -> None:
    # Open a database connection context.
    with conn() as c:
        # Execute an UPDATE query to set the indexed timestamps and serialize the stats dictionary to JSON using the json library.
        c.execute(
            "UPDATE repos SET indexed_at=?, indexed_pushed_at=?, stats_json=? WHERE name=?",
            # Pass the values as a tuple, converting 'stats' to a JSON string using json.dumps().
            (now(), pushed_at, json.dumps(stats), name),
        )


# Define a function to update the LLM-generated summary for a specific repository.
def set_summary(name: str, summary: str) -> None:
    # Open a database connection context.
    with conn() as c:
        # Execute an UPDATE query to set the summary text and update the timestamp for when the summary was last changed.
        c.execute("UPDATE repos SET summary=?, summary_updated_at=? WHERE name=?", (summary, now(), name))


# ---------- suggestions (episodic memory) ----------
# Define a function to add a new suggestion generated by the reviewer, returning True if it's new.
def add_suggestion(repo: str, key: str, title: str, detail: str = "", source: str = "review") -> bool:
    """Insert a suggestion unless the same (repo,key) already exists. Returns True if new."""
    # Open a database connection context.
    with conn() as c:
        # Execute a SELECT query to check if a suggestion for this repo and key already exists.
        if c.execute("SELECT 1 FROM suggestions WHERE repo=? AND key=?", (repo, key)).fetchone():
            # If it exists, return False indicating it wasn't added.
            return False
        # If it doesn't exist, execute an INSERT query to add the new suggestion to the database.
        c.execute(
            "INSERT INTO suggestions (repo,key,title,detail,source,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            # Pass the suggestion details and the current timestamp for creation and update times.
            (repo, key, title, detail, source, now(), now()),
        )
    # Return True indicating the suggestion was successfully added.
    return True


# Define a function to list suggestions, optionally filtering by repository name or suggestion status.
def list_suggestions(repo: str | None = None, status: str | None = None) -> list[dict]:
    # Initialize the base query string and an empty list for the query arguments.
    q, args = "SELECT * FROM suggestions WHERE 1=1", []
    # Check if a repository filter was provided.
    if repo:
        # Append the repo filter condition to the query string.
        q += " AND repo=?"
        # Add the repository name to the arguments list.
        args.append(repo)
    # Check if a status filter was provided.
    if status:
        # Append the status filter condition to the query string.
        q += " AND status=?"
        # Add the status string to the arguments list.
        args.append(status)
    # Open a database connection context.
    with conn() as c:
        # Execute the dynamically constructed query, ordering the results by ID in descending order, and convert the rows to dicts.
        return [dict(r) for r in c.execute(q + " ORDER BY id DESC", args).fetchall()]


# Define a function to update the status of a specific suggestion (e.g., to mark it as accepted or dismissed).
def set_suggestion_status(sid: int, status: str) -> None:
    # Open a database connection context.
    with conn() as c:
        # Execute an UPDATE query to change the status and update the 'updated_at' timestamp for the given suggestion ID.
        c.execute("UPDATE suggestions SET status=?, updated_at=? WHERE id=?", (status, now(), sid))
