# Phag Backend

Python/FastAPI backend for indexing image folders, generating thumbnails, and managing tags.

## Setup

```bash
uv sync --dev
```

## CLI

```bash
uv run phag init-db ../dev.db
uv run phag add-root ../dev.db ~/Pictures
uv run phag index-roots ../dev.db
uv run phag list-images ../dev.db
```

## API

```bash
PHAG_DB_PATH=../dev.db uv run phag serve --reload
```

The API starts on `http://127.0.0.1:8000` by default.

Interactive docs:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Regenerate the committed OpenAPI spec:

```bash
uv run phag export-openapi ../docs/openapi.json
```

Core endpoints:

- `GET /health`
- `GET /roots`
- `POST /roots`
- `PATCH /roots/{root_id}`
- `POST /scans`
- `POST /scan-jobs`
- `GET /scan-jobs`
- `GET /scan-jobs/{job_id}`
- `DELETE /scan-jobs/{job_id}`
- `DELETE /scan-jobs`
- `GET /images`
- `GET /tags`
- `POST /tags`
- `PATCH /tags/{tag_id}`
- `DELETE /tags/{tag_id}`
- `POST /images/{image_id}/tags`
- `DELETE /images/{image_id}/tags/{tag_id}`
- `GET /thumbnails/{size}/{prefix}/{filename}`
- `GET /images/{image_id}/file`

## Tests

```bash
uv run pytest
```
