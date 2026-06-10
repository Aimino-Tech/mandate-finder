<template>
  <div>
    <h1 class="text-2xl font-bold mb-6">API Keys</h1>
    <div v-if="loading" class="text-center py-12 text-gray-400">Loading...</div>
    <template v-else>
      <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th class="text-left px-4 py-3 font-medium">Name</th>
              <th class="text-left px-4 py-3 font-medium">Tier</th>
              <th class="text-left px-4 py-3 font-medium">Scopes</th>
              <th class="text-center px-4 py-3 font-medium">Active</th>
              <th class="text-left px-4 py-3 font-medium">Last Used</th>
              <th class="text-left px-4 py-3 font-medium">Created</th>
              <th class="text-left px-4 py-3 font-medium">Expires</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="k in keys" :key="k.id"
              class="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50"
            >
              <td class="px-4 py-3 font-medium">{{ k.name }}</td>
              <td class="px-4 py-3">
                <span class="px-2 py-0.5 rounded-full text-xs" :class="tierClass(k.tier)">{{ k.tier }}</span>
              </td>
              <td class="px-4 py-3 text-gray-500">{{ (k.scopes as string[])?.join(", ") || "—" }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="k.is_active ? 'text-green-500' : 'text-red-500'">{{ k.is_active ? "✓" : "✗" }}</span>
              </td>
              <td class="px-4 py-3 text-gray-500 text-xs">{{ k.last_used_at ? fmt(k.last_used_at as string) : "never" }}</td>
              <td class="px-4 py-3 text-gray-500 text-xs">{{ k.created_at ? fmt(k.created_at as string) : "—" }}</td>
              <td class="px-4 py-3 text-gray-500 text-xs">{{ k.expires_at ? fmt(k.expires_at as string) : "never" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-sm text-gray-400 mt-4">Total: {{ total }} API key(s)</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useAdminApi } from "@/composables/useAdminApi";

const api = useAdminApi();
const loading = ref(true);
const keys = ref<Record<string, unknown>[]>([]);
const total = ref(0);

function fmt(d: string) { return new Date(d).toLocaleString(); }
function tierClass(t: string) {
  const m: Record<string, string> = {
    solo: "bg-blue-100 text-blue-700",
    professional: "bg-purple-100 text-purple-700",
    agency: "bg-green-100 text-green-700",
  };
  return m[t] || "bg-gray-100 text-gray-700";
}

async function fetchKeys() {
  loading.value = true;
  try {
    const res = await api.getApiKeys();
    keys.value = res.api_keys;
    total.value = res.total;
  } catch (e) { console.error(e); }
  finally { loading.value = false; }
}
fetchKeys();
</script>
