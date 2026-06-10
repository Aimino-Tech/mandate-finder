<template>
  <div class="bg-white dark:bg-gray-900 rounded-xl p-5 shadow-sm border border-gray-200 dark:border-gray-800">
    <h3 class="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">{{ title }}</h3>
    <div v-if="!data || data.length === 0" class="text-center py-8 text-gray-400 text-sm">No data</div>
    <Line v-else :data="chartData" :options="chartOptions" class="max-h-64" />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler } from "chart.js";
import { Line } from "vue-chartjs";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

const props = defineProps<{
  title: string;
  data: { date: string; value: number }[];
  color?: string;
  fill?: boolean;
}>();

const chartData = computed(() => ({
  labels: props.data.map((d) => {
    const p = d.date.split("-");
    return p.length >= 3 ? `${p[1]}/${p[2]}` : d.date;
  }),
  datasets: [
    {
      label: props.title,
      data: props.data.map((d) => d.value),
      borderColor: props.color || "#3b82f6",
      backgroundColor: props.fill ? (props.color || "#3b82f6") + "20" : "transparent",
      fill: props.fill ?? false,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 5,
    },
  ],
}));

const chartOptions = {
  responsive: true,
  maintainAspectRatio: true,
  plugins: {
    legend: { display: false },
    tooltip: { backgroundColor: "#1f2937", titleColor: "#f9fafb", bodyColor: "#d1d5db", cornerRadius: 8, padding: 10 },
  },
  scales: {
    x: { grid: { display: false }, ticks: { color: "#9ca3af", font: { size: 11 } } },
    y: { grid: { color: "#f3f4f6" }, ticks: { color: "#9ca3af", font: { size: 11 } }, beginAtZero: true },
  },
};
</script>
