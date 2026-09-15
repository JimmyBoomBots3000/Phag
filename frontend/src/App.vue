<template>
  <main class="app-shell">
    <aside class="sidebar">
      <section class="panel">
        <div class="app-title-row">
          <h1>Phag</h1>
          <button type="button" class="small-button" @click="openSettings">Settings</button>
        </div>
        <p v-if="scanInProgress" class="muted">{{ scanStatusMessage }}</p>
        <p v-if="scanSummary" class="muted">
          {{ scanSummary.discovered_count }} found,
          {{ scanSummary.indexed_count }} indexed,
          {{ scanSummary.skipped_count }} skipped
        </p>
      </section>

      <section class="panel">
        <div class="panel-title-row">
          <h2>Tags</h2>
          <button type="button" class="small-button" @click="openTagManager">Manage</button>
        </div>
        <div class="tag-filter-row">
          <fieldset class="match-options">
            <label>
              <input v-model="tagMatch" type="radio" value="and" @change="reloadImages" />
              <span>AND</span>
            </label>
            <label>
              <input v-model="tagMatch" type="radio" value="or" @change="reloadImages" />
              <span>OR</span>
            </label>
          </fieldset>
          <button type="button" class="small-button" :disabled="!hasTagFilters" @click="clearTagFilters">Clear</button>
        </div>
        <label class="tag-special-filter">
          <input v-model="includeUntaggedFilter" type="checkbox" @change="reloadImages" />
          <span>Untagged</span>
        </label>
        <TagTree :nodes="tagTree" :selected-tags="selectedTagFilters" @toggle="toggleTagFilter" />
      </section>
    </aside>

    <section class="workspace">
      <header class="toolbar">
        <div>
          <strong>{{ images.length }}</strong>
          <span class="muted">images</span>
        </div>
        <div class="toolbar-controls">
          <select v-model="sortBy" @change="reloadImages">
            <option value="filename">Filename</option>
            <option value="date_modified">Modified</option>
            <option value="date_taken">Taken</option>
            <option value="file_size">Size</option>
          </select>
          <button type="button" @click="toggleSortDirection">{{ sortDirection.toUpperCase() }}</button>
          <button type="button" @click="reloadAll">Refresh</button>
        </div>
      </header>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

      <div class="image-grid">
        <button
          v-for="image in images"
          :key="`${image.id}:${image.path}`"
          type="button"
          class="thumb"
          :class="{ selected: isImageSelected(image.id) }"
          @click="selectImage(image, $event)"
        >
          <img v-if="image.small_thumbnail_path" :src="assetUrl(image.small_thumbnail_path)" :alt="image.path_relative" />
          <span v-else class="placeholder">No thumbnail</span>
          <span class="filename">{{ image.path_relative }}</span>
        </button>
      </div>
    </section>

    <aside class="details">
      <template v-if="selectedImage">
        <h2>{{ detailTitle }}</h2>
        <dl v-if="hasSingleSelectedImage">
          <dt>Dimensions</dt>
          <dd>{{ selectedImage.width ?? "?" }} x {{ selectedImage.height ?? "?" }}</dd>
          <dt>Size</dt>
          <dd>{{ formatBytes(selectedImage.file_size_bytes) }}</dd>
          <dt>Modified</dt>
          <dd>{{ selectedImage.modified_time }}</dd>
        </dl>

        <form class="tag-form" @submit.prevent="handleTagSelectedImage">
          <input v-model="newTagName" list="tag-suggestions" placeholder="people/alice" />
          <datalist id="tag-suggestions">
            <option v-for="tag in tagSuggestions" :key="tag.id" :value="tag.display_name"></option>
          </datalist>
          <button type="submit">Tag</button>
        </form>

        <ul class="applied-tags">
          <li v-for="tag in commonSelectedTags" :key="tag.id">
            <span>{{ tag.display_name }}</span>
            <button type="button" @click="handleRemoveCommonTag(tag.id)">Remove</button>
          </li>
          <li v-for="tag in partialSelectedTags" :key="tag.id" class="partial-tag">
            <span>{{ tag.display_name }}</span>
            <button type="button" class="tag-count-link" @click="selectImagesWithTag(tag)">
              {{ tag.count }} of {{ selectedImages.length }}
            </button>
          </li>
        </ul>

        <a
          v-if="hasSingleSelectedImage"
          class="original-link"
          :href="assetUrl(`originals/${selectedImage.id}`)"
          target="_blank"
          rel="noreferrer"
        >
          Open Original
        </a>
      </template>
      <p v-else class="muted">Select an image</p>
    </aside>
  </main>

  <div v-if="settingsOpen" class="modal-backdrop">
    <section class="modal">
      <header class="modal-header">
        <h2>Settings</h2>
        <button type="button" class="small-button" @click="settingsOpen = false">Close</button>
      </header>

      <section class="settings-section">
        <div class="settings-heading-row">
          <h3>Library Roots</h3>
          <div class="settings-actions">
            <button type="button" class="small-button" @click="openRootChooser">Add Root</button>
            <button type="button" class="small-button" :disabled="busy || scanInProgress" @click="handleScanAll">
              Scan All
            </button>
          </div>
        </div>
        <p v-if="scanInProgress" class="muted">{{ scanStatusMessage }}</p>
        <ul class="plain-list settings-root-list">
          <li v-for="root in roots" :key="root.id">
            <div class="root-row">
              <span>{{ root.path }}</span>
              <div class="settings-actions">
                <button
                  type="button"
                  class="small-button"
                  :disabled="busy || scanInProgress"
                  @click="handleScanRoot(root.path)"
                >
                  Scan
                </button>
                <button
                  type="button"
                  class="small-button"
                  :disabled="busy || scanInProgress"
                  @click="handleRemoveRoot(root.id)"
                >
                  Remove
                </button>
              </div>
            </div>
          </li>
        </ul>
      </section>
    </section>
  </div>

  <div v-if="rootChooserOpen" class="modal-backdrop">
    <section class="modal">
      <header class="modal-header">
        <h2>Select Root Folder</h2>
        <button type="button" class="small-button" @click="rootChooserOpen = false">Close</button>
      </header>
      <div class="chooser-path">{{ directoryListing?.path }}</div>
      <div class="chooser-actions">
        <button
          type="button"
          :disabled="!directoryListing?.parent_path"
          @click="browseDirectory(directoryListing?.parent_path ?? undefined)"
        >
          Up
        </button>
        <button type="button" :disabled="!directoryListing" @click="handleAddSelectedRoot">Add This Folder</button>
      </div>
      <ul class="directory-list">
        <li v-for="directory in directoryListing?.directories ?? []" :key="directory">
          <button type="button" class="text-button" @click="browseDirectory(directory)">
            {{ baseName(directory) }}
          </button>
        </li>
      </ul>
    </section>
  </div>

  <div v-if="tagManagerOpen" class="modal-backdrop">
    <section class="modal">
      <header class="modal-header">
        <h2>Manage Tags</h2>
        <button type="button" class="small-button" @click="closeTagManager">Close</button>
      </header>
      <ul class="tag-manager-list">
        <li v-for="tag in tags" :key="tag.id">
          <form v-if="editingTagId === tag.id" class="tag-manager-row" @submit.prevent="handleRenameTag(tag)">
            <input v-model="editingTagName" />
            <button type="submit">Save</button>
            <button type="button" @click="cancelTagRename">Cancel</button>
          </form>
          <div v-else class="tag-manager-row">
            <span>{{ tag.display_name }}</span>
            <div class="tag-manager-actions">
              <button type="button" class="small-button" @click="startTagRename(tag)">Rename</button>
              <button type="button" class="small-button" @click="handleDeleteTag(tag)">Delete</button>
            </div>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  addRoot,
  assetUrl,
  deleteTag,
  getScanJob,
  listImageTags,
  listImages,
  listDirectories,
  listRoots,
  listTags,
  queueScan,
  renameTag,
  removeRoot,
  tagImage,
  untagImage,
  type IndexedRoot,
  type DirectoryListing,
  type LibraryImage,
  type ScanJob,
  type ScanSummary,
  type Tag
} from "./api";
import TagTree, { type TagTreeNode } from "./components/TagTree.vue";

