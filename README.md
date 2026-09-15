# Phag Test Setup

Phag is a local photo tagging app. For this test version, it runs like a small
developer project instead of a normal installed Windows app.

You will run two pieces at the same time:

- Backend: a local Python service that indexes folders and stores tags.
- Frontend: a browser app that talks to the backend.

All data stays on your machine. The app creates a local SQLite database file and
thumbnail folder inside this project folder.

## Install The Tools

Install these first:

1. Python 3.12
   - https://www.python.org/downloads/
   - During install, enable **Add python.exe to PATH** if Windows offers it.

2. uv
   - https://docs.astral.sh/uv/getting-started/installation/
   - This manages the Python dependencies.

3. Node.js LTS
   - https://nodejs.org/
   - Use the LTS version, not the Current version.

4. Git
   - https://git-scm.com/download/win
   - This is only needed if you are cloning the project from GitHub, but that makes it easier 
   to get updates while this is in development.

After installing tools, close any open PowerShell windows, and open a new PowerShell 
window. Then check:

```powershell
python --version
uv --version
node --version
npm --version
git --version
```

Expected versions:

- Python should say `3.12.x`.
- Node should say an LTS version such as `20.x` or `22.x`.
- The exact uv, npm, and git versions are not important, as long as all of these return without error.

## Get The Project

Open PowerShell and go to the folder where you want the project.

If using Git:

```powershell
git clone https://github.com/JimmyBoomBots3000/Phag.git phag
cd phag
```

If using a zip file, unzip it, then `cd` into the unzipped `phag` folder.

## First-Time Setup

From the project root, install the backend dependencies:

```powershell
cd backend
uv sync
```

Then install the frontend dependencies:

```powershell
cd ..\frontend
npm install
```

## Run The App

You need two PowerShell windows.

### Window 1: Backend

From the project root:

```powershell
cd backend
$env:PHAG_DB_PATH = "..\dev.db"
uv run phag serve --reload
```

Leave this window open. It should say the backend is running at:

```text
http://127.0.0.1:8000
```

### Window 2: Frontend

From the project root:

```powershell
cd frontend
npm run dev
```

Leave this window open too. It should print a local URL, usually:

```text
http://127.0.0.1:5173
```

Open that URL in your browser.

## Basic Test Flow

1. Open `http://127.0.0.1:5173`.
2. Add a folder that contains images.
3. Wait for the scan indicator to finish.
4. Select one or more images.
5. Add tags.
6. Filter by tags.
7. Try renaming or deleting tags.
8. Remove a folder and confirm its images disappear.

Supported image types currently include common formats like JPG, JPEG, PNG,
GIF, BMP, TIFF, and WebP.

## Where Data Goes

The test setup creates:

```text
dev.db
thumbnails\
```

These are local test data. If you want to reset the app, stop both PowerShell
windows and delete `dev.db` and `thumbnails`.

## Stopping The App

In each PowerShell window, press:

```text
Ctrl+C
```

If PowerShell asks whether to terminate the batch job, type `Y` and press Enter.

## Updating The App

After getting a newer copy of the project, run:

```powershell
cd backend
uv sync
cd ..\frontend
npm install
```

Then start the backend and frontend again.

## Troubleshooting

If `python`, `uv`, `node`, `npm`, or `git` is not recognized, close PowerShell
and open a new one. If it still fails, that tool was not added to PATH during
installation.

If `uv sync` fails because Python 3.12 is missing, install Python 3.12 and rerun
the command.

If `npm install` or `npm run dev` fails after changing machines or updating
Node, delete `frontend\node_modules`, then run:

```powershell
cd frontend
npm install
```

If the browser app opens but cannot load images or tags, confirm the backend
PowerShell window is still running and check:

```text
http://127.0.0.1:8000/health
```

It should show:

```json
{"status":"ok"}
```

If port `8000` or `5173` is already in use, tell the developer. The app can be
run on other ports, but the commands need small changes.
