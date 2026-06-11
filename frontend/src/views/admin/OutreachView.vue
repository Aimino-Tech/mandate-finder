<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Outreach Campaigns</h1>
      <button @click="showForm = true" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">+ New Campaign</button>
    </div>
    <div v-if="loading" class="text-center py-12 text-gray-400">Loading...</div>

    <div v-if="showForm" class="bg-white dark:bg-gray-900 rounded-xl p-6 shadow-sm border mb-6">
      <h2 class="text-lg font-semibold mb-4">Create Campaign</h2>
      <form @submit.prevent="createCampaign" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium mb-1">Campaign Name</label>
          <input v-model="form.name" required class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Target Company</label>
          <input v-model="form.target_company_name" required class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Company Domain</label>
          <input v-model="form.target_company_domain" placeholder="example.com" class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Industry</label>
          <input v-model="form.target_industry" class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800" />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">Tone</label>
          <select v-model="form.tone" class="w-full px-3 py-2 border rounded-lg text-sm dark:bg-gray-800">
            <option value="professional">Professional</option>
            <option value="friendly">Friendly</option>
            <option value="formal">Formal</option>
          </select>
        </div>
        <div class="flex items-end gap-2">
          <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">Save</button>
          <button type="button" @click="showForm = false" class="px-4 py-2 border rounded-lg text-sm hover:bg-gray-100 dark:border-gray-700">Cancel</button>
        </div>
      </form>
    </div>

    <div v-for="c in campaigns" :key="c.id" class="bg-white dark:bg-gray-900 rounded-xl p-5 shadow-sm border mb-3">
      <div class="flex items-center justify-between">
        <div>
          <div class="flex items-center gap-3">
            <span class="w-2 h-2 rounded-full" :class="statusClass(c.status)" />
            <p class="font-medium">{{ c.name }}</p>
            <span class="px-2 py-0.5 rounded-full text-xs" :class="tierClass(c.tone)">{{ c.tone }}</span>
          </div>
          <p class="text-sm text-gray-500 mt-1">{{ c.target_company_name }}<span v-if="c.target_company_domain"> ({{ c.target_company_domain }})</span></p>
          <p class="text-xs text-gray-400 mt-1">
            {{ c.total_messages }} messages · {{ c.sent_count }} sent · {{ c.opened_count }} opened · {{ c.replied_count }} replies
            <span v-if="c.status === 'active'"> · <button @click="pause(c.id)" class="text-yellow-600 hover:underline">Pause</button></span>
            <span v-if="c.status === 'paused'"> · <button @click="resume(c.id)" class="text-green-600 hover:underline">Resume</button></span>
          </p>
        </div>
        <div class="flex gap-2">
          <button v-if="c.status === 'review'" @click="approve(c.id)" class="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700">Approve</button>
          <button v-if="c.status === 'approved'" @click="sendCampaign(c.id)" class="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700">Send</button>
        </div>
      </div>
    </div>
    <p v-if="!loading && campaigns.length === 0" class="text-center py-12 text-gray-400">No campaigns yet</p>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { useAdminApi } from "@/composables/useAdminApi";

const api = useAdminApi();
const loading = ref(true);
const showForm = ref(false);
const campaigns = ref<Record<string, unknown>[]>([]);
const form = reactive({ name: "", target_company_name: "", target_company_domain: "", target_industry: "", tone: "professional" });

function statusClass(s: string) {
  const m: Record<string, string> = { draft: "bg-gray-400", generating: "bg-yellow-400", review: "bg-blue-400", approved: "bg-green-400", active: "bg-green-500", paused: "bg-yellow-500", completed: "bg-gray-400", cancelled: "bg-red-400" };
  return m[s] || "bg-gray-400";
}
function tierClass(t: string) {
  const m: Record<string, string> = { professional: "bg-blue-100 text-blue-700", friendly: "bg-green-100 text-green-700", formal: "bg-purple-100 text-purple-700" };
  return m[t] || "bg-gray-100 text-gray-700";
}

async function fetchCampaigns() {
  loading.value = true;
  try { campaigns.value = await api.getCampaigns(); }
  catch (e) { console.error(e); }
  finally { loading.value = false; }
}

async function createCampaign() {
  try {
    await api.createCampaign({ name: form.name, target_company_name: form.target_company_name, target_company_domain: form.target_company_domain, target_industry: form.target_industry || null, tone: form.tone });
    showForm.value = false;
    fetchCampaigns();
  } catch (e) { console.error(e); }
}

async function approve(id: string) {
  try { await api.approveCampaign(id); fetchCampaigns(); }
  catch (e) { console.error(e); }
}

async function sendCampaign(id: string) {
  try { await api.sendCampaign(id); fetchCampaigns(); }
  catch (e) { console.error(e); }
}

async function pause(id: string) {
  try { await api.pauseCampaign(id); fetchCampaigns(); }
  catch (e) { console.error(e); }
}

async function resume(id: string) {
  try { await api.resumeCampaign(id); fetchCampaigns(); }
  catch (e) { console.error(e); }
}

fetchCampaigns();
</script>
