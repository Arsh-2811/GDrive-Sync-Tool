import sys
import time
import logging

# Import from sibling modules
from . import config
from . import downloader

log = logging.getLogger(__name__)

def run_download_cycle():
    """Performs one cycle of finding and downloading files."""
    log.info("Starting new download cycle.")

    # 1. Authenticate and Get Service
    service = downloader.get_drive_service(config.SERVICE_ACCOUNT_FILE_PATH, config.SCOPES)
    if not service:
        log.critical("Failed to authenticate with Google Drive. Exiting cycle.")
        return False # Indicate critical failure

    # 2. Load Previous State (List of files found last time)
    # We load state first. If we decide to search, we overwrite it later.
    # This allows downloading from the existing list even if searching fails.
    matches = downloader.load_state(config.SAVED_FILES_LIST_PATH)
    perform_search = True # Default to searching

    # Simple logic: If state exists, use it. Force search if needed (e.g., via env var - not implemented here)
    if matches is not None:
        log.info("Using previously saved file list.")
        perform_search = False
    else:
        log.info("No previous state found or loaded. Will perform search.")
        perform_search = True

    # 3. Search for Files (if needed)
    if perform_search:
        found_matches = downloader.find_matching_files_recursive(
            service, config.FOLDER_ID, config.REGEX_PATTERN
        )
        if found_matches:
            matches = found_matches
            downloader.save_state(matches, config.SAVED_FILES_LIST_PATH)
        else:
            log.warning("Search performed, but no matching files were found.")
            # Keep using potentially loaded 'matches' if search fails but state existed?
            # Current logic: if search runs, it dictates the list. If search finds nothing, matches becomes empty.
            matches = [] # Reset matches if search was done and found nothing
            # Optional: delete state file if search finds nothing
            # if config.SAVED_FILES_LIST_PATH.exists():
            #     try: config.SAVED_FILES_LIST_PATH.unlink()
            #     except OSError: pass

    # 4. Process Downloads
    if not matches:
        log.info("No files identified for download in this cycle.")
        return True # Cycle completed successfully, even if nothing to download

    log.info(f"Processing {len(matches)} files for potential download.")
    files_processed = 0
    download_errors = 0
    all_skipped_or_success = True # Track if any download attempt actually failed

    for file_info in matches:
        files_processed += 1
        if not (isinstance(file_info, (list, tuple)) and len(file_info) == 3):
            log.warning(f"Skipping invalid file entry: {file_info}")
            continue

        file_id, file_name, file_size_str = file_info

        # Perform the download check/attempt
        success = downloader.download_file_from_drive(
            service, file_id, file_name, file_size_str, config.DOWNLOAD_PATH
        )

        if not success:
            # download_file_from_drive logs specific errors (like quota)
            # Here we just track if any download failed overall
            log.warning(f"Download attempt failed or was incomplete for: {file_name}")
            all_skipped_or_success = False
            download_errors += 1

    log.info(f"Finished processing {files_processed} files.")
    log.info(f"Encountered errors on {download_errors} files during this cycle.")

    # Return True if the cycle ran without critical auth errors,
    # even if some downloads failed (e.g., due to quota). Docker restart handles retry.
    return True


def main():
    """Main entry point."""
    # Set log level from config
    downloader.set_log_level(config.LOG_LEVEL)

    log.info("G-Drive Downloader starting up.")
    log.info(f"Configuration:")
    log.info(f"  Folder ID: {config.FOLDER_ID}")
    log.info(f"  Regex Pattern: {config.REGEX_PATTERN}")
    log.info(f"  Download Path: {config.DOWNLOAD_PATH}")
    log.info(f"  Service Account File: {config.SERVICE_ACCOUNT_FILE_PATH}")
    log.info(f"  State File: {config.SAVED_FILES_LIST_PATH}")
    log.info(f"  Retry Delay: {config.RETRY_DELAY_SECONDS} seconds")

    # Run the download cycle once
    success = run_download_cycle()

    if not success:
        log.critical("Critical error during cycle, exiting with error status.")
        # Sleep briefly before exiting to allow logs to flush if needed
        time.sleep(5)
        sys.exit(1) # Exit with error for Docker restart policy

    log.info(f"Download cycle complete. Waiting {config.RETRY_DELAY_SECONDS} seconds before exiting.")
    time.sleep(config.RETRY_DELAY_SECONDS)
    log.info("Exiting current run.")
    sys.exit(0) # Exit successfully


if __name__ == "__main__":
    main()