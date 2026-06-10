<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Dashboard</h1>
      <select v-model="days" @change="fetchData" class="px-3 py-1.5 border rounded-lg text-sm dark:bg-gray-800 dark:border-gray-700">
        <option :value="7">7 days</option>
        <option :value="30">30 days</option>
        <option :value="90">90 days</option>
      </select>
    </div>
    <div v-if="loading" class="text-center py-12 text-gray-400">Loading...</div>
    <template v-else>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <StatCard title="MRR" :value="latest('mrr')" icon="💰" format="currency" :subtitle="trend('mrr')" />
        <StatCard title="Active Users" :value="latest('active_users')" icon="👤" :subtitle="trend('active_users')" />
        <StatCard title="Churn Rate" :value="latest('churn_rate')" icon="📉" format="percent" :subtitle="trend('churn_rate')" />
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <MetricChart title="MRR Trend" :data="data.mrr || []" color="#3b82f6" :fill="true" />
        <MetricChart title="Active Users" :data="data.active_users || []" color="#10b981" :fill="true" />
        <MetricChart title="Churn Rate" :data="data.churn_rate || []" color="#ef4444" />
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
const days = ref(30);
const loading = ref(true);
const data = reactive<Record<string, { date: string; value: number }[]>>({});

function latest(key: string): number {
  const arr = data[key] || [];
  return arr.length > 0 ? arr[arr.length - 1].value : 0;
}
function trend(key: string): string {
  const arr = data[key] || [];
  if (arr.length < 2) return "";
  const pct = ((arr[arr.length - 1].value - arr[arr.length - 2].value) / arr[arr.length - 2].value) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}
async function fetchData() {
  loading.value = true;
  try {
    const res = await api.getDashboard(days.value);
    Object.assign(data, res);
  } catch (e) { console.error(e); }
  finally { loading.value = false; }
}
fetchData();
</script>
