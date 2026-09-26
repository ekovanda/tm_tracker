# Collaborator's Getting Started Guide

Welcome to the Trackmania Bingo project! If you are familiar with Trackmania and have used the Bingo web app as a player or viewer, this guide will help you understand how the system works under the hood and get you set up to contribute—even if you are completely new to backend development.

---

## 1. The Big Picture: How the App Works

When you play a Trackmania Bingo challenge on the website, several components work together:

```
[ Browser / Website ]  <--->  [ FastAPI Backend ]  <--->  [ Nadeo Live Services ]
  (HTML / CSS / JS)               (Python)                   (Trackmania API)
                                      |
                                      v
                             [ GCP Cloud Storage ]
                                  (Firestore)
```

1. **The Frontend (`static/`)**:
   - The user interface you see in your browser (the 4x4 Bingo grid, player cards, timer countdowns, and recent personal best records).
   - Built with plain HTML, modern CSS, and vanilla JavaScript (`app.js`). No frontend frameworks (like React or Vue) to learn.

2. **The Backend (`api.py`, `bingo_service.py`, `bingo.py`)**:
   - A Python web server running **FastAPI**.
   - Handles game rules: deciding which tracks go on the board, calculating line wins, tracking timers, and determining which player currently claims each square.
   - Communicates with Ubisoft/Nadeo servers to poll official leaderboard times for each player.

3. **Persistent Memory (`storage.py` & Firestore)**:
   - Hosted on Google Cloud Platform (GCP).
   - If the server restarts or deploys a new update in the middle of a 5-hour match, it reloads the active game state from Firestore so no progress or timers are lost.

4. **Secrets Management**:
   - Passwords and Nadeo API tokens are sensitive and kept out of public code. In production, GCP Secret Manager injects them automatically; on your local computer, they live in a private `.env` file.

---

## 2. Directory Map: What Lives Where

When you want to make a change or understand a feature, look in these files:

| If you want to change or inspect... | Look at this file |
| :--- | :--- |
| **Colors, typography, layout, animations** | [`static/styles.css`](static/styles.css) |
| **HTML markup, modals, buttons, board layout** | [`static/index.html`](static/index.html) |
| **Button clicks, browser timer ticks, board updates** | [`static/app.js`](static/app.js) |
| **Bingo rules (board generation, line wins, ties)** | [`bingo.py`](bingo.py) |
| **Talking to Nadeo API (fetching campaign records)** | [`live_services.py`](live_services.py) |
| **Web API routes (`/api/game`, `/api/auth/verify`)** | [`api.py`](api.py) |
| **Saving & loading state to/from Firestore** | [`storage.py`](storage.py) |
| **Verifying your local setup and API connectivity** | [`scripts/verify_connection.py`](scripts/verify_connection.py) |
| **Deploying to live Google Cloud Run (Windows)** | [`scripts/deploy.ps1`](scripts/deploy.ps1) |
| **Deploying to live Google Cloud Run (Linux/macOS)** | [`scripts/deploy.sh`](scripts/deploy.sh) |

---

## 3. Initial Setup on Windows (or Linux/macOS)