type SortBy = "filename" | "date_modified" | "date_taken" | "file_size";
type SortDirection = "asc" | "desc";
type TagMatch = "and" | "or";

interface SelectedTagSummary extends Tag {
  count: number;
  imageIds: number[];
}

const roots = ref<IndexedRoot[]>([]);
const tags = ref<Tag[]>([]);
const images = ref<LibraryImage[]>([]);
const selectedImage = ref<LibraryImage | null>(null);
const selectedImageIds = ref<Set<number>>(new Set());
const selectedTagSummaries = ref<SelectedTagSummary[]>([]);
const selectedTagFilters = ref<string[]>([]);
const includeUntaggedFilter = ref(false);
const newTagName = ref("");
const settingsOpen = ref(false);
const rootChooserOpen = ref(false);
const directoryListing = ref<DirectoryListing | null>(null);
const tagManagerOpen = ref(false);
const editingTagId = ref<number | null>(null);
const editingTagName = ref("");
const tagMatch = ref<TagMatch>("and");
const sortBy = ref<SortBy>("filename");
const sortDirection = ref<SortDirection>("asc");
const activeScanJob = ref<ScanJob | null>(null);
const scanSummary = ref<ScanSummary | null>(null);
const errorMessage = ref("");
const busy = ref(false);

const tagTree = computed(() => buildTagTree(tags.value));
const tagSuggestions = computed(() =>
  tags.value.filter((tag) => !commonSelectedTags.value.some((selectedTag) => selectedTag.id === tag.id))
);
const hasTagFilters = computed(() => selectedTagFilters.value.length > 0 || includeUntaggedFilter.value);
const selectedImages = computed(() => images.value.filter((image) => selectedImageIds.value.has(image.id)));
const hasSingleSelectedImage = computed(() => selectedImages.value.length === 1);
const commonSelectedTags = computed(() =>
  selectedTagSummaries.value.filter((tag) => tag.count === selectedImages.value.length)
);
const partialSelectedTags = computed(() =>
  selectedTagSummaries.value.filter((tag) => tag.count > 0 && tag.count < selectedImages.value.length)
);
const detailTitle = computed(() =>
  selectedImages.value.length > 1 ? `${selectedImages.value.length} images selected` : selectedImage.value?.path_relative
);
const scanInProgress = computed(
  () => activeScanJob.value?.status === "queued" || activeScanJob.value?.status === "running"
);
const scanStatusMessage = computed(() => {
  if (!activeScanJob.value) return "";
  const path = activeScanJob.value.current_path ?? activeScanJob.value.root_path;
  if (activeScanJob.value.status === "queued") {
    return path ? `Scan queued: ${path}` : "Scan queued";
  }
  return path ? `Scanning: ${path}` : "Scan running";
});

