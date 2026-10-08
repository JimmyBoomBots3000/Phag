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
  "path": "/Users/example/Pictures",
  "recursive": true,
  "replace_covered_roots": false
}
```

`recursive` defaults to `true`. Set it to `false` to index only image files
directly inside the selected folder.

Adding a child folder under an enabled recursive parent root returns `409`.
Adding a recursive parent folder that covers existing child roots also returns
`409` unless `replace_covered_roots` is `true`; replacement disables covered
child roots and marks their active file locations as orphaned.

`PATCH /roots/{root_id}`

Updates root scan options.

```json
{
  "recursive": false,
  "replace_covered_roots": false
}
```

Changing a parent root to recursive follows the same covered-root confirmation
rule as `POST /roots`.

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

`GET /scan-jobs`

Lists known scan jobs, newest first.

`GET /scan-jobs/{job_id}`

Returns the queued scan status. Completed jobs include the same scan summary
counts returned by `POST /scans`.

`DELETE /scan-jobs/{job_id}`

Cancels one queued or running scan job. Running jobs stop cooperatively at a
safe boundary; work already completed is kept.

`DELETE /scan-jobs`

Cancels all queued or running scan jobs.

### Images

`GET /images`

Lists active library images. Supported query parameters:

- `tag`: repeatable tag filter, for example `?tag=people/alice&tag=places/rome`
- `root_id`: repeatable root filter, for example `?root_id=1&root_id=2`
- `include_untagged`: include images with no tags
- `tag_match`: `and` or `or`
- `sort_by`: `filename`, `date_modified`, `date_taken`, or `file_size`
- `sort_direction`: `asc` or `desc`
- `limit`: page size, 1-500
- `offset`: row offset

`GET /images/{image_id}/file`

Serves one active source file for an indexed image.

`POST /images/{image_id}/move`

Moves one active source file into a destination directory. If the destination
is covered by an enabled indexed root, the active file location is updated and
the image remains visible in the library. If `allow_unindexed` is true, the file
can move outside indexed roots; the image then drops out of active library
views until that destination is added as an indexed root and scanned.

```json
{
  "destination_directory": "/Users/example/Pictures/Sorted",
  "allow_unindexed": false
}
```

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
