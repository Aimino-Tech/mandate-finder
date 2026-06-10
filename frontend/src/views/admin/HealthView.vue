<template>
  <div>
    <h1 class="text-2xl font-bold mb-6">System Health</h1>
    <div v-if="loading" class="text-center py-12 text-gray-400">Loading...</div>
    <template v-else>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <StatCard title="Queue Depth" :value="current.worker_queue_depth ?? '-'" icon="📋" />
        <StatCard title="P95 Latency" :value="current.api_latency_p95 ? `${(current.api_latency_p95 * 1000).toFixed(0)}ms` : '-'" icon="⏱️" />
        <StatCard title="Error Rate" :value="current.error_rate ?? '-'" icon="⚠️" format="percent" />
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <MetricChart title="Queue Depth" :data="health.worker_queue_depth || []" color="#f59e0b" :fill="true" />
        <MetricChart title="P95 Latency" :data="health.api_latency_p95 || []" color="#8b5cf6" :fill="true" />
        <MetricChart title="Error Rate" :data="health.error_rate || []" color="#ef4444" :fill="true" />
      </div>
      <div class="mt-6 text-center">
        <a :href="api.getExportUrl('error_rate')" class="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">📥 Download CSV</a>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { useAdminApi } from "@/composables/useAdminApi";
import StatCard from "@/components/admin/StatCard.vue";
import MetricChart from "@/components/admin/MetricChart.vue";

const api = useAdminApi();
const loading = ref(true);
const health = reactive<Record<string, { date: string; value: number }[]>>({});
const current = reactive<Record<string, number>>({});

async function fetchData() {
  loading.value = true;
  try {
    const [h, c] = await Promise.all([api.getHealth(7), api.getHealthCurrent()]);
    Object.assign(health, h);
    Object.assign(current, c);
  } catch (e) { console.error(e); }
  finally { loading.value = false; }
}
fetchData();
</script>
