<template>
  <main class="app-shell">
    <aside class="sidebar">
      <section class="panel">
        <div class="app-title-row">
          <h1 class="logo-heading">
            <PhagLogo class="brand-logo" />
          </h1>
          <div class="title-actions">
            <button type="button" class="small-button" @click="openSettings">Settings</button>
          </div>
        </div>
        <p v-if="scanStatusMessage" class="muted">{{ scanStatusMessage }}</p>
        <p v-if="scanSummary" class="muted">
          {{ scanSummary.discovered_count }} found,
          {{ scanSummary.indexed_count }} indexed,
          {{ scanSummary.skipped_count }} skipped<template v-if="scanSummary.failed_count">,
            {{ scanSummary.failed_count }} failed</template>
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
          <input v-model="includeUntaggedFilter" type="checkbox" @change="handleUntaggedFilterChange" />
          <span>Untagged</span>
        </label>
        <TagTree :nodes="tagTree" :selected-tags="selectedTagFilters" @toggle="toggleTagFilter" />
      </section>

      <section class="panel roots-panel">
        <h2>Roots</h2>
        <ul class="plain-list root-filter-list">
          <li v-for="root in roots" :key="root.id">
            <label class="root-filter-row">
              <input
                type="checkbox"
                :checked="selectedRootFilters.includes(root.id)"
                @change="toggleRootFilter(root.id)"
              />
              <span>{{ baseName(root.path) }}</span>
            </label>
          </li>
        </ul>
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
          <button type="button" class="small-button" @click="toggleSortDirection">{{ sortDirection.toUpperCase() }}</button>
          <button type="button" class="small-button" @click="reloadAll">Refresh</button>
        </div>
      </header>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

      <div class="image-grid-scroll">
        <div class="image-grid">
          <button
            v-for="image in images"
            :key="`${image.id}:${image.path}`"
            type="button"
            class="thumb"
            :class="{ selected: isImageSelected(image.id) }"
            @click="selectImage(image, $event)"
            @dblclick="openImageFile(image)"
          >
            <img v-if="image.small_thumbnail_path" :src="assetUrl(image.small_thumbnail_path)" :alt="image.path_relative" />
            <span v-else class="placeholder">No thumbnail</span>
            <span class="filename">{{ image.path_relative }}</span>
          </button>
        </div>
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
          <button type="submit" class="small-button">Tag</button>
        </form>

        <section v-if="hasSelectedTags" class="applied-tag-section">
          <div class="tag-bulk-actions">
            <button type="button" class="small-button" @click="handleRemoveAllSelectedTags">Remove All</button>
          </div>

          <ul class="applied-tags">
            <li v-for="tag in commonSelectedTags" :key="tag.id">
              <span>{{ tag.display_name }}</span>
              <button type="button" class="small-button" @click="handleRemoveCommonTag(tag.id)">Remove</button>
            </li>
            <li v-for="tag in partialSelectedTags" :key="tag.id" class="partial-tag">
              <span>{{ tag.display_name }}</span>
              <button type="button" class="tag-count-link" @click="selectImagesWithTag(tag)">
                {{ tag.count }} of {{ selectedImages.length }}
              </button>
            </li>
          </ul>
        </section>

        <div class="image-action-row">
          <button type="button" class="small-button" @click="openMoveChooser">Move To</button>
          <a
            v-if="hasSingleSelectedImage"
            class="image-file-link"
            :href="assetUrl(`images/${selectedImage.id}/file`)"
            target="_blank"
            rel="noreferrer"
          >
            Open Image
          </a>
        </div>
      </template>
      <div v-else class="empty-details">
        <p class="muted">Select one or more images</p>
        <p class="selection-help">
          Shift-click selects a range. {{ multiSelectClickLabel }} adds or removes individual images.
        </p>
      </div>
    </aside>
  </main>

  <div v-if="settingsOpen" class="modal-backdrop">
    <section class="modal">
      <header class="modal-header">
        <h2>Settings</h2>
        <button type="button" class="small-button" @click="settingsOpen = false">Close</button>
      </header>

      <section class="settings-section">
        <label class="settings-field">
          <span>Appearance</span>
          <select v-model="themePreference" @change="handleThemePreferenceChange">
            <option value="system">Use system setting</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
      </section>

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
        <p v-if="scanStatusMessage" class="muted">{{ scanStatusMessage }}</p>
        <p v-if="settingsErrorMessage" class="modal-error">{{ settingsErrorMessage }}</p>
        <div class="root-legend">
          <span class="root-mode-badge recursive" aria-hidden="true">R</span>
          <span>Scan subfolders recursively</span>
        </div>
        <ul class="plain-list settings-root-list">
          <li v-for="root in roots" :key="root.id">
            <div class="root-row">
              <div class="root-main">
                <span
                  v-if="root.recursive"
                  class="root-mode-badge recursive"
                  aria-label="Scan subfolders recursively"
                  title="Scan subfolders recursively"
                >
                  R
                </span>
                <span class="root-path">{{ root.path }}</span>
              </div>
              <div class="settings-actions">
                <label class="inline-check">
                  <input
                    type="checkbox"
                    :checked="root.recursive"
                    :disabled="busy || scanInProgress"
                    @change="handleRootRecursiveChange(root, $event)"
                  />
                  <span>Scan subfolders recursively</span>
                </label>
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

      <section v-if="activeScanJobs.length" class="settings-section">
        <div class="settings-heading-row">
          <h3>Scans</h3>
          <button
            type="button"
            class="small-button"
            :disabled="busy || !hasCancelableScans"
            @click="handleCancelAllScans"
          >
            Cancel All
          </button>
        </div>
        <ul class="plain-list scan-job-list">
          <li v-for="job in activeScanJobs" :key="job.id">
            <div class="scan-job-row">
              <div class="scan-job-main">
                <span class="scan-job-status">{{ scanJobLabel(job) }}</span>
                <span class="scan-job-path">{{ job.current_path ?? job.root_path ?? "All roots" }}</span>
              </div>
              <button
                type="button"
                class="small-button"
                :disabled="busy || !isCancelableScan(job)"
                @click="handleCancelScan(job)"
              >
                Cancel
              </button>
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
      <p v-if="rootChooserErrorMessage" class="modal-error">{{ rootChooserErrorMessage }}</p>
      <div class="chooser-path">{{ directoryListing?.path }}</div>
      <label class="option-row">
        <input v-model="rootChooserRecursive" type="checkbox" />
        <span>Include subfolders</span>
      </label>
      <div class="chooser-actions">
        <button
          type="button"
          class="small-button"
          :disabled="!directoryListing?.parent_path"
          @click="browseDirectory(directoryListing?.parent_path ?? undefined)"
        >
          Up
        </button>
        <button type="button" class="small-button" :disabled="!directoryListing" @click="handleAddSelectedRoot">
          Add This Folder
        </button>
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

  <div v-if="moveChooserOpen" class="modal-backdrop">
    <section class="modal">
      <header class="modal-header">
        <h2>Move Images</h2>
        <button type="button" class="small-button" @click="moveChooserOpen = false">Close</button>
      </header>
      <p v-if="moveChooserErrorMessage" class="modal-error">{{ moveChooserErrorMessage }}</p>
      <p class="muted">{{ moveChooserSummary }}</p>
      <div class="chooser-path">{{ moveDirectoryListing?.path }}</div>
      <div class="chooser-actions">
        <button
          type="button"
          class="small-button"
          :disabled="!moveDirectoryListing?.parent_path"
          @click="browseMoveDirectory(moveDirectoryListing?.parent_path ?? undefined)"
        >
          Up
        </button>
        <button type="button" class="small-button" :disabled="!moveDirectoryListing" @click="handleMoveSelectedImages">
          Move Here
        </button>
      </div>
      <ul class="directory-list">
        <li v-for="directory in moveDirectoryListing?.directories ?? []" :key="directory">
          <button type="button" class="text-button" @click="browseMoveDirectory(directory)">
            {{ baseName(directory) }}
          </button>
        </li>
      </ul>
    </section>
  </div>

  <div v-if="untrackedMovePromptOpen" class="modal-backdrop">
    <section class="modal compact-modal">
      <header class="modal-header">
        <h2>Track Destination?</h2>
      </header>
      <p class="modal-copy">
        Phag is not tracking the destination folder. Add it to Library Roots before moving?
        Choose No to move anyway; the image will leave the library view until this folder is tracked.
      </p>
      <div class="chooser-path">{{ pendingMoveDestination }}</div>
      <label class="option-row">
        <input v-model="pendingMoveRecursive" type="checkbox" />
        <span>Scan subfolders recursively</span>
      </label>
      <div class="modal-actions">
        <button type="button" class="small-button" @click="handleTrackedMoveChoice">Yes</button>
        <button type="button" class="small-button" @click="handleUntrackedMoveChoice">No</button>
        <button type="button" class="small-button" @click="cancelPendingMove">Cancel</button>
      </div>
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
            <button type="submit" class="small-button">Save</button>
            <button type="button" class="small-button" @click="cancelTagRename">Cancel</button>
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
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  addRoot,
  ApiError,
  assetUrl,
  cancelAllScanJobs,
  cancelScanJob,
  deleteTag,
  getScanJob,
  listImageTags,
  listImages,
  listDirectories,
  listRoots,
  listScanJobs,
  listTags,
  moveImage,
  queueScan,
  renameTag,
  removeRoot,
  tagImage,
  untagImage,
  updateRootRecursive,
  type IndexedRoot,
  type DirectoryListing,
  type LibraryImage,
  type ScanJob,
  type ScanSummary,
  type Tag
} from "./api";
import PhagLogo from "./components/PhagLogo.vue";
import TagTree, { type TagTreeNode } from "./components/TagTree.vue";