async function withErrors(work: () => Promise<void>): Promise<void> {
  errorMessage.value = "";
  busy.value = true;
  try {
    await work();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    busy.value = false;
  }
}

async function reloadAll(): Promise<void> {
  await withErrors(loadLibraryState);
}

async function loadLibraryState(): Promise<void> {
  roots.value = await listRoots();
  tags.value = await listTags();
  await reloadImages();
}

async function reloadImages(): Promise<void> {
  images.value = await listImages({
    tags: selectedTagFilters.value,
    includeUntagged: includeUntaggedFilter.value,
    tagMatch: tagMatch.value,
    sortBy: sortBy.value,
    sortDirection: sortDirection.value,
    limit: 100,
    offset: 0
  });
  pruneMissingSelections();
  await loadSelectedTagSummaries();
}

async function selectImage(image: LibraryImage, event: MouseEvent): Promise<void> {
  if (event.shiftKey && selectedImage.value) {
    selectImageRange(selectedImage.value.id, image.id);
  } else if (event.metaKey || event.ctrlKey) {
    toggleImageSelection(image);
  } else {
    selectedImageIds.value = new Set([image.id]);
  }

  const primaryImage = selectedImageIds.value.has(image.id) ? image : selectedImages.value.at(-1) ?? null;
  selectedImage.value = primaryImage;
  if (!primaryImage) {
    selectedTagSummaries.value = [];
    return;
  }

  await withErrors(loadSelectedTagSummaries);
}

async function openRootChooser(): Promise<void> {
  rootChooserOpen.value = true;
  await browseDirectory();
}

function openSettings(): void {
  settingsOpen.value = true;
}

