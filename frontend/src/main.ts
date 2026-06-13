import { createApp } from "vue";
import * as Sentry from "@sentry/vue";
import App from "./App.vue";
import router from "./router";

const app = createApp(App);

if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    app,
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    integrations: [
      Sentry.browserTracingIntegration({ router }),
      Sentry.replayIntegration(),
    ],
    tracesSampleRate: import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE
      ? parseFloat(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE)
      : 0.1,
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
  });
}

app.use(router).mount("#app");