type SortBy = "filename" | "date_modified" | "date_taken" | "file_size";
type SortDirection = "asc" | "desc";
type TagMatch = "and" | "or";
type ThemeMode = "light" | "dark";
type ThemePreference = ThemeMode | "system";

interface SelectedTagSummary extends Tag {
  count: number;
  imageIds: number[];
}

interface RootOverlapDetail {
  code: "root_already_covered" | "covered_roots_require_confirmation";
  covering_root?: { id: number; path: string; recursive: boolean } | null;
  covered_roots?: { id: number; path: string; recursive: boolean }[];
}

const roots = ref<IndexedRoot[]>([]);
const tags = ref<Tag[]>([]);
const images = ref<LibraryImage[]>([]);
const selectedImage = ref<LibraryImage | null>(null);
const selectedImageIds = ref<Set<number>>(new Set());
const selectedTagSummaries = ref<SelectedTagSummary[]>([]);
const selectedTagFilters = ref<string[]>([]);
const selectedRootFilters = ref<number[]>([]);
const includeUntaggedFilter = ref(false);
const newTagName = ref("");
const settingsOpen = ref(false);
const rootChooserOpen = ref(false);
const rootChooserRecursive = ref(true);
const rootChooserErrorMessage = ref("");
const settingsErrorMessage = ref("");
const directoryListing = ref<DirectoryListing | null>(null);
const moveChooserOpen = ref(false);
const moveChooserErrorMessage = ref("");
const moveDirectoryListing = ref<DirectoryListing | null>(null);
const untrackedMovePromptOpen = ref(false);
const pendingMoveRecursive = ref(true);
const pendingMoveDestination = ref("");
const pendingMoveImages = ref<LibraryImage[]>([]);
const tagManagerOpen = ref(false);
const editingTagId = ref<number | null>(null);
const editingTagName = ref("");
const tagMatch = ref<TagMatch>("and");
const sortBy = ref<SortBy>("filename");
const sortDirection = ref<SortDirection>("asc");
const scanJobs = ref<ScanJob[]>([]);
const latestFinishedScanJob = ref<ScanJob | null>(null);
const scanSummary = ref<ScanSummary | null>(null);
const errorMessage = ref("");
const busy = ref(false);
const themePreference = ref<ThemePreference>(initialThemePreference());
const systemThemeMode = ref<ThemeMode>(getSystemThemeMode());

