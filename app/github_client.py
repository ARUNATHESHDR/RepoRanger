"""Thin GitHub REST client (httpx). Every function the agent or indexer needs lives here."""
# Import the standard library 'base64' module to decode file contents returned by GitHub.
import base64

# Import the 'httpx' library to make asynchronous and synchronous HTTP requests.
import httpx

# Import the 'settings' object from the local 'config' module to access the GitHub token and username.
from .config import settings

# Define a constant string for the base URL of the GitHub REST API.
API = "https://api.github.com"


# Define a helper function to instantiate an HTTP client with the correct headers.
def _client() -> httpx.Client:
    # Initialize a dictionary with standard headers required for the GitHub API v3 (JSON format).
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # Check if the github_token is configured in settings.
    if settings.github_token:
        # If it is, add the Authorization header using the Bearer token scheme.
        headers["Authorization"] = f"Bearer {settings.github_token}"
    # Return a new synchronous httpx.Client configured with the base URL, headers, and a 30-second timeout.
    return httpx.Client(base_url=API, headers=headers, timeout=30)


# Define a helper function to retrieve the configured GitHub username.
def _owner() -> str:
    # Check if the github_username setting is empty or None.
    if not settings.github_username:
        # If it is missing, raise a RuntimeError indicating it must be set in the .env file.
        raise RuntimeError("GITHUB_USERNAME is not set in .env")
    # Return the configured GitHub username.
    return settings.github_username


# Define a function to list all repositories owned by the user.
def list_repos() -> list[dict]:
    """All repos you own (public + private if the token allows)."""
    # Initialize an empty list to store fetched repositories and set the starting page number to 1.
    repos, page = [], 1
    # Create an HTTP client context using the _client() helper.
    with _client() as c:
        # Start an infinite loop to paginate through the API results.
        while True:
            # Make a GET request to /user/repos, asking for up to 100 owner-affiliated repos per page, sorted by pushed date.
            r = c.get("/user/repos", params={"per_page": 100, "page": page, "affiliation": "owner", "sort": "pushed"})
            # Raise an HTTPError if the response status code indicates an error.
            r.raise_for_status()
            # Parse the JSON response body into a Python list of dictionaries.
            batch = r.json()
            # If the parsed list is empty, we have reached the end of the pages, so break the loop.
            if not batch:
                break
            # Extend the overall repos list with the results from the current page.
            repos.extend(batch)
            # Increment the page counter for the next loop iteration.
            page += 1
    # Initialize an empty list to store the filtered repository dictionaries.
    out = []
    # Loop through each fetched repository.
    for r in repos:
        # Check if the repo is a fork and the setting to include forks is false.
        if r["fork"] and not settings.include_forks:
            # Skip this repository if it's a fork and forks are excluded.
            continue
        # Check if the repository has been archived by the owner.
        if r["archived"]:
            # Skip archived repositories.
            continue
        # Check if an explicit list of allowed repositories is configured and the current repo is not in it.
        if settings.only_repos and r["name"] not in settings.only_repos:
            # Skip this repository because it is not in the allowlist.
            continue
        # Append a selected subset of the repository metadata to the output list.
        out.append(
            {
                "name": r["name"],
                "description": r["description"] or "",
                "language": r["language"] or "",
                "default_branch": r["default_branch"],
                "pushed_at": r["pushed_at"] or "",
                "stars": r["stargazers_count"],
                "open_issues": r["open_issues_count"],
                "html_url": r["html_url"],
            }
        )
    # Return the filtered list of repositories.
    return out


# Define a function to fetch the complete file tree of a specific repository branch.
def get_tree(repo: str, branch: str) -> list[dict]:
    # Create an HTTP client context.
    with _client() as c:
        # Make a recursive GET request to the Git Trees API to get all files in the branch.
        r = c.get(f"/repos/{_owner()}/{repo}/git/trees/{branch}", params={"recursive": "1"})
        # Check if the repo is completely empty (GitHub returns 409 Conflict for trees on empty repos).
        if r.status_code == 409:  # empty repo
            # Return an empty list since there are no files.
            return []
        # Raise an exception for any other HTTP errors.
        r.raise_for_status()
        # Return a list comprehension that filters the tree nodes, keeping only 'blob' (file) types.
        return [t for t in r.json().get("tree", []) if t["type"] == "blob"]


