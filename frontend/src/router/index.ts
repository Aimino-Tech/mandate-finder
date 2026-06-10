import { createRouter, createWebHistory } from "vue-router";
import AdminLayout from "@/layouts/AdminLayout.vue";
import LoginView from "@/views/admin/LoginView.vue";
import DashboardView from "@/views/admin/DashboardView.vue";
import PipelineView from "@/views/admin/PipelineView.vue";
import HealthView from "@/views/admin/HealthView.vue";
import AlertsView from "@/views/admin/AlertsView.vue";
import ApiKeysView from "@/views/admin/ApiKeysView.vue";

const routes = [
  { path: "/admin/login", name: "Login", component: LoginView },
  {
    path: "/admin",
    component: AdminLayout,
    redirect: "/admin/dashboard",
    children: [
      { path: "dashboard", name: "Dashboard", component: DashboardView },
      { path: "pipeline", name: "Pipeline", component: PipelineView },
      { path: "health", name: "Health", component: HealthView },
      { path: "api-keys", name: "ApiKeys", component: ApiKeysView },
      { path: "alerts", name: "Alerts", component: AlertsView },
    ],
  },
  { path: "/:pathMatch(.*)*", redirect: "/admin/dashboard" },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach((to) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("admin_token");
    if (!token && to.path !== "/admin/login") return { name: "Login" };
  }
});

export default router;