### Step 1: Install Prerequisites
1. **Git**: [Download Git for Windows](https://gitforwindows.org/) (accept default installation options).
2. **Python 3.13**: [Download Python 3.13](https://www.python.org/downloads/) *(Important: check "Add python.exe to PATH" during installation)*.
3. **`uv`**: An extremely fast package and virtual environment manager.
   - Open **PowerShell** and run:
     ```powershell
     irm https://astral.sh/uv/install.ps1 | iex
     ```
   - *(On Linux / macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`)*
4. **Google Cloud SDK (`gcloud`)** *(needed if you want to deploy to Cloud Run)*:
   - [Download Google Cloud SDK for Windows](https://cloud.google.com/sdk/docs/install#windows).

> [!NOTE]
> **You do NOT need Docker installed on your machine!** Deployments to Google Cloud Run are built remotely in the cloud via Google Cloud Build.

---

### Step 2: Clone the Project and Create Your Environment

Open **PowerShell** (or your terminal) and run:

```powershell
# 1. Clone the repository
git clone <repository-url> tm_tracker
cd tm_tracker

# 2. Create an isolated Python environment
uv venv .venv_tm_bingo

# 3. Activate the environment
# On Windows PowerShell:
.\.venv_tm_bingo\Scripts\Activate.ps1
# (On Linux / macOS: source .venv_tm_bingo/bin/activate)

# 4. Install dependencies and development tools
uv pip install -e ".[dev]"
```

*(If PowerShell displays an execution policy error on Step 3, run: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` and try again).*

---

### Step 3: Configure Your Local Secrets (`.env`)

In the project root folder, create a file named `.env` (note the leading dot). This file is **gitignored**, meaning Git will never upload it to GitHub.

Paste the credentials provided by the project maintainer into `.env`:

```ini
# Nadeo API Service Account Credentials
BASIC_AUTH="Basic <secret-nadeo-string>"

# PBKDF2 Password Hash for the web frontend unlock gate
APP_PASSWORD_HASH="pbkdf2_sha256$600000$<salt>$<hash>"

# Identifying headers for Nadeo API compliance
# (IMPORTANT: Copy these exact values from the maintainer - do NOT use your personal email)
EMAIL="contact@example.com"
PROJECT_NAME="Eljay's TM Bingo"
MAINTAINER_HANDLE="Eljay"
```

> [!IMPORTANT]
> The `EMAIL`, `PROJECT_NAME`, and `MAINTAINER_HANDLE` identify the registered Nadeo service account to Ubisoft servers. Keep the values provided by the maintainer so API requests are accepted.

---

## 4. Test Your Setup and Connection (First Run Check)

Before running the server, run the built-in verification script:

```powershell
uv run --active python scripts/verify_connection.py
```

This script automatically verifies:
- Your Python version and installed libraries.
- Your `.env` file and password hash format.
- Connection and authentication with Ubisoft/Nadeo servers.
- A live test query fetching recent official Trackmania campaigns.

If you see `ALL CHECKS PASSED!`, your local environment and API credentials are 100% operational!

---

## 5. Running the Local Bingo Web App

Start the local development server:

```powershell
uv run --active uvicorn api:app --reload --port 8080
```

- Open your web browser and go to: **`http://localhost:8080`**
- Enter the application password to unlock the console.
- You can now test setting up a Bingo match, previewing the 4x4 board, starting timers, and tracking live challenges!
- With `--reload`, any change you save to Python or HTML/CSS files is updated instantly.

---

## 6. Running Automated Tests

Before pushing code or publishing changes, make sure all tests pass:

```powershell
uv run --active python -m pytest
```

*Tests run offline with simulated Nadeo data—fast, safe, and reliable.*

To format and check your code against project style rules:
```powershell
pre-commit run --all-files
```

---

## 7. Deploying to Google Cloud from Windows (No Docker Needed!)

When you are ready to publish your updates to the live site ([https://shorturl.fm/tm-bingo](https://shorturl.fm/tm-bingo)):

### One-Time Cloud Authentication (First time only)
```powershell
gcloud auth login
gcloud config set project project-dd21ce0e-1dd3-476c-af0
```

### Deploying Updates
Run the PowerShell deployment script:

```powershell
.\scripts\deploy.ps1
```
*(On Linux/macOS: `./scripts/deploy.sh`)*

**How this works without Docker:**
1. Your files are sent to **Google Cloud Build** in Google's cloud.
2. Google's cloud builds the container image and registers it.
3. Google Cloud Run automatically updates the service with the new version and mounts all production secrets.
4. Your changes are live in ~1-2 minutes!

---

## 8. Useful Glossary for Collaborators

- **FastAPI**: The modern Python web framework handling web requests and JSON data.
- **Single-Page Application (SPA)**: The browser downloads the webpage once and updates the board smoothly in the background without reloading the page.
- **Virtual Environment (`.venv_tm_bingo`)**: An isolated folder on your computer containing the exact Python packages required by this project, preventing conflicts with other programs.
- **Nadeo Live Services**: The official Trackmania servers that supply campaign maps, leaderboards, and personal best driving times.
- **Firestore**: A cloud-based database from Google used to save active game sessions across server restarts.
- **Cloud Build**: Google Cloud's remote builder that packages your app into containers without needing Docker installed locally.
