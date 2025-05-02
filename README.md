# Google Drive Recursive Downloader (Dockerized)

This project provides a Dockerized Python application to automatically download files matching a specific pattern from a Google Drive folder and its subfolders. It's designed to run periodically, check for existing files (based on size), handle Google Drive download quotas by retrying later, and maintain state between runs.

## Features

*   **Recursive Search:** Scans through subfolders within a specified Google Drive Folder ID.
*   **Pattern Matching:** Uses regular expressions to identify target files.
*   **State Persistence:** Remembers which files were found in the last search (`found_files.json`) to avoid repeated API calls.
*   **Idempotent Downloads:** Checks local file existence and size against Google Drive; skips download if the file is already present and complete.
*   **Automatic Retries:** Designed to run continuously (using Docker restart policy) with a configurable delay, automatically retrying downloads that failed (e.g., due to temporary quota limits).
*   **Robust Cleanup:** Removes partially downloaded files if an error occurs during download.
*   **Dockerized:** Runs in a container for easy deployment and dependency management.
*   **Configurable:** Settings like Folder ID, Regex, paths, and retry delay are configured via environment variables.
*   **Secure Credential Handling:** Mounts the Google Service Account key as a read-only volume at runtime, avoiding baking secrets into the image.

## Prerequisites

*   [Docker](https://docs.docker.com/get-docker/) installed.
*   [Docker Compose](https://docs.docker.com/compose/install/) (usually included with Docker Desktop) installed.
*   A [Google Cloud Platform project](https://cloud.google.com/) with the Google Drive API enabled.
*   A [Google Cloud Service Account](https://cloud.google.com/iam/docs/service-accounts-create) with a JSON key file downloaded.
*   The Google Drive folder you want to scan must be shared with the Service Account's email address (granting at least "Viewer" permissions).

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone <your-repo-url> gdrive-sync-tool
    cd gdrive-sync-tool
    ```

2.  **Create Required Host Directories:** These directories will be mounted into the container to persist data.
    ```bash
    mkdir -p data/downloads
    mkdir -p data/state
    mkdir -p secrets
    # Optional: Add .gitkeep files if you want Git to track the empty directories
    # touch data/downloads/.gitkeep data/state/.gitkeep secrets/.gitkeep
    ```

3.  **Place Service Account Key:** Copy your downloaded Google Service Account JSON key file into the `secrets/` directory and **rename it** to `google_cloud_credentials.json`.
    ```bash
    cp /path/to/your/downloaded-key.json ./secrets/google_cloud_credentials.json
    ```
    **WARNING:** Ensure the `secrets/` directory and its contents are listed in your `.gitignore` file and **never committed** to version control.

4.  **Configure Environment Variables:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Edit the `.env` file with your specific configuration:
        *   Set `GDRIVE_FOLDER_ID` to the ID of your target Google Drive folder.
        *   Adjust `GDRIVE_REGEX_PATTERN`, `RETRY_DELAY_SECONDS`, `LOG_LEVEL` if needed. The defaults often suffice.

## Running the Application

Use Docker Compose for easy management:

1.  **Build and Start (Detached Mode):**
    ```bash
    docker-compose up --build -d
    ```
    *   `--build`: Builds the Docker image if it doesn't exist or if the `Dockerfile` or source code has changed.
    *   `-d`: Runs the container in the background (detached).

2.  **Checking Logs:**
    *   Follow the logs in real-time:
        ```bash
        docker-compose logs -f
        ```
    *   View recent logs:
        ```bash
        docker-compose logs --tail 100
        ```

3.  **Stopping the Application:**
    ```bash
    docker-compose down
    ```
    This stops and removes the container but **preserves the volumes** (`data/` and `secrets/` content on your host machine).

## How it Works (Retry Loop)

1.  The `docker-compose.yml` file sets `restart: always`.
2.  The container starts and runs the `gdrive_downloader/main.py` script.
3.  The script performs one full cycle: authenticate, load state/search, process downloads (downloading or skipping).
4.  At the end of the `main()` function in `main.py`, it logs completion and waits for `RETRY_DELAY_SECONDS` using `time.sleep()`.
5.  The script then exits (with code 0 if successful, or 1 if a critical error occurred).
6.  Docker's `restart: always` policy detects the container exit and automatically restarts it.
7.  The cycle repeats.

This ensures that if a file hits a download quota, the script will simply fail that specific download attempt in one cycle, wait, exit, restart, and try again in the next cycle, eventually succeeding when the quota resets.

## Project Structure Explained

*   `gdrive_downloader/`: Contains the core Python application logic, structured as a package.
    *   `config.py`: Loads and validates configuration from environment variables.
    *   `downloader.py`: Holds functions for interacting with the Google Drive API, downloading, saving/loading state.
    *   `main.py`: Orchestrates the application flow, calling functions from other modules.
*   `data/`: Mounted directory on the host for persistent data.
    *   `downloads/`: Where downloaded files are stored.
    *   `state/`: Stores `found_files.json` to remember search results.
*   `secrets/`: Mounted directory on the host for sensitive files (like the service account key). **Should be gitignored!**
*   `.env.example` / `.env`: Environment variable configuration. `.env` should be gitignored.
*   `Dockerfile`: Instructions for building the container image.
*   `docker-compose.yml`: Easy way to define and run the multi-container Docker application (though currently only one service). Manages volumes and environment variables cleanly.
*   `requirements.txt`: Python package dependencies.
*   `README.md`: This file.