# Define a function to fetch the raw contents of a specific file from a repository.
def get_file(repo: str, path: str, ref: str | None = None) -> str:
    # Create an HTTP client context.
    with _client() as c:
        # Make a GET request to the repository contents endpoint, conditionally passing the branch/ref if provided.
        r = c.get(f"/repos/{_owner()}/{repo}/contents/{path}", params={"ref": ref} if ref else None)
        # Raise an exception if the request fails (e.g., file not found).
        r.raise_for_status()
        # Parse the JSON response body.
        data = r.json()
        # Check if the requested path is actually a directory (the API returns a list of items for directories).
        if isinstance(data, list):
            # Return a formatted string listing the contents of the directory.
            return "\n".join(f"{i['type']}: {i['path']}" for i in data)
        # Check if the file content is base64 encoded (which is typical for the contents API).
        if data.get("encoding") == "base64":
            # Decode the base64 string to bytes, then decode bytes to UTF-8 text, replacing invalid characters.
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        # Fallback: if not base64 encoded, try returning the plain content or an empty string.
        return data.get("content", "")


# Define a function to fetch the most recent commits for a repository.
def get_commits(repo: str, limit: int = 15) -> list[dict]:
    # Create an HTTP client context.
    with _client() as c:
        # Make a GET request to the commits endpoint, limiting the number of results.
        r = c.get(f"/repos/{_owner()}/{repo}/commits", params={"per_page": limit})
        # Check if the repo is empty (GitHub returns 409 Conflict for commits on empty repos).
        if r.status_code == 409:
            # Return an empty list since there are no commits.
            return []
        # Raise an exception for any other HTTP errors.
        r.raise_for_status()
    # Parse the response and map it to a simplified list of dictionaries using a list comprehension.
    return [
        {
            # Truncate the full commit SHA hash to the first 7 characters.
            "sha": x["sha"][:7],
            # Extract the commit message and split it by newline to get only the first line (title).
            "message": x["commit"]["message"].split("\n")[0],
            # Extract the commit author's date.
            "date": x["commit"]["author"]["date"],
            # Extract the commit author's name.
            "author": x["commit"]["author"]["name"],
        }
        for x in r.json()
    ]


# Define a function to list issues (and pull requests) for a repository.
def get_issues(repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    # Create an HTTP client context.
    with _client() as c:
        # Make a GET request to the issues endpoint, passing the state filter and page limit.
        r = c.get(f"/repos/{_owner()}/{repo}/issues", params={"state": state, "per_page": limit})
        # Raise an exception if the request fails.
        r.raise_for_status()
    # Parse the response and map it to a simplified list of dictionaries.
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
            "created_at": i["created_at"],
            "updated_at": i["updated_at"],
            # Determine if the item is a Pull Request (the API returns PRs alongside issues; PRs have a "pull_request" key).
            "is_pr": "pull_request" in i,
        }
        for i in r.json()
    ]


# Define a function to get the status of the most recent GitHub Actions CI run for a repository.
def get_ci_status(repo: str) -> dict:
    """Latest GitHub Actions run, or {} if the repo has none."""
    # Create an HTTP client context.
    with _client() as c:
        # Make a GET request to the workflow runs endpoint, requesting only the most recent run (per_page=1).
        r = c.get(f"/repos/{_owner()}/{repo}/actions/runs", params={"per_page": 1})
        # If the repository has Actions disabled or another issue occurs, it might not return 200.
        if r.status_code != 200:
            # Return an empty dictionary in case of failure or disabled Actions.
            return {}
        # Safely extract the list of workflow runs from the JSON response.
        runs = r.json().get("workflow_runs", [])
    # If the list of runs is empty, it means no CI has been executed yet.
    if not runs:
        # Return an empty dictionary.
        return {}
    # Extract the first (most recent) run from the list.
    run = runs[0]
    # Return a simplified dictionary containing the CI run's name, status, conclusion, and URL.
    return {"name": run["name"], "status": run["status"], "conclusion": run["conclusion"], "url": run["html_url"]}


# Define a function to create a new issue in a repository.
def create_issue(repo: str, title: str, body: str) -> dict:
    # Create an HTTP client context.
    with _client() as c:
        # Make a POST request to the issues endpoint, passing the issue title and body as JSON.
        r = c.post(f"/repos/{_owner()}/{repo}/issues", json={"title": title, "body": body})
        # Raise an exception if the creation fails (e.g., due to permissions).
        r.raise_for_status()
        # Parse the JSON response body.
        d = r.json()
    # Return a dictionary containing the newly created issue's number and web URL.
    return {"number": d["number"], "url": d["html_url"]}
