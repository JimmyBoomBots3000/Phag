<template>
  <ul class="tag-tree" :class="{ nested }">
    <li v-for="node in nodes" :key="node.fullPath" class="tag-node">
      <div class="tag-node-row">
        <button
          v-if="node.children.length"
          class="tag-disclosure"
          type="button"
          :aria-expanded="isExpanded(node.fullPath)"
          @click="toggleExpanded(node.fullPath)"
        >
          {{ isExpanded(node.fullPath) ? "v" : ">" }}
        </button>
        <span v-else class="tag-disclosure-placeholder"></span>

        <label v-if="node.tag">
          <input
            :checked="selectedTags.includes(node.tag.display_name)"
            type="checkbox"
            @change="toggleTag(node.tag.display_name)"
          />
          <span>{{ node.name }}</span>
        </label>
        <span v-else class="tag-group">{{ node.name }}</span>
      </div>

      <TagTree
        v-if="node.children.length && isExpanded(node.fullPath)"
        :nodes="node.children"
        :selected-tags="selectedTags"
        nested
        @toggle="toggleTag"
      />
    </li>
  </ul>
</template>

<script setup lang="ts">
import { ref } from "vue";
import type { Tag } from "../api";

export interface TagTreeNode {
  name: string;
  fullPath: string;
  tag: Tag | null;
  children: TagTreeNode[];
}

defineProps<{
  nodes: TagTreeNode[];
  selectedTags: string[];
  nested?: boolean;
}>();

const emit = defineEmits<{
  toggle: [tagName: string];
}>();

const expandedPaths = ref<Set<string>>(new Set());

function toggleTag(tagName: string): void {
  emit("toggle", tagName);
}

function isExpanded(path: string): boolean {
  return expandedPaths.value.has(path);
}

function toggleExpanded(path: string): void {
  const nextExpandedPaths = new Set(expandedPaths.value);
  if (nextExpandedPaths.has(path)) {
    nextExpandedPaths.delete(path);
  } else {
    nextExpandedPaths.add(path);
  }
  expandedPaths.value = nextExpandedPaths;
}
</script>
