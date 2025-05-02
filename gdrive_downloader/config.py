import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from a .env file if it exists (useful for local dev)
# In Docker, environment variables are typically passed directly.
load_dotenv()

# --- Configuration Loading ---

# Define base directory within the container (consistent with WORKDIR in Dockerfile)
APP_BASE_DIR = Path("/app")

# --- Required Environment Variables ---
FOLDER_ID = os.getenv('GDRIVE_FOLDER_ID')
if not FOLDER_ID:
    raise ValueError("Missing required environment variable: GDRIVE_FOLDER_ID")

# --- Optional Environment Variables with Defaults ---
DEFAULT_DOWNLOAD_DIR = APP_BASE_DIR / "downloads"
DOWNLOAD_PATH_STR = os.getenv('DOWNLOAD_PATH_CONTAINER', str(DEFAULT_DOWNLOAD_DIR))
DOWNLOAD_PATH = Path(DOWNLOAD_PATH_STR)

# Default regex matches "00XX Dub, Edited.mp4" or "00XX Edited, Dub.mp4"
DEFAULT_REGEX = r'^00\d{2} (Dub, Edited|Edited, Dub)\.mp4$'
REGEX_PATTERN = os.getenv('GDRIVE_REGEX_PATTERN', DEFAULT_REGEX)

# Path to the service account file *inside the container*
DEFAULT_CREDS_PATH = APP_BASE_DIR / "secrets" / "google_cloud_credentials.json"
SERVICE_ACCOUNT_FILE_PATH_STR = os.getenv('SERVICE_ACCOUNT_FILE_CONTAINER', str(DEFAULT_CREDS_PATH))
SERVICE_ACCOUNT_FILE_PATH = Path(SERVICE_ACCOUNT_FILE_PATH_STR)

# Path to the state file *inside the container*
DEFAULT_STATE_DIR = APP_BASE_DIR / "state"
STATE_FILE_DIR_STR = os.getenv('STATE_FILE_DIR_CONTAINER', str(DEFAULT_STATE_DIR))
STATE_FILE_DIR = Path(STATE_FILE_DIR_STR)
SAVED_FILES_LIST_FILENAME = "found_files.json"
SAVED_FILES_LIST_PATH = STATE_FILE_DIR / SAVED_FILES_LIST_FILENAME

# Retry mechanism configuration (within the container's run cycle)
DEFAULT_RETRY_DELAY_SECONDS = 300 # 5 minutes
RETRY_DELAY_SECONDS = int(os.getenv('RETRY_DELAY_SECONDS', str(DEFAULT_RETRY_DELAY_SECONDS)))

# Google Drive API Scope
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# --- Ensure necessary directories exist inside the container's expected structure ---
# These will be created within the container if they don't exist,
# but mounting volumes from the host is the standard way to manage persistence.
DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
STATE_FILE_DIR.mkdir(parents=True, exist_ok=True)

# --- Log Configuration ---
# Using standard Python logging directed to stdout/stderr for Docker compatibility
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()