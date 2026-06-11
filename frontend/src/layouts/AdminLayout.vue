<template>
  <div class="flex h-screen">
    <aside class="w-64 bg-gray-900 text-white flex flex-col shrink-0">
      <div class="p-4 border-b border-gray-700">
        <h1 class="text-lg font-bold">Mandate Finder</h1>
        <p class="text-xs text-gray-400">Admin Dashboard</p>
      </div>
      <nav class="flex-1 p-2 space-y-1">
        <router-link
          v-for="item in navItems" :key="item.to" :to="item.to"
          class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors"
          :class="isActive(item.to) ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800 hover:text-white'"
        >
          <span class="text-lg">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="p-4 border-t border-gray-700">
        <button
          @click="handleLogout"
          class="flex items-center gap-2 text-sm text-gray-400 hover:text-white w-full px-3 py-2 rounded-lg hover:bg-gray-800"
        >
          <span>🚪</span> Logout
        </button>
      </div>
    </aside>
    <main class="flex-1 overflow-auto bg-gray-50 dark:bg-gray-950"><div class="p-6"><router-view /></div></main>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();
const navItems = [
  { to: "/admin/dashboard", label: "Dashboard", icon: "📊" },
  { to: "/admin/pipeline", label: "Pipeline", icon: "🔗" },
  { to: "/admin/outreach", label: "Outreach", icon: "📤" },
  { to: "/admin/health", label: "System Health", icon: "❤️" },
  { to: "/admin/api-keys", label: "API Keys", icon: "🔑" },
  { to: "/admin/crm", label: "CRM", icon: "📞" },
  { to: "/admin/alerts", label: "Alerts", icon: "🔔" },
  { to: "/admin/billing", label: "Billing", icon: "💳" },
];

function isActive(path: string) { return route.path === path; }
function handleLogout() { localStorage.removeItem("admin_token"); router.push("/admin/login"); }
</script>
