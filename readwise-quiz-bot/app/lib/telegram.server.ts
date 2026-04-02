import { Bot } from "grammy";
import { prisma } from "./db.server";
import { validateToken, syncHighlightsForUser } from "./readwise.server";
import { generateQuiz } from "./quiz.server";

export const bot = new Bot(process.env.TELEGRAM_BOT_TOKEN || "");

bot.command("start", async (ctx) => {
  const chatId = ctx.chat.id;

  await prisma.user.upsert({
    where: { telegramChatId: BigInt(chatId) },
    create: { telegramChatId: BigInt(chatId) },
    update: {},
  });

  await ctx.reply(
    `Welcome to Readwise Quiz Bot! 📚\n\n` +
      `I'll help you review and remember what you've read by sending you quizzes based on your Readwise highlights.\n\n` +
      `To get started, send me your Readwise access token:\n` +
      `/token YOUR_TOKEN\n\n` +
      `You can get your token at: https://readwise.io/access_token\n\n` +
      `Commands:\n` +
      `/token <token> - Set your Readwise token\n` +
      `/sync - Sync your highlights\n` +
      `/quiz - Get a quiz question\n` +
      `/summary - Get a random highlight summary`
  );
});

bot.command("token", async (ctx) => {
  const chatId = ctx.chat.id;
  const token = ctx.match?.trim();

  if (!token) {
    await ctx.reply(
      "Please provide your token: /token YOUR_TOKEN\n\nGet it at: https://readwise.io/access_token"
    );
    return;
  }

  const valid = await validateToken(token);
  if (!valid) {
    await ctx.reply("Invalid token. Please check and try again.");
    return;
  }

  await prisma.user.upsert({
    where: { telegramChatId: BigInt(chatId) },
    create: { telegramChatId: BigInt(chatId), readwiseToken: token },
    update: { readwiseToken: token },
  });

  await ctx.reply(
    "Token saved! Now run /sync to import your highlights."
  );
});

bot.command("sync", async (ctx) => {
  const chatId = ctx.chat.id;
  const user = await prisma.user.findUnique({
    where: { telegramChatId: BigInt(chatId) },
  });

  if (!user?.readwiseToken) {
    await ctx.reply("Please set your Readwise token first with /token");
    return;
  }

  await ctx.reply("Syncing your highlights... This may take a moment.");

  try {
    const count = await syncHighlightsForUser(user.id);
    await ctx.reply(`Synced ${count} highlights! You can now use /quiz or /summary.`);
  } catch (error) {
    await ctx.reply("Failed to sync highlights. Please check your token and try again.");
  }
});

bot.command("quiz", async (ctx) => {
  const chatId = ctx.chat.id;
  await sendQuizToChat(chatId);
});

bot.command("summary", async (ctx) => {
  const chatId = ctx.chat.id;
  await sendSummaryToChat(chatId);
});

bot.on("message:text", async (ctx) => {
  const chatId = ctx.chat.id;
  const text = ctx.message.text;

  if (text.startsWith("/")) return;

  const user = await prisma.user.findUnique({
    where: { telegramChatId: BigInt(chatId) },
  });

  if (!user?.pendingQuizId) {
    await ctx.reply("Send /quiz for a question or /summary for a highlight!");
    return;
  }

  const quiz = await prisma.quiz.findUnique({
    where: { id: user.pendingQuizId },
    include: { highlight: true },
  });

  if (!quiz) {
    await prisma.user.update({
      where: { id: user.id },
      data: { pendingQuizId: null },
    });
    await ctx.reply("That quiz expired. Send /quiz for a new one!");
    return;
  }

  const userAnswer = text.trim().toUpperCase().charAt(0);
  const correct = userAnswer === quiz.correctAnswer;

  await prisma.quiz.update({
    where: { id: quiz.id },
    data: {
      userAnswer,
      correct,
      answeredAt: new Date(),
    },
  });

  await prisma.user.update({
    where: { id: user.id },
    data: { pendingQuizId: null },
  });

  if (correct) {
    await ctx.reply(
      `Correct! ✅\n\nThe highlight was from "${quiz.highlight.bookTitle}":\n"${quiz.highlight.text}"`
    );
  } else {
    await ctx.reply(
      `Not quite! The answer was ${quiz.correctAnswer}.\n\n` +
        `The highlight was from "${quiz.highlight.bookTitle}":\n"${quiz.highlight.text}"`
    );
  }
});

export async function sendQuizToChat(chatId: number | bigint) {
  const user = await prisma.user.findUnique({
    where: { telegramChatId: BigInt(chatId) },
    include: { highlights: true },
  });

  if (!user) {
    await bot.api.sendMessage(Number(chatId), "Please /start the bot first.");
    return;
  }

  if (user.highlights.length === 0) {
    await bot.api.sendMessage(
      Number(chatId),
      "No highlights found. Run /sync to import them from Readwise."
    );
    return;
  }

  const highlight =
    user.highlights[Math.floor(Math.random() * user.highlights.length)];

  try {
    const quizData = await generateQuiz(
      highlight.text,
      highlight.bookTitle,
      highlight.bookAuthor
    );

    const quiz = await prisma.quiz.create({
      data: {
        userId: user.id,
        highlightId: highlight.id,
        question: quizData.question,
        options: quizData.options,
        correctAnswer: quizData.correctAnswer,
      },
    });

    await prisma.user.update({
      where: { id: user.id },
      data: { pendingQuizId: quiz.id },
    });

    const optionsText = (quizData.options as string[]).join("\n");
    await bot.api.sendMessage(
      Number(chatId),
      `📝 Quiz time!\n\n${quizData.question}\n\n${optionsText}\n\nReply with the letter (A, B, C, or D)`
    );
  } catch (error) {
    await bot.api.sendMessage(
      Number(chatId),
      "Failed to generate quiz. Please try again with /quiz."
    );
  }
}

export async function sendSummaryToChat(chatId: number | bigint) {
  const user = await prisma.user.findUnique({
    where: { telegramChatId: BigInt(chatId) },
    include: { highlights: true },
  });

  if (!user) {
    await bot.api.sendMessage(Number(chatId), "Please /start the bot first.");
    return;
  }

  if (user.highlights.length === 0) {
    await bot.api.sendMessage(
      Number(chatId),
      "No highlights found. Run /sync to import them from Readwise."
    );
    return;
  }

  const highlight =
    user.highlights[Math.floor(Math.random() * user.highlights.length)];

  const author = highlight.bookAuthor
    ? ` by ${highlight.bookAuthor}`
    : "";

  let message = `📖 From "${highlight.bookTitle}"${author}:\n\n"${highlight.text}"`;

  if (highlight.note) {
    message += `\n\n📝 Your note: ${highlight.note}`;
  }

  await bot.api.sendMessage(Number(chatId), message);
}
