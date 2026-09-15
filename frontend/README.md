# Phag Frontend

Vue/Vite browser client for the Phag backend.

## Setup

```bash
npm install
```

## Run

Start the backend first:

```bash
cd ../backend
PHAG_DB_PATH=../dev.db uv run phag serve --reload
```

Then run the frontend:

```bash
npm run dev
```

The frontend expects the backend at `http://127.0.0.1:8000` by default.
Override with:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```
