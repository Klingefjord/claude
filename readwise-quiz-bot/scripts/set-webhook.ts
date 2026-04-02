/**
 * One-time script to register the Telegram webhook URL.
 *
 * Usage:
 *   TELEGRAM_BOT_TOKEN=xxx TELEGRAM_WEBHOOK_SECRET=yyy WEBHOOK_URL=https://your-app.vercel.app/api/telegram-webhook npx tsx scripts/set-webhook.ts
 */

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const WEBHOOK_SECRET = process.env.TELEGRAM_WEBHOOK_SECRET;
const WEBHOOK_URL = process.env.WEBHOOK_URL;

if (!BOT_TOKEN || !WEBHOOK_SECRET || !WEBHOOK_URL) {
  console.error(
    "Missing required env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, WEBHOOK_URL"
  );
  process.exit(1);
}

async function main() {
  const res = await fetch(
    `https://api.telegram.org/bot${BOT_TOKEN}/setWebhook`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: WEBHOOK_URL,
        secret_token: WEBHOOK_SECRET,
      }),
    }
  );

  const data = await res.json();
  console.log("Webhook set:", JSON.stringify(data, null, 2));
}

main().catch(console.error);
