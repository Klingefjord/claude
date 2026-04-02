import Anthropic from "@anthropic-ai/sdk";

const anthropic = new Anthropic();

interface QuizResult {
  question: string;
  options: string[];
  correctAnswer: string;
}

export async function generateQuiz(
  highlightText: string,
  bookTitle: string,
  bookAuthor?: string | null
): Promise<QuizResult> {
  const source = bookAuthor ? `"${bookTitle}" by ${bookAuthor}` : `"${bookTitle}"`;

  const message = await anthropic.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 512,
    messages: [
      {
        role: "user",
        content: `You are a quiz generator. Given this highlight from ${source}, create a multiple-choice question that tests understanding of the concept.

Highlight: "${highlightText}"

Respond in this exact JSON format (no markdown, no code fences):
{"question": "Your question here?", "options": ["A) correct answer", "B) wrong answer", "C) wrong answer", "D) wrong answer"], "correctAnswer": "A"}

Rules:
- The question should test comprehension, not just recall
- Make wrong answers plausible but clearly incorrect
- The correct answer letter should be randomized (not always A)
- Keep the question concise
- Options should start with A), B), C), D)`,
      },
    ],
  });

  const text =
    message.content[0].type === "text" ? message.content[0].text : "";
  const parsed = JSON.parse(text);

  return {
    question: parsed.question,
    options: parsed.options,
    correctAnswer: parsed.correctAnswer,
  };
}
