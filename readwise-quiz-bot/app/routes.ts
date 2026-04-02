import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("api/telegram-webhook", "routes/api.telegram-webhook.ts"),
  route("api/cron/daily-quiz", "routes/api.cron.daily-quiz.ts"),
] satisfies RouteConfig;
