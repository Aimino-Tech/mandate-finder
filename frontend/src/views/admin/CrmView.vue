<template>
  <div>
    <h1 class="text-2xl font-bold mb-6">CRM Integrations</h1>

    <div v-if="loading" class="text-center py-12 text-gray-400">Loading...</div>

    <template v-else>
      <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-4 mb-6">
        <h2 class="text-lg font-semibold mb-3">Connect a CRM</h2>
        <div class="flex flex-wrap gap-3 items-end">
          <div>
            <label class="block text-xs text-gray-500 mb-1">CRM</label>
            <select v-model="newCrmType"
              class="px-3 py-1.5 border rounded-lg text-sm dark:bg-gray-800 dark:border-gray-700">
              <option value="pipedrive">Pipedrive (API Token)</option>
              <option value="hubspot">HubSpot (OAuth2)</option>
              <option value="salesforce">Salesforce (OAuth2)</option>
            </select>
          </div>
          <div v-if="newCrmType === 'pipedrive'">
            <label class="block text-xs text-gray-500 mb-1">API Token</label>
            <input v-model="newApiToken" placeholder="Pipedrive API token"
              class="px-3 py-1.5 border rounded-lg text-sm dark:bg-gray-800 dark:border-gray-700 w-72" />
          </div>
          <button @click="handleConnect"
            class="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
            {{ newCrmType === 'pipedrive' ? 'Connect' : 'Connect (uses token field)' }}
          </button>
        </div>
      </div>

      <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th class="text-left px-4 py-3 font-medium">CRM</th>
              <th class="text-left px-4 py-3 font-medium">Label</th>
              <th class="text-center px-4 py-3 font-medium">Auto-Sync</th>
              <th class="text-center px-4 py-3 font-medium">Synced</th>
              <th class="text-center px-4 py-3 font-medium">Status</th>
              <th class="text-left px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!connections.length">
              <td colspan="6" class="text-center py-8 text-gray-400">No CRM connections.</td>
            </tr>
            <tr v-for="c in connections" :key="c.id as string"
              class="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
              <td class="px-4 py-3 font-medium">{{ c.crm_type as string }}</td>
              <td class="px-4 py-3">{{ (c.label as string) || '—' }}</td>
              <td class="px-4 py-3 text-center">
                <button @click="toggleSync(c.id as string, !(c.auto_sync_enabled as boolean))"
                  class="px-3 py-1 rounded text-xs font-medium"
                  :class="c.auto_sync_enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'">
                  {{ c.auto_sync_enabled ? 'ON' : 'OFF' }}
                </button>
              </td>
              <td class="px-4 py-3 text-center">{{ c.synced_lead_count as number }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="c.is_active ? 'text-green-500' : 'text-red-500'">{{ c.is_active ? 'Active' : 'Inactive' }}</span>
              </td>
              <td class="px-4 py-3">
                <button @click="showMapping(c.id as string)" class="text-blue-500 hover:text-blue-700 text-xs mr-2">Mapping</button>
                <button @click="handleDisconnect(c.id as string)" class="text-red-500 hover:text-red-700 text-xs">Disconnect</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex gap-3 mt-4">
        <button @click="handleRetry" class="px-4 py-1.5 bg-yellow-600 text-white rounded-lg text-sm hover:bg-yellow-700">
          Retry Failed
        </button>
        <button @click="fetchHistory" class="px-4 py-1.5 bg-gray-600 text-white rounded-lg text-sm hover:bg-gray-700">
          Refresh History
        </button>
      </div>

      <div v-if="history.length" class="mt-4 bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th class="text-left px-4 py-3 font-medium">Lead ID</th>
              <th class="text-center px-4 py-3 font-medium">Status</th>
              <th class="text-center px-4 py-3 font-medium">Contact</th>
              <th class="text-center px-4 py-3 font-medium">Deal</th>
              <th class="text-left px-4 py-3 font-medium">Error</th>
              <th class="text-left px-4 py-3 font-medium">Time</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in history" :key="e.id as string"
              class="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
              <td class="px-4 py-3 font-mono text-xs">{{ e.lead_id as string }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="e.success ? 'text-green-500' : 'text-red-500'">{{ e.success ? 'OK' : 'FAIL' }}</span>
              </td>
              <td class="px-4 py-3 text-center text-xs">{{ (e.contact_id as string) || '—' }}</td>
              <td class="px-4 py-3 text-center text-xs">{{ (e.deal_id as string) || '—' }}</td>
              <td class="px-4 py-3 text-xs text-red-500">{{ (e.error_message as string) || '—' }}</td>
              <td class="px-4 py-3 text-xs text-gray-500">{{ e.created_at ? fmt(e.created_at as string) : '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="text-sm text-gray-400 p-3 border-t border-gray-100 dark:border-gray-800">Total: {{ total }} entries</p>
      </div>
    </template>

    <div v-if="mappingConnId" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="mappingConnId = ''">
      <div class="bg-white dark:bg-gray-900 rounded-xl shadow-xl border border-gray-200 dark:border-gray-800 p-6 max-w-md w-full mx-4">
        <h3 class="text-lg font-semibold mb-3">Field Mapping</h3>
        <p class="text-xs text-gray-500 mb-3">Map MandateFinder fields to CRM fields.</p>
        <div v-for="(_, idx) in mappingEntries" :key="idx" class="flex gap-2 mb-2">
          <input v-model="mappingEntries[idx].from" placeholder="MF field" class="flex-1 px-2 py-1 border rounded text-sm dark:bg-gray-800 dark:border-gray-700 font-mono text-xs" />
          <span class="self-center text-gray-400">→</span>
          <input v-model="mappingEntries[idx].to" placeholder="CRM field" class="flex-1 px-2 py-1 border rounded text-sm dark:bg-gray-800 dark:border-gray-700 font-mono text-xs" />
          <button @click="mappingEntries.splice(idx, 1)" class="text-red-500 text-xs self-center">✕</button>
        </div>
        <button @click="mappingEntries.push({ from: '', to: '' })" class="text-blue-500 text-xs mb-3">+ Add mapping</button>
        <div class="flex gap-2 justify-end">
          <button @click="mappingConnId = ''" class="px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded text-sm">Cancel</button>
          <button @click="saveMapping" class="px-3 py-1 bg-blue-600 text-white rounded text-sm">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useAdminApi } from "@/composables/useAdminApi";

const api = useAdminApi();
const loading = ref(true);
const connections = ref<Record<string, unknown>[]>([]);
const history = ref<Record<string, unknown>[]>([]);
const total = ref(0);
const newCrmType = ref("pipedrive");
const newApiToken = ref("");
const mappingConnId = ref("");
const mappingEntries = ref<{ from: string; to: string }[]>([]);

function fmt(d: string) { return new Date(d).toLocaleString(); }

async function fetchConnections() {
  loading.value = true;
  try { connections.value = await api.getCRMConnections(); }
  catch (e) { console.error(e); }
  finally { loading.value = false; }
}

async function fetchHistory() {
  try {
    const res = await api.getSyncHistory();
    history.value = res.entries;
    total.value = res.total;
  } catch (e) { console.error(e); }
}

async function handleConnect() {
  try {
    const body: Record<string, unknown> = { crm_type: newCrmType.value };
    if (newCrmType.value === "pipedrive") {
      if (!newApiToken.value.trim()) return;
      body.api_token = newApiToken.value.trim();
    }
    await api.connectCRM(body);
    newApiToken.value = "";
    await fetchConnections();
  } catch (e) { console.error(e); }
}

async function handleDisconnect(id: string) {
  if (!confirm("Disconnect this CRM?")) return;
  try { await api.disconnectCRM(id); await fetchConnections(); }
  catch (e) { console.error(e); }
}

async function toggleSync(id: string, enabled: boolean) {
  try { await api.toggleAutoSync(id, enabled); await fetchConnections(); }
  catch (e) { console.error(e); }
}

async function handleRetry() {
  try { await api.retryFailedSyncs(); await fetchHistory(); await fetchConnections(); }
  catch (e) { console.error(e); }
}

async function showMapping(id: string) {
  mappingConnId.value = id;
  const c = connections.value.find(c => c.id === id);
  const fm = (c?.field_mapping as Record<string, string> | undefined) || {};
  mappingEntries.value = Object.entries(fm).map(([k, v]) => ({ from: k, to: v }));
  if (!mappingEntries.value.length) mappingEntries.value = [{ from: '', to: '' }];
}

async function saveMapping() {
  const fm: Record<string, string> = {};
  for (const e of mappingEntries.value) {
    if (e.from.trim() && e.to.trim()) fm[e.from.trim()] = e.to.trim();
  }
  try { await api.updateFieldMapping(mappingConnId.value, fm); mappingConnId.value = ''; await fetchConnections(); }
  catch (e) { console.error(e); }
}

fetchConnections();
fetchHistory();
</script>
