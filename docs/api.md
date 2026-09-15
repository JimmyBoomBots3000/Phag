# Phag Backend API

The backend exposes a FastAPI REST API. When the service is running, interactive
documentation is available from the app itself:

- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- OpenAPI JSON: `GET /openapi.json`

The committed OpenAPI export lives at:

```text
docs/openapi.json
```

Regenerate it from the backend project:

```bash
cd backend
uv run phag export-openapi ../docs/openapi.json
```

## Run Locally

```bash
cd backend
PHAG_DB_PATH=../dev.db uv run phag serve --reload
```

## Core Endpoints

### Health

`GET /health`

Returns basic service health.

### Roots

`GET /roots`

Lists enabled indexed roots. Use `include_disabled=true` to include disabled roots.

`POST /roots`

Registers a folder as an indexed root.

```json
{
  "path": "/Users/example/Pictures"
}
```

`DELETE /roots/{root_id}`

Disables an indexed root and marks its active file locations as orphaned.
Existing image metadata is retained until orphan cleanup runs.

### Filesystem

`GET /filesystem/directories`

Lists server-local child directories for folder selection. Optional query
parameter:

- `path`: directory to browse. If omitted, the backend user's home directory is
  used.

### Scans

`POST /scans`

Runs an indexing scan synchronously. With no body root, scans all enabled roots.

```json
{}
```

To scan one folder directly:

```json
{
  "root_path": "/Users/example/Pictures"
}
```

`POST /scan-jobs`

Queues an indexing scan and returns immediately with a job id and status.

`GET /scan-jobs/{job_id}`

Returns the queued scan status. Completed jobs include the same scan summary
counts returned by `POST /scans`.

### Images

`GET /images`

Lists active library images. Supported query parameters:

- `tag`: repeatable tag filter, for example `?tag=people/alice&tag=places/rome`
- `include_untagged`: include images with no tags
- `tag_match`: `and` or `or`
- `sort_by`: `filename`, `date_modified`, `date_taken`, or `file_size`
- `sort_direction`: `asc` or `desc`
- `limit`: page size, 1-500
- `offset`: row offset

`GET /originals/{image_id}`

Serves one active source file for an indexed image.

### Tags

`GET /tags`

Lists all tags.

`POST /tags`

Creates a tag.

```json
{
  "name": "people/alice"
}
```

`PATCH /tags/{tag_id}`

Renames a tag globally while preserving its image associations.

`DELETE /tags/{tag_id}`

Deletes a tag globally and removes its image associations.

`GET /images/{image_id}/tags`

Lists tags on one image.

`POST /images/{image_id}/tags`

Applies a tag to an image, creating the tag if needed.

```json
{
  "name": "people/alice"
}
```

`DELETE /images/{image_id}/tags/{tag_id}`

Removes one tag association from an image.

`DELETE /tags/{tag_id}`

Deletes a tag globally.

### Thumbnails

`GET /thumbnails/{size_name}/{prefix}/{filename}`

Serves a generated thumbnail. `GET /images` returns these paths in
`small_thumbnail_path` and `medium_thumbnail_path`.

### Orphans

`POST /orphans/purge`

Deletes expired orphan metadata.

```json
{
  "retention_days": 3
}
```
