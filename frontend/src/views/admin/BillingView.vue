<template>
  <div>
    <h1 class="text-2xl font-bold mb-6">Billing & Subscription</h1>

    <div v-if="loading" class="text-center py-12 text-gray-400">Loading...</div>

    <template v-else>
      <!-- Current subscription -->
      <div v-if="subscription" class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold">Current Plan</h2>
            <p class="text-sm text-gray-500 mt-1">
              {{ subscription.plan_name || 'Unknown' }}
              <span class="ml-2 px-2 py-0.5 rounded-full text-xs" :class="statusClass(subscription.status)">
                {{ subscription.status }}
              </span>
            </p>
            <p v-if="subscription.trial_end_at" class="text-xs text-gray-400 mt-1">
              Trial ends: {{ fmt(subscription.trial_end_at) }}
            </p>
            <p v-if="subscription.current_period_end" class="text-xs text-gray-400 mt-1">
              Current period ends: {{ fmt(subscription.current_period_end) }}
            </p>
            <p v-if="subscription.canceled_at" class="text-xs text-red-400 mt-1">
              Canceled: {{ fmt(subscription.canceled_at) }}
            </p>
          </div>
          <div class="flex gap-2">
            <button @click="openPortal" class="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
              Billing Portal
            </button>
            <button v-if="subscription.status === 'active' || subscription.status === 'past_due'" @click="handleCancel" class="px-4 py-2 border border-red-300 text-red-600 rounded-lg text-sm hover:bg-red-50 dark:hover:bg-red-900/20">
              Cancel
            </button>
          </div>
        </div>
      </div>

      <!-- No subscription -->
      <div v-if="!subscription">
        <h2 class="text-lg font-semibold mb-4">Choose a Plan</h2>
        <p class="text-sm text-gray-500 mb-6">Start your 14-day free trial. No credit card required.</p>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div v-for="plan in plans" :key="plan.id as string"
            class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border p-6 flex flex-col transition-all hover:shadow-md"
            :class="plan.tier === 'agency' ? 'border-blue-500 ring-2 ring-blue-200 dark:ring-blue-800' : 'border-gray-200 dark:border-gray-800'"
          >
            <div v-if="plan.tier === 'agency'" class="text-xs font-semibold text-blue-600 uppercase mb-2">Best Value</div>
            <h3 class="text-xl font-bold">{{ plan.name as string }}</h3>
            <p class="text-3xl font-bold mt-3">€{{ ((plan.price_monthly_eur as number) / 100).toFixed(2) }}<span class="text-sm font-normal text-gray-500">/mo</span></p>
            <ul class="mt-4 space-y-2 text-sm flex-1">
              <li v-for="(val, key) in (plan.features as Record<string, unknown>)" :key="key"
                class="flex items-center gap-2"
                :class="val ? 'text-gray-700 dark:text-gray-300' : 'text-gray-400 line-through'"
              >
                <span>{{ val ? '✅' : '❌' }}</span>
                {{ featureLabel(key as string) }}
              </li>
            </ul>
            <button @click="handleSubscribe(plan.id as string)"
              class="mt-6 w-full px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              :class="plan.tier === 'agency'
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700'"
            >
              {{ subscription && subscription.plan_id === plan.id ? 'Current Plan' : 'Start Free Trial' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Active subscription - show plan cards for upgrade/downgrade -->
      <div v-if="subscription" class="mb-8">
        <h2 class="text-lg font-semibold mb-4">Change Plan</h2>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div v-for="plan in plans" :key="plan.id as string"
            class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border p-6 flex flex-col transition-all hover:shadow-md"
            :class="plan.id === subscription.plan_id ? 'border-green-500 ring-2 ring-green-200 dark:ring-green-800' : 'border-gray-200 dark:border-gray-800'"
          >
            <h3 class="text-xl font-bold">{{ plan.name as string }}</h3>
            <p class="text-3xl font-bold mt-3">€{{ ((plan.price_monthly_eur as number) / 100).toFixed(2) }}<span class="text-sm font-normal text-gray-500">/mo</span></p>
            <ul class="mt-4 space-y-2 text-sm flex-1">
              <li v-for="(val, key) in (plan.features as Record<string, unknown>)" :key="key"
                class="flex items-center gap-2"
                :class="val ? 'text-gray-700 dark:text-gray-300' : 'text-gray-400 line-through'"
              >
                <span>{{ val ? '✅' : '❌' }}</span>
                {{ featureLabel(key as string) }}
              </li>
            </ul>
            <button v-if="plan.id === subscription.plan_id" disabled
              class="mt-6 w-full px-4 py-2 rounded-lg text-sm font-medium bg-gray-200 dark:bg-gray-700 text-gray-500 cursor-not-allowed">
              Current Plan
            </button>
            <button v-else-if="isUpgrade(plan.id as string)" @click="handleUpgrade(plan.id as string)"
              class="mt-6 w-full px-4 py-2 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700">
              Upgrade
            </button>
            <button v-else @click="handleDowngrade(plan.id as string)"
              class="mt-6 w-full px-4 py-2 rounded-lg text-sm font-medium bg-yellow-600 text-white hover:bg-yellow-700">
              Downgrade
            </button>
          </div>
        </div>
      </div>

      <!-- Invoice history -->
      <div class="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
          <h2 class="text-lg font-semibold">Invoice History</h2>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th class="text-left px-4 py-3 font-medium">Amount</th>
              <th class="text-left px-4 py-3 font-medium">VAT</th>
              <th class="text-left px-4 py-3 font-medium">Total</th>
              <th class="text-center px-4 py-3 font-medium">Status</th>
              <th class="text-left px-4 py-3 font-medium">Date</th>
              <th class="text-left px-4 py-3 font-medium">Invoice</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!invoices.length">
              <td colspan="6" class="text-center py-8 text-gray-400">No invoices yet.</td>
            </tr>
            <tr v-for="inv in invoices" :key="inv.id as string"
              class="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
              <td class="px-4 py-3">€{{ ((inv.amount_eur as number) / 100).toFixed(2) }}</td>
              <td class="px-4 py-3">€{{ ((inv.vat_amount as number) / 100).toFixed(2) }} ({{ inv.vat_percentage }}%)</td>
              <td class="px-4 py-3 font-medium">€{{ ((inv.total_eur as number) / 100).toFixed(2) }}</td>
              <td class="px-4 py-3 text-center">
                <span :class="inv.status === 'paid' ? 'text-green-500' : 'text-red-500'">{{ inv.status }}</span>
              </td>
              <td class="px-4 py-3 text-gray-500">{{ inv.paid_at ? fmt(inv.paid_at) : '—' }}</td>
              <td class="px-4 py-3">
                <a v-if="inv.pdf_url" :href="inv.pdf_url as string" target="_blank" class="text-blue-500 hover:text-blue-700 text-xs">
                  📄 PDF
                </a>
                <span v-else class="text-gray-400 text-xs">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useBillingApi } from "@/composables/useBillingApi";

const api = useBillingApi();
const loading = ref(true);
const plans = ref<Record<string, unknown>[]>([]);
const subscription = ref<Record<string, unknown> | null>(null);
const invoices = ref<Record<string, unknown>[]>([]);

function fmt(d: unknown) {
  if (!d) return "—";
  return new Date(d as string).toLocaleDateString("de-DE", { year: "numeric", month: "short", day: "numeric" });
}

function statusClass(s: string) {
  const m: Record<string, string> = {
    active: "bg-green-100 text-green-700",
    trialing: "bg-blue-100 text-blue-700",
    past_due: "bg-yellow-100 text-yellow-700",
    canceled: "bg-gray-100 text-gray-500",
    incomplete: "bg-red-100 text-red-700",
    none: "bg-gray-100 text-gray-500",
  };
  return m[s] || "bg-gray-100 text-gray-500";
}

function featureLabel(key: string): string {
  const m: Record<string, string> = {
    max_searches: "Maximum Searches",
    max_team_members: "Team Members",
    crm_integrations: "CRM Integrations",
    api_access: "API Access",
    export_csv: "CSV Export",
    priority_support: "Priority Support",
  };
  return m[key] || key;
}

function isUpgrade(planId: string): boolean {
  if (!subscription.value) return false;
  const currentIdx = plans.value.findIndex(p => p.id === subscription.value!.plan_id);
  const newIdx = plans.value.findIndex(p => p.id === planId);
  return newIdx > currentIdx;
}

async function fetchAll() {
  loading.value = true;
  try {
    const [p, s, i] = await Promise.all([
      api.getPlans(),
      api.getSubscription(),
      api.getInvoices(),
    ]);
    plans.value = p;
    subscription.value = s;
    invoices.value = i;
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
}

async function handleSubscribe(planId: string) {
  try {
    await api.subscribe(planId);
    await fetchAll();
  } catch (e) {
    console.error(e);
  }
}

async function handleUpgrade(planId: string) {
  try {
    await api.upgrade(planId);
    await fetchAll();
  } catch (e) {
    console.error(e);
  }
}

async function handleDowngrade(planId: string) {
  try {
    await api.downgrade(planId);
    await fetchAll();
  } catch (e) {
    console.error(e);
  }
}

async function handleCancel() {
  if (!confirm("Cancel your subscription? You will retain access until the end of the billing period.")) return;
  try {
    await api.cancel();
    await fetchAll();
  } catch (e) {
    console.error(e);
  }
}

async function openPortal() {
  try {
    const { url } = await api.getPortalUrl();
    window.open(url, "_blank");
  } catch (e) {
    console.error(e);
  }
}

fetchAll();
</script>
