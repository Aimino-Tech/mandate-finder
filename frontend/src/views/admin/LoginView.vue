<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100 dark:bg-gray-950">
    <div class="bg-white dark:bg-gray-900 p-8 rounded-xl shadow-lg w-full max-w-sm">
      <h1 class="text-2xl font-bold mb-6 text-center">Admin Login</h1>
      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1">API Key</label>
          <input v-model="apiKey" type="password" required placeholder="mf_..." class="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 focus:ring-2 focus:ring-blue-500 outline-none" />
        </div>
        <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
        <button type="submit" :disabled="loading" class="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50">
          {{ loading ? "Verifying..." : "Sign In" }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const apiKey = ref("");
const error = ref("");
const loading = ref(false);

async function handleLogin() {
  loading.value = true;
  error.value = "";
  localStorage.setItem("admin_token", apiKey.value);
  try {
    const res = await fetch("/api/v1/admin/dashboard", {
      headers: { Authorization: `Bearer ${apiKey.value}` },
    });
    if (res.ok) {
      router.push("/admin/dashboard");
    } else if (res.status === 403) {
      localStorage.removeItem("admin_token");
      error.value = "This API key does not have admin access (agency tier required)";
    } else {
      localStorage.removeItem("admin_token");
      error.value = "Invalid API key";
    }
  } catch {
    localStorage.removeItem("admin_token");
    error.value = "Could not connect to server";
  } finally {
    loading.value = false;
  }
}
</script>
