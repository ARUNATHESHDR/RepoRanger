# Import the 'os' module from the Python standard library to read environment variables.
import os
# Import 'dataclass' and 'field' from the standard library 'dataclasses' to easily create configuration objects.
from dataclasses import dataclass, field
# Import 'Path' from the standard library 'pathlib' to handle filesystem paths in a cross-platform way.
from pathlib import Path

# Import 'load_dotenv' from the external 'python-dotenv' library to load variables from a .env file into os.environ.
from dotenv import load_dotenv

# Execute load_dotenv() to read the .env file in the current directory and inject its contents into the environment.
load_dotenv()

# Resolve the absolute path of the directory containing the parent of this file, setting it as the project base directory.
BASE_DIR = Path(__file__).resolve().parent.parent
# Create a path for the 'data' directory inside the base directory to store local files.
DATA_DIR = BASE_DIR / "data"
# Create the 'data' directory if it doesn't already exist using pathlib.
DATA_DIR.mkdir(exist_ok=True)


# Define a helper function to safely parse string environment variables into boolean values.
def _bool(name: str, default: str = "false") -> bool:
    # Retrieve the env variable, strip whitespace, convert to lowercase, and check if it matches "1", "true", or "yes".
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


# Use the @dataclass decorator to automatically generate an __init__ method and other magic methods for the class.
@dataclass
class Settings:
    # Google AI Studio key (preferred LLM — Gemini Flash is fast and has a free tier).
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    # Gemini model to use. gemini-3.8-flash is the fastest current free-tier model.
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    # Groq API key — kept as fallback if no Google key is present.
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    # Retrieve the Groq model name, defaulting to "llama-3.3-70b-versatile".
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    # Retrieve the GitHub personal access token (defaults to empty string).
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    # Retrieve the GitHub username (defaults to empty string).
    github_username: str = os.getenv("GITHUB_USERNAME", "")
    # Parse the INCLUDE_FORKS environment variable to a boolean using the custom _bool function.
    include_forks: bool = _bool("INCLUDE_FORKS")
    # Retrieve MAX_FILES_PER_REPO, defaulting to "150", and cast it to an integer.
    max_files_per_repo: int = int(os.getenv("MAX_FILES_PER_REPO", "150"))
    # Retrieve SYNC_INTERVAL_HOURS, defaulting to "6", and cast it to an integer.
    sync_interval_hours: int = int(os.getenv("SYNC_INTERVAL_HOURS", "6"))
    # Use dataclass 'field' with a default_factory to split the ONLY_REPOS string into a list of strings, removing whitespace.
    only_repos: list[str] = field(
        default_factory=lambda: [r.strip() for r in os.getenv("ONLY_REPOS", "").split(",") if r.strip()]
    )
    # Define the SQLite database path inside the DATA_DIR, converting the Path object to a string.
    sqlite_path: str = str(DATA_DIR / "agent.db")
    # Define the checkpointer database path inside the DATA_DIR, converting to string.
    checkpoint_path: str = str(DATA_DIR / "checkpoints.db")
    # Define the ChromaDB storage directory path inside the DATA_DIR, converting to string.
    chroma_dir: str = str(DATA_DIR / "chroma")


# Instantiate a singleton instance of the Settings class to be used throughout the application.
settings = Settings()
