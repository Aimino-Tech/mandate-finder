import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { sentryVitePlugin } from "@sentry/vite-plugin";
import { resolve } from "path";

export default defineConfig({
  plugins: [
    vue(),
    sentryVitePlugin({
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      telemetry: false,
    }),
  ],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
