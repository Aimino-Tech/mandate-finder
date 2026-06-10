<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Pipeline Monitor</h1>
      <select v-model="days" @change="fetchData" class="px-3 py-1.5 border rounded-lg text-sm dark:bg-gray-800 dark:border-gray-700">
        <option :value="7">7 days</option>
        <option :value="30">30 days</option>
        <option :value="90">90 days</option>
      </select>
    </div>
    <div v-if="loading" class="text-center py-12 text-gray-400">Loading...</div>
    <template v-else>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <StatCard title="Jobs Ingested" :value="totals.jobs_ingested || 0" icon="📥" />
        <StatCard title="Jobs Enriched" :value="totals.jobs_enriched || 0" icon="🔧" />
        <StatCard title="Jobs Scored" :value="totals.jobs_scored || 0" icon="⭐" />
        <StatCard title="AGI Processed" :value="totals.agi_processed ?? 0" icon="🤖" />
        <StatCard title="AGI Matched" :value="totals.agi_matched ?? 0" icon="🎯" />
        <StatCard title="AGI Outreach" :value="totals.agi_outreach_generated ?? 0" icon="📤" />
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <MetricChart title="Ingested" :data="pipeline.ingested || []" color="#3b82f6" />
        <MetricChart title="Enriched" :data="pipeline.enriched || []" color="#10b981" />
        <MetricChart title="Scored" :data="pipeline.scored || []" color="#f59e0b" />
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <MetricChart title="AGI Processed" :data="pipeline.agi_processed || []" color="#8b5cf6" />
        <MetricChart title="AGI Matched" :data="pipeline.agi_matched || []" color="#ec4899" />
        <MetricChart title="AGI Outreach" :data="pipeline.agi_outreach_generated || []" color="#14b8a6" />
      </div>
      <div v-if="Object.keys(sources).length" class="mt-6">
        <h2 class="text-lg font-semibold mb-4">Per-Source Breakdown</h2>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <MetricChart
            v-for="(points, src) in sources" :key="src"
            :title="'Source: ' + src" :data="points"
            color="#3b82f6"
          />
        </div>
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
const pipeline = reactive<Record<string, { date: string; value: number }[]>>({});
const sources = reactive<Record<string, { date: string; value: number }[]>>({});
const totals = reactive<Record<string, number>>({});

async function fetchData() {
  loading.value = true;
  try {
    const [p, s] = await Promise.all([api.getPipeline(days.value), api.getPipelineSources(days.value)]);
    Object.assign(pipeline, p);
    Object.assign(sources, s.sources);
    Object.assign(totals, s.totals);
  } catch (e) { console.error(e); }
  finally { loading.value = false; }
}
fetchData();
</script>