async function browseDirectory(path?: string): Promise<void> {
  await withErrors(async () => {
    directoryListing.value = await listDirectories(path);
  });
}

async function handleAddSelectedRoot(): Promise<void> {
  const path = directoryListing.value?.path;
  if (!path) return;
  await withErrors(async () => {
    await addRoot(path);
    rootChooserOpen.value = false;
    await loadLibraryState();
    await startQueuedScan(path);
  });
}

async function handleScanAll(): Promise<void> {
  await withErrors(async () => {
    await startQueuedScan();
  });
}

async function handleScanRoot(path: string): Promise<void> {
  await withErrors(async () => {
    await startQueuedScan(path);
  });
}

async function handleRemoveRoot(rootId: number): Promise<void> {
  await withErrors(async () => {
    await removeRoot(rootId);
    await loadLibraryState();
    await startQueuedScan();
  });
}

async function handleTagSelectedImage(): Promise<void> {
  const imageIds = selectedImages.value.map((image) => image.id);
  const tagName = newTagName.value.trim();
  if (!imageIds.length || !tagName) return;
  await withErrors(async () => {
    for (const imageId of imageIds) {
      await tagImage(imageId, tagName);
    }
    newTagName.value = "";
    await refreshTagsAndImages();
  });
}

async function handleRemoveCommonTag(tagId: number): Promise<void> {
  const imageIds = selectedImages.value.map((image) => image.id);
  if (!imageIds.length) return;
  await withErrors(async () => {
    for (const imageId of imageIds) {
      await untagImage(imageId, tagId);
    }
    await refreshTagsAndImages();
  });
}

function openTagManager(): void {
  tagManagerOpen.value = true;
}

function closeTagManager(): void {
  tagManagerOpen.value = false;
  cancelTagRename();
}

function startTagRename(tag: Tag): void {
  editingTagId.value = tag.id;
  editingTagName.value = tag.display_name;
}

function cancelTagRename(): void {
  editingTagId.value = null;
  editingTagName.value = "";
}

async function handleRenameTag(tag: Tag): Promise<void> {
  const nextName = editingTagName.value.trim();
  if (!nextName || nextName === tag.display_name) {
    cancelTagRename();
    return;
  }

  await withErrors(async () => {
    await renameTag(tag.id, nextName);
    replaceSelectedTagFilter(tag.display_name, nextName);
    cancelTagRename();
    await refreshTagsAndImages();
  });
}

async function handleDeleteTag(tag: Tag): Promise<void> {
  if (!window.confirm(`Delete tag "${tag.display_name}"?`)) return;

  await withErrors(async () => {
    await deleteTag(tag.id);
    removeSelectedTagFilter(tag.display_name);
    await refreshTagsAndImages();
  });
}

async function refreshTagsAndImages(): Promise<void> {
  tags.value = await listTags();
  await reloadImages();
}

async function loadSelectedTagSummaries(): Promise<void> {
  const imageIds = selectedImages.value.map((image) => image.id);
  if (!imageIds.length) {
    selectedTagSummaries.value = [];
    return;
  }

  const tagsByImage = await Promise.all(imageIds.map(async (imageId) => [imageId, await listImageTags(imageId)] as const));
  const tagsById = new Map<number, SelectedTagSummary>();
  for (const [imageId, imageTags] of tagsByImage) {
    for (const tag of imageTags) {
      const summary = tagsById.get(tag.id);
      if (summary) {
        summary.count += 1;
        summary.imageIds.push(imageId);
      } else {
        tagsById.set(tag.id, { ...tag, count: 1, imageIds: [imageId] });
      }
    }
  }

  selectedTagSummaries.value = [...tagsById.values()].sort((left, right) =>
    left.display_name.localeCompare(right.display_name)
  );
}

async function selectImagesWithTag(tag: SelectedTagSummary): Promise<void> {
  selectedImageIds.value = new Set(tag.imageIds);
  selectedImage.value = selectedImages.value.at(-1) ?? null;
  await withErrors(loadSelectedTagSummaries);
}

function toggleSortDirection(): void {
  sortDirection.value = sortDirection.value === "asc" ? "desc" : "asc";
  void reloadImages();
}

