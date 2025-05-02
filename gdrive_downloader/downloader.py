import io
import json
import logging
import re
import os
import time
from collections import deque
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build, Resource
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(
    level=logging.INFO, # Will be overridden by config.LOG_LEVEL if needed
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()] # Log to stdout/stderr
)
log = logging.getLogger(__name__)


def set_log_level(level_name: str):
    """Sets the logging level."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    log.setLevel(level)
    log.info(f"Logging level set to: {logging.getLevelName(log.level)}")


def get_drive_service(credentials_path: Path, scopes: List[str]) -> Optional[Resource]:
    """Authenticates and builds the Google Drive API service."""
    try:
        log.info(f"Authenticating using service account file: {credentials_path}")
        if not credentials_path.is_file():
            log.error(f"Service account file not found at: {credentials_path}")
            return None
        credentials = service_account.Credentials.from_service_account_file(
            str(credentials_path), scopes=scopes)
        service = build('drive', 'v3', credentials=credentials)
        log.info("Google Drive authentication successful.")
        return service
    except Exception as e:
        log.exception(f"Error during authentication or building Drive service: {e}", exc_info=True)
        return None


def list_drive_folder_contents(service: Resource, folder_id: str) -> List[Dict[str, Any]]:
    """Lists files and subfolders within a specific Google Drive folder."""
    files = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"
    fields = "nextPageToken, files(id, name, mimeType, size)"
    log.debug(f"Listing contents of folder ID: {folder_id}")

    while True:
        try:
            response = service.files().list(
                q=query,
                fields=fields,
                pageToken=page_token,
                # Consider adding corpus/supportsAllDrives if needed for Shared Drives
            ).execute()
            files.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        except HttpError as error:
            log.error(f"API Error listing files in folder {folder_id}: {error}")
            return [] # Return empty on error for this folder
    log.debug(f"Found {len(files)} items in folder {folder_id}")
    return files


def find_matching_files_recursive(service: Resource, start_folder_id: str, regex_pattern: str) -> List[List[str]]:
    """Recursively searches Google Drive for files matching the regex pattern."""
    queue = deque([start_folder_id])
    compiled_regex = re.compile(regex_pattern)
    matches = []
    processed_folders = set()
    folder_count = 0
    log.info(f"Starting recursive search from folder ID: {start_folder_id} with pattern: {regex_pattern}")

    while queue:
        current_folder_id = queue.popleft()
        if current_folder_id in processed_folders:
            continue
        processed_folders.add(current_folder_id)
        folder_count += 1
        if folder_count % 20 == 0: # Log progress periodically
             log.info(f"Searching... Folders processed: {folder_count}")

        items = list_drive_folder_contents(service, current_folder_id)

        for item in items:
            item_name = item.get('name')
            item_id = item.get('id')
            mime_type = item.get('mimeType')
            item_size_str = item.get('size') # Size is None for folders/google docs

            if not item_id or not item_name:
                log.warning(f"Skipping item with missing ID or name in folder {current_folder_id}")
                continue

            if mime_type == 'application/vnd.google-apps.folder':
                queue.append(item_id)
            elif mime_type != 'application/vnd.google-apps.folder' and compiled_regex.match(item_name):
                log.debug(f"Match found: Name='{item_name}', ID='{item_id}', Size='{item_size_str}'")
                matches.append([item_id, item_name, item_size_str])

    log.info(f"Search complete. Processed {folder_count} folders. Found {len(matches)} matching files.")
    return matches


def download_file_from_drive(service: Resource, file_id: str, filename: str, expected_size_str: Optional[str], download_dir: Path) -> bool:
    """Downloads a single file, checks existence/size, handles errors, ensures cleanup."""
    full_download_path = download_dir / filename
    download_successful = False
    expected_size = None
    log.info(f"Checking download for: '{filename}' (ID: {file_id})")

    # --- 1. Pre-check: File Existence and Size ---
    if expected_size_str is not None:
        try:
            expected_size = int(expected_size_str)
        except (ValueError, TypeError):
            log.warning(f"Could not parse expected size '{expected_size_str}' for {filename}.")

    if full_download_path.exists():
        try:
            local_size = full_download_path.stat().st_size
            if expected_size is not None and local_size == expected_size:
                log.info(f"Skipping: '{filename}' already exists with matching size ({local_size} bytes).")
                return True # Indicate success (already present and complete)
            elif expected_size is not None:
                 log.warning(f"'{filename}' exists but size ({local_size} bytes) differs from expected ({expected_size} bytes). Re-downloading...")
            else:
                 log.warning(f"'{filename}' exists locally ({local_size} bytes), but expected size is unknown. Re-downloading...")
        except OSError as e:
            log.warning(f"Could not get size of existing file {full_download_path}: {e}. Attempting download.")

    # --- 2. Download Attempt ---
    log.info(f"Downloading '{filename}' to {full_download_path}...")
    request = service.files().get_media(fileId=file_id)
    fh = None

    try:
        # Open file handle using pathlib's open method
        fh = full_download_path.open('wb')
        downloader = MediaIoBaseDownload(fh, request, chunksize=10*1024*1024) # 10MB chunk size
        done = False
        last_progress = -1
        while not done:
            status, done = downloader.next_chunk(num_retries=3) # Retry on transient errors
            if status:
                progress = int(status.progress() * 100)
                if progress > last_progress: # Log progress changes
                    log.info(f" -> Downloading '{filename}': {progress}%")
                    last_progress = progress

        log.info(f" -> Completed download: '{filename}'")
        download_successful = True
        return True # Indicate success

    # --- Handle Specific API/Download Errors ---
    except HttpError as error:
        error_message = f"API Error during download of {filename}: {error}"
        reason = "Unknown"
        details_parsed = False
        try:
            content_str = error.content.decode('utf-8')
            if content_str:
                 error_details = json.loads(content_str)
                 reason = error_details.get('error', {}).get('errors', [{}])[0].get('reason', 'Unknown')
                 error_message += f" (Reason: {reason})" # Append reason to message
                 details_parsed = True
            else:
                error_message += " (No further details available)"
        except Exception as parse_error:
             error_message += f" (Could not parse error details: {parse_error})"
        
        log.error(error_message)

        # Add specific follow-up actions/logs based on the parsed reason
        if details_parsed:
            if reason == 'downloadQuotaExceeded':
                log.warning(f"   -> Daily quota exceeded for this file '{filename}'. Will retry later.")
            elif reason == 'notFound':
                 log.error(f"  -> File ID {file_id} ('{filename}') not found on Google Drive.")

    except IOError as e:
        log.exception(f"File I/O Error during download of {filename}: {e}", exc_info=True)
    except Exception as e:
        log.exception(f"An unexpected error occurred during download of {filename}: {e}", exc_info=True)

    # --- Cleanup ---
    finally:
        if fh is not None and not fh.closed:
            fh.close()
        if not download_successful:
            log.warning(f"Cleaning up after failed download attempt for {filename}.")
            if full_download_path.exists():
                try:
                    full_download_path.unlink() # Delete the file
                    log.info(f"Deleted potentially incomplete file: {full_download_path}")
                except OSError as delete_error:
                    log.error(f"Failed to delete incomplete file {full_download_path}: {delete_error}")
            else:
                 log.info(f"No file found at {full_download_path} to delete.")

    return False # Indicate download failure

def save_state(matches: List[List[str]], state_file_path: Path):
    """Saves the list of found file matches (state) to a JSON file."""
    log.info(f"Saving state ({len(matches)} files) to {state_file_path}")
    try:
        with state_file_path.open('w', encoding='utf-8') as f:
            json.dump(matches, f, indent=4)
        log.info("State saved successfully.")
    except IOError as e:
        log.error(f"Error saving state file {state_file_path}: {e}")
    except Exception as e:
        log.exception(f"An unexpected error occurred while saving state: {e}", exc_info=True)


def load_state(state_file_path: Path) -> Optional[List[List[str]]]:
    """Loads the list of file matches (state) from a JSON file."""
    if not state_file_path.exists():
        log.info(f"State file '{state_file_path}' not found. Assuming first run or no previous state.")
        return None
    log.info(f"Attempting to load state from {state_file_path}")
    try:
        with state_file_path.open('r', encoding='utf-8') as f:
            matches = json.load(f)
        # Validation
        if isinstance(matches, list):
            if all(isinstance(item, (list, tuple)) and len(item) == 3 for item in matches):
                 log.info(f"Loaded state successfully ({len(matches)} items).")
                 return [list(item) for item in matches] # Ensure inner lists
            else:
                 log.error(f"Invalid item format found in state file {state_file_path}. Expected [id, name, size].")
                 return None
        else:
             log.error(f"Invalid format found in state file {state_file_path}. Expected a JSON list.")
             return None
    except json.JSONDecodeError as e:
        log.error(f"Error decoding JSON from state file {state_file_path}: {e}")
    except IOError as e:
        log.error(f"Error reading state file {state_file_path}: {e}")
    except Exception as e:
        log.exception(f"An unexpected error occurred while loading state: {e}", exc_info=True)
    return None