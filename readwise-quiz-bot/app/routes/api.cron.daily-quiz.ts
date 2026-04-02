import { prisma } from "../lib/db.server";
import { sendQuizToChat } from "../lib/telegram.server";
import type { Route } from "./+types/api.cron.daily-quiz";

export async function loader({ request }: Route.LoaderArgs) {
  const authHeader = request.headers.get("Authorization");
  if (authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
    return new Response("Unauthorized", { status: 401 });
  }

  const users = await prisma.user.findMany({
    where: {
      readwiseToken: { not: null },
      highlights: { some: {} },
    },
  });

  const results = await Promise.allSettled(
    users.map((user) => sendQuizToChat(user.telegramChatId))
  );

  const succeeded = results.filter((r) => r.status === "fulfilled").length;
  const failed = results.filter((r) => r.status === "rejected").length;

  return Response.json({
    ok: true,
    sent: succeeded,
    failed,
    total: users.length,
  });
}