const tagTree = computed(() => buildTagTree(tags.value));
const tagSuggestions = computed(() =>
  tags.value.filter((tag) => !commonSelectedTags.value.some((selectedTag) => selectedTag.id === tag.id))
);
const multiSelectClickLabel = computed(() => isMacPlatform() ? "⌘-click" : "Ctrl-click");
const hasTagFilters = computed(() => selectedTagFilters.value.length > 0 || includeUntaggedFilter.value);
const hasRootFilters = computed(() => selectedRootFilters.value.length > 0);
const selectedImages = computed(() => images.value.filter((image) => selectedImageIds.value.has(image.id)));
const hasSingleSelectedImage = computed(() => selectedImages.value.length === 1);
const hasSelectedTags = computed(() => selectedTagSummaries.value.length > 0);
const commonSelectedTags = computed(() =>
  selectedTagSummaries.value.filter((tag) => tag.count === selectedImages.value.length)
);
const partialSelectedTags = computed(() =>
  selectedTagSummaries.value.filter((tag) => tag.count > 0 && tag.count < selectedImages.value.length)
);
const detailTitle = computed(() =>
  selectedImages.value.length > 1 ? `${selectedImages.value.length} images selected` : selectedImage.value?.path_relative
);
const moveChooserSummary = computed(() =>
  selectedImages.value.length === 1 ? selectedImage.value?.path_relative : `${selectedImages.value.length} images selected`
);
const activeScanJobs = computed(() => scanJobs.value.filter(isActiveScan));
const latestScanJob = computed(() => activeScanJobs.value[0] ?? latestFinishedScanJob.value);
const scanInProgress = computed(() => activeScanJobs.value.length > 0);
const hasCancelableScans = computed(() => scanJobs.value.some(isCancelableScan));
const scanStatusMessage = computed(() => {
  const job = latestScanJob.value;
  if (!job) return "";
  const path = job.current_path ?? job.root_path;
  if (job.status === "queued") {
    return path ? `Scan queued: ${path}` : "Scan queued";
  }
  if (job.status === "running") {
    return path ? `Scanning: ${path}` : "Scan running";
  }
  if (job.status === "canceling") {
    return path ? `Canceling scan: ${path}` : "Canceling scan";
  }
  if (job.status === "canceled") {
    return path ? `Scan canceled: ${path}` : "Scan canceled";
  }
  return "";
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

async function withRootChooserErrors(work: () => Promise<void>): Promise<void> {
  rootChooserErrorMessage.value = "";
  busy.value = true;
  try {
    await work();
  } catch (error) {
    rootChooserErrorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    busy.value = false;
  }
}

async function withMoveChooserErrors(work: () => Promise<void>): Promise<void> {
  moveChooserErrorMessage.value = "";
  busy.value = true;
  try {
    await work();
  } catch (error) {
    moveChooserErrorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    busy.value = false;
  }
}

async function withSettingsErrors(work: () => Promise<void>): Promise<void> {
  settingsErrorMessage.value = "";
  busy.value = true;
  try {
    await work();
  } catch (error) {
    settingsErrorMessage.value = error instanceof Error ? error.message : String(error);
  } finally {
    busy.value = false;
  }
}

async function reloadAll(): Promise<void> {
  await withErrors(loadLibraryState);
}

async function loadInitialState(): Promise<void> {
  busy.value = true;
  for (let attempt = 1; attempt <= 30; attempt += 1) {
    try {
      errorMessage.value = attempt === 1 ? "Starting backend..." : errorMessage.value;
      await loadLibraryState();
      errorMessage.value = "";
      busy.value = false;
      return;
    } catch (error) {
      if (attempt === 30) {
        errorMessage.value = error instanceof Error ? error.message : String(error);
        busy.value = false;
        return;
      }
      await delay(500);
    }
  }
}

async function loadLibraryState(): Promise<void> {
  roots.value = await listRoots();
  const knownJobs = await listScanJobs();
  scanJobs.value = knownJobs.filter(isActiveScan);
  tags.value = await listTags();
  await reloadImages();
}

async function reloadImages(): Promise<void> {
  images.value = await listImages({
    tags: selectedTagFilters.value,
    rootIds: selectedRootFilters.value,
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

function openImageFile(image: LibraryImage): void {
  window.open(assetUrl(`images/${image.id}/file`), "_blank", "noreferrer");
}

function isMacPlatform(): boolean {
  return /Mac|iPhone|iPad|iPod/.test(navigator.platform);
}

async function openRootChooser(): Promise<void> {
  rootChooserOpen.value = true;
  rootChooserRecursive.value = true;
  rootChooserErrorMessage.value = "";
  await browseDirectory();
}

function openSettings(): void {
  settingsErrorMessage.value = "";
  settingsOpen.value = true;
}

function handleThemePreferenceChange(): void {
  setThemePreference(themePreference.value);
}

function setThemePreference(preference: ThemePreference): void {
  themePreference.value = preference;
  localStorage.setItem("phag-theme", preference);
  applyThemePreference(preference);
}

function initialThemePreference(): ThemePreference {
  const savedTheme = localStorage.getItem("phag-theme");
  if (savedTheme === "light" || savedTheme === "dark" || savedTheme === "system") return savedTheme;
  return "system";
}

function getSystemThemeMode(): ThemeMode {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyThemePreference(preference: ThemePreference): void {
  if (preference === "system") {
    delete document.documentElement.dataset.theme;
    return;
  }
  document.documentElement.dataset.theme = preference;
}

async function browseDirectory(path?: string): Promise<void> {
  await withRootChooserErrors(async () => {
    directoryListing.value = await listDirectories(path);
  });
}

async function browseMoveDirectory(path?: string): Promise<void> {
  await withMoveChooserErrors(async () => {
    moveDirectoryListing.value = await listDirectories(path);
  });
}

async function openMoveChooser(): Promise<void> {
  if (!selectedImages.value.length) return;
  moveChooserOpen.value = true;
  moveChooserErrorMessage.value = "";
  await browseMoveDirectory();
}

async function handleMoveSelectedImages(): Promise<void> {
  const destinationDirectory = moveDirectoryListing.value?.path;
  const imagesToMove = [...selectedImages.value];
  if (!destinationDirectory || !imagesToMove.length) return;

  if (!isDirectoryIndexed(destinationDirectory)) {
    pendingMoveDestination.value = destinationDirectory;
    pendingMoveImages.value = imagesToMove;
    pendingMoveRecursive.value = true;
    untrackedMovePromptOpen.value = true;
    return;
  }

  await performMove(imagesToMove, destinationDirectory, false);
}

async function handleTrackedMoveChoice(): Promise<void> {
  const destinationDirectory = pendingMoveDestination.value;
  const imagesToMove = [...pendingMoveImages.value];
  if (!destinationDirectory || !imagesToMove.length) return;

  untrackedMovePromptOpen.value = false;
  await withMoveChooserErrors(async () => {
    const added = await addRootWithOverlapConfirmation(destinationDirectory, pendingMoveRecursive.value);
    if (!added) {
      restorePendingMove(destinationDirectory, imagesToMove);
      return;
    }
    await loadLibraryState();
    await moveImages(imagesToMove, destinationDirectory, false);
    await startQueuedScan(destinationDirectory);
    clearPendingMove();
    moveChooserOpen.value = false;
    await refreshTagsAndImages();
  });
}

async function handleUntrackedMoveChoice(): Promise<void> {
  const destinationDirectory = pendingMoveDestination.value;
  const imagesToMove = [...pendingMoveImages.value];
  if (!destinationDirectory || !imagesToMove.length) return;

  untrackedMovePromptOpen.value = false;
  await performMove(imagesToMove, destinationDirectory, true);
}

function cancelPendingMove(): void {
  untrackedMovePromptOpen.value = false;
  clearPendingMove();
}

async function performMove(
  imagesToMove: LibraryImage[],
  destinationDirectory: string,
  allowUnindexed: boolean,
): Promise<void> {
  await withMoveChooserErrors(async () => {
    await moveImages(imagesToMove, destinationDirectory, allowUnindexed);
    clearPendingMove();
    moveChooserOpen.value = false;
    await refreshTagsAndImages();
  });
}

async function moveImages(
  imagesToMove: LibraryImage[],
  destinationDirectory: string,
  allowUnindexed: boolean,
): Promise<void> {
  for (const image of imagesToMove) {
    await moveImage(image.id, destinationDirectory, allowUnindexed);
  }
}

function restorePendingMove(destinationDirectory: string, imagesToMove: LibraryImage[]): void {
  pendingMoveDestination.value = destinationDirectory;
  pendingMoveImages.value = imagesToMove;
  untrackedMovePromptOpen.value = true;
}

function clearPendingMove(): void {
  pendingMoveDestination.value = "";
  pendingMoveImages.value = [];
}

function isDirectoryIndexed(directory: string): boolean {
  const normalizedDirectory = normalizePath(directory);
  return roots.value.some((root) => {
    if (!root.enabled) return false;
    const normalizedRoot = normalizePath(root.path);
    return root.recursive ? isSameOrChildPath(normalizedDirectory, normalizedRoot) : normalizedDirectory === normalizedRoot;
  });
}

function normalizePath(path: string): string {
  return path.replace(/[\\/]+$/, "");
}

function isSameOrChildPath(path: string, parentPath: string): boolean {
  return path === parentPath || path.startsWith(`${parentPath}/`) || path.startsWith(`${parentPath}\\`);
}

async function handleAddSelectedRoot(): Promise<void> {
  const path = directoryListing.value?.path;
  if (!path) return;
  await withRootChooserErrors(async () => {
    const added = await addRootWithOverlapConfirmation(path, rootChooserRecursive.value);
    if (!added) return;
    rootChooserOpen.value = false;
    await loadLibraryState();
    await startQueuedScan(path);
  });
}

async function handleScanAll(): Promise<void> {
  await withSettingsErrors(async () => {
    await startQueuedScan();
  });
}

async function handleScanRoot(path: string): Promise<void> {
  await withSettingsErrors(async () => {
    await startQueuedScan(path);
  });
}

async function handleRemoveRoot(rootId: number): Promise<void> {
  await withSettingsErrors(async () => {
    await removeRoot(rootId);
    await loadLibraryState();
    await startQueuedScan();
  });
}

async function handleRootRecursiveChange(root: IndexedRoot, event: Event): Promise<void> {
  const checkbox = event.target as HTMLInputElement;
  const nextRecursive = checkbox.checked;
  if (nextRecursive === root.recursive) return;

  const confirmed = window.confirm("Changing this root setting will rescan the folder now. Continue?");
  if (!confirmed) {
    checkbox.checked = root.recursive;
    return;
  }

  await withSettingsErrors(async () => {
    const updated = await updateRootRecursiveWithOverlapConfirmation(root, nextRecursive);
    if (!updated) {
      checkbox.checked = root.recursive;
      return;
    }
    await loadLibraryState();
    await startQueuedScan(root.path);
  });
}

async function addRootWithOverlapConfirmation(path: string, recursive: boolean): Promise<boolean> {
  try {
    await addRoot(path, recursive);
    return true;
  } catch (error) {
    const detail = rootOverlapDetail(error);
    if (detail?.code === "covered_roots_require_confirmation") {
      const confirmed = window.confirm(replaceCoveredRootsMessage(detail.covered_roots ?? []));
      if (!confirmed) return false;
      await addRoot(path, recursive, true);
      return true;
    }
    if (detail?.code === "root_already_covered") {
      throw new Error(`This folder is already covered by recursive root ${detail.covering_root?.path ?? ""}`.trim());
    }
    throw error;
  }
}

async function updateRootRecursiveWithOverlapConfirmation(root: IndexedRoot, recursive: boolean): Promise<boolean> {
  try {
    await updateRootRecursive(root.id, recursive);
    return true;
  } catch (error) {
    const detail = rootOverlapDetail(error);
    if (detail?.code === "covered_roots_require_confirmation") {
      const confirmed = window.confirm(replaceCoveredRootsMessage(detail.covered_roots ?? []));
      if (!confirmed) return false;
      await updateRootRecursive(root.id, recursive, true);
      return true;
    }
    if (detail?.code === "root_already_covered") {
      throw new Error(`This folder is already covered by recursive root ${detail.covering_root?.path ?? ""}`.trim());
    }
    throw error;
  }
}

function toggleRootFilter(rootId: number): void {
  selectedTagFilters.value = [];
  includeUntaggedFilter.value = false;

  if (selectedRootFilters.value.includes(rootId)) {
    selectedRootFilters.value = selectedRootFilters.value.filter((selectedRootId) => selectedRootId !== rootId);
  } else {
    selectedRootFilters.value = [...selectedRootFilters.value, rootId];
  }

  void reloadImages();
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

async function handleRemoveAllSelectedTags(): Promise<void> {
  if (!selectedTagSummaries.value.length) return;
  if (!window.confirm("Remove all tags from the selected image(s)?")) return;
  await withErrors(async () => {
    for (const tag of selectedTagSummaries.value) {
      for (const imageId of tag.imageIds) {
        await untagImage(imageId, tag.id);
      }
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
  scanJobs.value = scanJobs.value.filter(isActiveScan);
  latestFinishedScanJob.value = null;
  const job = await queueScan(rootPath);
  upsertScanJob(job);
  void pollScanJob(job.id);
}

async function pollScanJob(jobId: string): Promise<void> {
  try {
    while (isActiveScan(findScanJob(jobId))) {
      await delay(1000);
      const job = await getScanJob(jobId);
      upsertScanJob(job);
      if (job.status === "completed") {
        latestFinishedScanJob.value = job;
        scanSummary.value = job.summary;
        removeScanJob(job.id);
        await loadLibraryState();
        return;
      }
      if (job.status === "failed") {
        latestFinishedScanJob.value = job;
        removeScanJob(job.id);
        reportScanError(job.error ?? "Scan failed");
        return;
      }
      if (job.status === "canceled") {
        latestFinishedScanJob.value = job;
        removeScanJob(job.id);
        await loadLibraryState();
        return;
      }
    }
  } catch (error) {
    reportScanError(error instanceof Error ? error.message : String(error));
  }
}

async function handleCancelScan(job: ScanJob): Promise<void> {
  if (!isCancelableScan(job)) return;
  await withSettingsErrors(async () => {
    const canceledJob = await cancelScanJob(job.id);
    upsertScanJob(canceledJob);
    if (canceledJob.status === "canceled") {
      latestFinishedScanJob.value = canceledJob;
      removeScanJob(canceledJob.id);
      await loadLibraryState();
    }
  });
}

async function handleCancelAllScans(): Promise<void> {
  await withSettingsErrors(async () => {
    const response = await cancelAllScanJobs();
    for (const job of response.jobs) {
      if (isActiveScan(job)) {
        upsertScanJob(job);
      } else {
        latestFinishedScanJob.value = job.status === "canceled" ? job : latestFinishedScanJob.value;
        removeScanJob(job.id);
      }
    }
    await loadLibraryState();
  });
}

function reportScanError(message: string): void {
  if (settingsOpen.value) {
    settingsErrorMessage.value = message;
  } else {
    errorMessage.value = message;
  }
}

function upsertScanJob(job: ScanJob): void {
  const index = scanJobs.value.findIndex((existingJob) => existingJob.id === job.id);
  if (index === -1) {
    scanJobs.value = [job, ...scanJobs.value];
    return;
  }

  const nextJobs = [...scanJobs.value];
  nextJobs[index] = job;
  scanJobs.value = nextJobs;
}

function findScanJob(jobId: string): ScanJob | null {
  return scanJobs.value.find((job) => job.id === jobId) ?? null;
}

function removeScanJob(jobId: string): void {
  scanJobs.value = scanJobs.value.filter((job) => job.id !== jobId);
}

function isActiveScan(job: ScanJob | null): boolean {
  return job?.status === "queued" || job?.status === "running" || job?.status === "canceling";
}

function isCancelableScan(job: ScanJob | null): boolean {
  return job?.status === "queued" || job?.status === "running";
}

function scanJobLabel(job: ScanJob): string {
  switch (job.status) {
    case "queued":
      return "Queued";
    case "running":
      return "Running";
    case "canceling":
      return "Canceling";
    case "canceled":
      return "Canceled";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
  }
  return job.status;
}

function rootOverlapDetail(error: unknown): RootOverlapDetail | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  if (!error.detail || typeof error.detail !== "object") return null;
  const detail = error.detail as Partial<RootOverlapDetail>;
  if (detail.code !== "root_already_covered" && detail.code !== "covered_roots_require_confirmation") return null;
  return detail as RootOverlapDetail;
}

function replaceCoveredRootsMessage(coveredRoots: { path: string }[]): string {
  const paths = coveredRoots.map((root) => root.path).join("\n");
  return `This folder contains existing library roots. Replace them with this parent folder and rescan?\n\n${paths}`;
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
  selectedRootFilters.value = [];
  const index = selectedTagFilters.value.indexOf(tagName);
  if (index >= 0) {
    selectedTagFilters.value.splice(index, 1);
  } else {
    selectedTagFilters.value.push(tagName);
  }
  void reloadImages();
}

function handleUntaggedFilterChange(): void {
  selectedRootFilters.value = [];
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

const systemThemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
const handleSystemThemeChange = (): void => {
  systemThemeMode.value = getSystemThemeMode();
};

applyThemePreference(themePreference.value);
onMounted(() => {
  systemThemeQuery.addEventListener("change", handleSystemThemeChange);
  void loadInitialState();
});
onUnmounted(() => {
  systemThemeQuery.removeEventListener("change", handleSystemThemeChange);
});
</script>
