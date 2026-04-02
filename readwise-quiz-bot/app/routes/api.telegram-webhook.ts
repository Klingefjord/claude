import { webhookCallback } from "grammy/web";
import { bot } from "../lib/telegram.server";
import type { Route } from "./+types/api.telegram-webhook";

export async function action({ request }: Route.ActionArgs) {
  const secretToken = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
  if (secretToken !== process.env.TELEGRAM_WEBHOOK_SECRET) {
    return new Response("Unauthorized", { status: 401 });
  }

  try {
    const handler = webhookCallback(bot, "std/http");
    return handler(request);
  } catch (error) {
    console.error("Webhook error:", error);
    return new Response("Internal Server Error", { status: 500 });
  }
}
