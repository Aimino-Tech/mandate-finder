<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-800">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400">{{ title }}</h3>
      <span class="text-xl">{{ icon }}</span>
    </div>
    <p class="text-2xl font-bold">{{ formattedValue }}</p>
    <p v-if="subtitle" class="text-xs text-gray-400 mt-1">{{ subtitle }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  title: string;
  value: number | string;
  icon?: string;
  subtitle?: string;
  format?: "currency" | "number" | "percent";
}>();

const formattedValue = computed(() => {
  if (typeof props.value === "string") return props.value;
  switch (props.format) {
    case "currency":
      return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0 }).format(props.value);
    case "percent":
      return `${(props.value * 100).toFixed(1)}%`;
    default:
      return new Intl.NumberFormat("en-US").format(props.value);
  }
});
</script>
