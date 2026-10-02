const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export interface IndexedRoot {
  id: number;
  path: string;
  recursive: boolean;
  enabled: boolean;
  last_scanned_at: string | null;
}

export interface ScanSummary {
  discovered_count: number;
  indexed_count: number;
  skipped_count: number;
  orphaned_count: number;
  thumbnail_count: number;
  failed_count: number;
}

export interface ScanJob {
  id: string;
  root_path: string | null;
  current_path: string | null;
  status: "queued" | "running" | "canceling" | "canceled" | "completed" | "failed";
  summary: ScanSummary | null;
  error: string | null;
}

export interface CancelScanJobsResponse {
  canceled_count: number;
  jobs: ScanJob[];
}

export interface Tag {
  id: number;
  display_name: string;
  normalized_name: string;
}

export interface LibraryImage {
  id: number;
  content_hash: string;
  width: number | null;
  height: number | null;
  mime_type: string;
  file_size_bytes: number;
  path: string;
  path_relative: string;
  modified_time: string;
  date_taken: string | null;
  small_thumbnail_path: string | null;
  medium_thumbnail_path: string | null;
}

export interface ListImagesOptions {
  tags: string[];
  rootIds: number[];
  includeUntagged: boolean;
  tagMatch: "and" | "or";
  sortBy: "filename" | "date_modified" | "date_taken" | "file_size";
  sortDirection: "asc" | "desc";
  limit: number;
  offset: number;
}

export interface DirectoryListing {
  path: string;
  parent_path: string | null;
  directories: string[];
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers
    }
  });

  if (!response.ok) {
    const message = await response.text();
    throw new ApiError(response.status, message || `${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export class ApiError extends Error {
  detail: unknown;

  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
    try {
      this.detail = JSON.parse(message).detail;
    } catch {
      this.detail = message;
    }
  }
}

export function assetUrl(path: string | null): string {
  return path ? `${API_BASE_URL}/${path}` : "";
}

export function listRoots(): Promise<IndexedRoot[]> {
  return request<IndexedRoot[]>("/roots");
}

export function addRoot(path: string, recursive: boolean, replaceCoveredRoots = false): Promise<IndexedRoot> {
  return request<IndexedRoot>("/roots", {
    method: "POST",
    body: JSON.stringify({ path, recursive, replace_covered_roots: replaceCoveredRoots })
  });
}

export function updateRootRecursive(rootId: number, recursive: boolean, replaceCoveredRoots = false): Promise<IndexedRoot> {
  return request<IndexedRoot>(`/roots/${rootId}`, {
    method: "PATCH",
    body: JSON.stringify({ recursive, replace_covered_roots: replaceCoveredRoots })
  });
}

export function listDirectories(path?: string): Promise<DirectoryListing> {
  const params = new URLSearchParams();
  if (path) {
    params.set("path", path);
  }
  const query = params.toString();
  return request<DirectoryListing>(`/filesystem/directories${query ? `?${query}` : ""}`);
}

export function removeRoot(rootId: number): Promise<{ removed_count: number; deleted_tag_count: number }> {
  return request<{ removed_count: number; deleted_tag_count: number }>(`/roots/${rootId}`, {
    method: "DELETE"
  });
}

export function runScan(rootPath?: string): Promise<ScanSummary> {
  return request<ScanSummary>("/scans", {
    method: "POST",
    body: JSON.stringify(rootPath ? { root_path: rootPath } : {})
  });
}

export function queueScan(rootPath?: string): Promise<ScanJob> {
  return request<ScanJob>("/scan-jobs", {
    method: "POST",
    body: JSON.stringify(rootPath ? { root_path: rootPath } : {})
  });
}

export function listScanJobs(): Promise<ScanJob[]> {
  return request<ScanJob[]>("/scan-jobs");
}

export function getScanJob(jobId: string): Promise<ScanJob> {
  return request<ScanJob>(`/scan-jobs/${jobId}`);
}

export function cancelScanJob(jobId: string): Promise<ScanJob> {
  return request<ScanJob>(`/scan-jobs/${jobId}`, {
    method: "DELETE"
  });
}

export function cancelAllScanJobs(): Promise<CancelScanJobsResponse> {
  return request<CancelScanJobsResponse>("/scan-jobs", {
    method: "DELETE"
  });
}

export function listTags(): Promise<Tag[]> {
  return request<Tag[]>("/tags");
}

export function listImageTags(imageId: number): Promise<Tag[]> {
  return request<Tag[]>(`/images/${imageId}/tags`);
}

export function tagImage(imageId: number, name: string): Promise<{ image_id: number; tag_id: number; name: string }> {
  return request<{ image_id: number; tag_id: number; name: string }>(`/images/${imageId}/tags`, {
    method: "POST",
    body: JSON.stringify({ name })
  });
}

export function renameTag(tagId: number, name: string): Promise<{ id: number; name: string }> {
  return request<{ id: number; name: string }>(`/tags/${tagId}`, {
    method: "PATCH",
    body: JSON.stringify({ name })
  });
}

export function deleteTag(tagId: number): Promise<{ deleted_count: number }> {
  return request<{ deleted_count: number }>(`/tags/${tagId}`, {
    method: "DELETE"
  });
}

export function untagImage(imageId: number, tagId: number): Promise<{ removed_count: number; deleted_tag_count: number }> {
  return request<{ removed_count: number; deleted_tag_count: number }>(`/images/${imageId}/tags/${tagId}`, {
    method: "DELETE"
  });
}

export function listImages(options: ListImagesOptions): Promise<LibraryImage[]> {
  const params = new URLSearchParams({
    tag_match: options.tagMatch,
    include_untagged: String(options.includeUntagged),
    sort_by: options.sortBy,
    sort_direction: options.sortDirection,
    limit: String(options.limit),
    offset: String(options.offset)
  });

  for (const tag of options.tags) {
    params.append("tag", tag);
  }
  for (const rootId of options.rootIds) {
    params.append("root_id", String(rootId));
  }

  return request<LibraryImage[]>(`/images?${params.toString()}`);
}
