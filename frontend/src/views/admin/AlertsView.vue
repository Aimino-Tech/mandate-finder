<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Alerts</h1>
      <button @click="showForm = true" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">+ New Alert</button>
    </div>
    <div v-if="loading" class="text-center py-12 text-gray-400">Loading...</div>

    <div v-if="showForm" class="bg-white dark:bg-gray-900 rounded-xl p-6 shadow-sm border mb-6">
      <h2 class="text-lg font-semibold mb-4">Create Alert</h2>
      <form @submit.prevent="createAlert" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium mb-1">Metric</label>
          <select v-model="form.metric_type" required class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800">
            <option value="error_rate">Error Rate</option>
            <option value="worker_queue_depth">Queue Depth</option>
            <option value="api_latency_p95">P95 Latency</option>
            <option value="jobs_ingested">Jobs Ingested</option>
            <option value="churn_rate">Churn Rate</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Condition</label>
          <select v-model="form.condition" required class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800">
            <option value="gt">&gt;</option>
            <option value="lt">&lt;</option>
            <option value="gte">&gt;=</option>
            <option value="lte">&lt;=</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Threshold</label>
          <input v-model.number="form.threshold" type="number" step="any" required class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Window (min)</label>
          <input v-model.number="form.window_minutes" type="number" required class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800" />
        </div>
        <div class="md:col-span-2">
          <label class="block text-sm font-medium mb-1">Slack Webhook (optional)</label>
          <input v-model="form.slack_webhook_url" type="url" placeholder="https://hooks.slack.com/..." class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800" />
        </div>
        <div class="flex items-end gap-2">
          <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">Save</button>
          <button type="button" @click="showForm = false" class="px-4 py-2 border rounded-lg text-sm hover:bg-gray-100 dark:border-gray-700">Cancel</button>
        </div>
      </form>
    </div>

    <div v-for="a in alerts" :key="a.id" class="bg-white dark:bg-gray-900 rounded-xl p-5 shadow-sm border mb-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <span class="w-2 h-2 rounded-full" :class="a.enabled ? 'bg-green-500' : 'bg-gray-300'" />
          <div>
            <p class="font-medium">{{ a.metric_type }} <span class="text-gray-500 font-normal">{{ a.condition }} {{ a.threshold }}</span></p>
            <p class="text-xs text-gray-400 mt-0.5">{{ a.window_minutes }}min window<span v-if="a.last_triggered_at"> · Last: {{ fmt(a.last_triggered_at) }}</span></p>
          </div>
        </div>
        <div class="flex gap-2">
          <button @click="toggle(a)" class="px-2 py-1 text-xs border rounded hover:bg-gray-100 dark:border-gray-700">{{ a.enabled ? "Disable" : "Enable" }}</button>
          <button @click="remove(a.id)" class="px-2 py-1 text-xs bg-red-50 text-red-600 rounded hover:bg-red-100">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { useAdminApi } from "@/composables/useAdminApi";

const api = useAdminApi();
const loading = ref(true);
const showForm = ref(false);
const alerts = ref<Record<string, unknown>[]>([]);
const form = reactive({ metric_type: "error_rate", condition: "gt", threshold: 0.1, window_minutes: 15, slack_webhook_url: "" });

function fmt(d: string) { return new Date(d).toLocaleString(); }

async function fetchAlerts() {
  loading.value = true;
  try { alerts.value = await api.getAlerts(); }
  catch (e) { console.error(e); }
  finally { loading.value = false; }
}

async function createAlert() {
  try {
    await api.createAlert({
      metric_type: form.metric_type, condition: form.condition,
      threshold: form.threshold, window_minutes: form.window_minutes,
      slack_webhook_url: form.slack_webhook_url || null,
    });
    showForm.value = false;
    fetchAlerts();
  } catch (e) { console.error(e); }
}

async function toggle(a: Record<string, unknown>) {
  try { await api.updateAlert(a.id as string, { enabled: !a.enabled }); fetchAlerts(); }
  catch (e) { console.error(e); }
}

async function remove(id: string) {
  if (!confirm("Delete alert?")) return;
  try { await api.deleteAlert(id); fetchAlerts(); }
  catch (e) { console.error(e); }
}

fetchAlerts();
</script>