async function startQueuedScan(rootPath?: string): Promise<void> {
  activeScanJob.value = await queueScan(rootPath);
  void pollScanJob(activeScanJob.value.id);
}

async function pollScanJob(jobId: string): Promise<void> {
  try {
    while (activeScanJob.value?.id === jobId) {
      await delay(1000);
      const job = await getScanJob(jobId);
      if (activeScanJob.value?.id !== jobId) return;

      activeScanJob.value = job;
      if (job.status === "completed") {
        scanSummary.value = job.summary;
        await loadLibraryState();
        return;
      }
      if (job.status === "failed") {
        errorMessage.value = job.error ?? "Scan failed";
        return;
      }
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error);
  }
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function isImageSelected(imageId: number): boolean {
  return selectedImageIds.value.has(imageId);
}

function toggleImageSelection(image: LibraryImage): void {
  const nextSelectedIds = new Set(selectedImageIds.value);
  if (nextSelectedIds.has(image.id)) {
    nextSelectedIds.delete(image.id);
  } else {
    nextSelectedIds.add(image.id);
  }
  selectedImageIds.value = nextSelectedIds;
}

function selectImageRange(startImageId: number, endImageId: number): void {
  const startIndex = images.value.findIndex((image) => image.id === startImageId);
  const endIndex = images.value.findIndex((image) => image.id === endImageId);
  if (startIndex < 0 || endIndex < 0) return;

  const [firstIndex, lastIndex] = [startIndex, endIndex].sort((left, right) => left - right);
  selectedImageIds.value = new Set(images.value.slice(firstIndex, lastIndex + 1).map((image) => image.id));
}

function pruneMissingSelections(): void {
  const imageIds = new Set(images.value.map((image) => image.id));
  const selectedIds = [...selectedImageIds.value].filter((imageId) => imageIds.has(imageId));
  selectedImageIds.value = new Set(selectedIds);

  if (selectedImage.value && imageIds.has(selectedImage.value.id)) return;
  selectedImage.value = selectedImages.value.at(-1) ?? null;
  if (!selectedImage.value) {
    selectedTagSummaries.value = [];
  }
}

function toggleTagFilter(tagName: string): void {
  const index = selectedTagFilters.value.indexOf(tagName);
  if (index >= 0) {
    selectedTagFilters.value.splice(index, 1);
  } else {
    selectedTagFilters.value.push(tagName);
  }
  void reloadImages();
}

function clearTagFilters(): void {
  selectedTagFilters.value = [];
  includeUntaggedFilter.value = false;
  void reloadImages();
}

function replaceSelectedTagFilter(oldName: string, newName: string): void {
  selectedTagFilters.value = selectedTagFilters.value.map((tagName) => (tagName === oldName ? newName : tagName));
}

function removeSelectedTagFilter(tagName: string): void {
  selectedTagFilters.value = selectedTagFilters.value.filter((selectedTagName) => selectedTagName !== tagName);
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function baseName(path: string): string {
  return path.split("/").filter(Boolean).at(-1) ?? path;
}

function buildTagTree(tags: Tag[]): TagTreeNode[] {
  const rootNodes: TagTreeNode[] = [];
  const nodesByPath = new Map<string, TagTreeNode>();

  for (const tag of tags) {
    const parts = tag.display_name.split("/").filter(Boolean);
    let siblings = rootNodes;
    let currentPath = "";

    for (const [index, part] of parts.entries()) {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      let node = nodesByPath.get(currentPath);

      if (!node) {
        node = {
          name: part,
          fullPath: currentPath,
          tag: null,
          children: []
        };
        nodesByPath.set(currentPath, node);
        siblings.push(node);
      }

      if (index === parts.length - 1) {
        node.tag = tag;
      }

      siblings = node.children;
    }
  }

  sortTagTree(rootNodes);
  return rootNodes;
}

function sortTagTree(nodes: TagTreeNode[]): void {
  nodes.sort((left, right) => {
    const leftIsDirectory = left.children.length > 0;
    const rightIsDirectory = right.children.length > 0;
    if (leftIsDirectory !== rightIsDirectory) {
      return leftIsDirectory ? -1 : 1;
    }
    return left.name.localeCompare(right.name);
  });

  for (const node of nodes) {
    sortTagTree(node.children);
  }
}

onMounted(reloadAll);
</script>
