# Phag Frontend Handoff

## Purpose

This is the Vue/Vite browser client for Phag, a self-hosted image tagging app.
The frontend talks to the FastAPI backend and does not read image files directly.

## Current Stack

- Vue 3
- TypeScript
- Vite
- Handwritten `fetch` API client

## Local Setup

Install dependencies:

```bash
npm install
```

Run the backend from `../backend`:

```bash
PHAG_DB_PATH=../dev.db uv run phag serve --reload
```

Run the frontend from this directory:

```bash
npm run dev
```

The frontend defaults to `http://127.0.0.1:8000`. Override with:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## Files

```text
frontend/
  index.html
  package.json
  vite.config.ts
  tsconfig.json
  src/
    main.ts
    App.vue
    api.ts
    styles.css
```

`src/api.ts` contains typed wrappers around the backend REST API.

`src/App.vue` is currently a single-screen app with:

- root folder registration
- scan controls
- root list
- tag filters
- image grid
- selected-image details
- tag application/removal
- original image link

`src/styles.css` contains the application layout and visual styling.

## Backend Endpoints Used

- `GET /roots`
- `POST /roots`
- `POST /scan-jobs`
- `GET /scan-jobs/{job_id}`
- `GET /images`
- `GET /tags`
- `PATCH /tags/{tag_id}`
- `DELETE /tags/{tag_id}`
- `GET /images/{image_id}/tags`
- `POST /images/{image_id}/tags`
- `DELETE /images/{image_id}/tags/{tag_id}`
- `GET /thumbnails/{size_name}/{prefix}/{filename}`
- `GET /originals/{image_id}`

The full OpenAPI spec is in `../docs/openapi.json`.

## Recommended Next Frontend Work

1. Split `App.vue` into focused components.
2. Add per-operation loading states.
3. Add multi-select image behavior.
4. Add batch tagging for selected images.
5. Add infinite scroll using `limit` and `offset`.
6. Add image preview modal.
7. Generate API types/client from `../docs/openapi.json` once the API stabilizes.
