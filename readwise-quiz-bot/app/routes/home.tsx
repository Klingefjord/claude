import type { Route } from "./+types/home";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Readwise Quiz Bot" },
    {
      name: "description",
      content: "A Telegram bot that quizzes you on your Readwise highlights",
    },
  ];
}

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white flex items-center justify-center">
      <div className="max-w-lg mx-auto px-6 text-center">
        <h1 className="text-4xl font-bold mb-4">Readwise Quiz Bot</h1>
        <p className="text-lg text-gray-300 mb-8">
          A Telegram bot that helps you remember what you've read by sending
          daily quizzes based on your Readwise highlights.
        </p>

        <div className="bg-gray-800 rounded-xl p-6 text-left space-y-4 mb-8">
          <h2 className="text-xl font-semibold">How to use</h2>
          <ol className="list-decimal list-inside space-y-2 text-gray-300">
            <li>
              Search for the bot on Telegram
            </li>
            <li>
              Send <code className="bg-gray-700 px-1 rounded">/start</code> to begin
            </li>
            <li>
              Set your Readwise token with{" "}
              <code className="bg-gray-700 px-1 rounded">/token YOUR_TOKEN</code>
            </li>
            <li>
              Run <code className="bg-gray-700 px-1 rounded">/sync</code> to import highlights
            </li>
            <li>
              Get quizzes with{" "}
              <code className="bg-gray-700 px-1 rounded">/quiz</code> or wait for the daily quiz
            </li>
          </ol>
        </div>

        <div className="bg-gray-800 rounded-xl p-6 text-left space-y-3">
          <h2 className="text-xl font-semibold">Commands</h2>
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-gray-300">
            <code className="bg-gray-700 px-2 py-0.5 rounded text-sm">/start</code>
            <span>Register and get instructions</span>
            <code className="bg-gray-700 px-2 py-0.5 rounded text-sm">/token</code>
            <span>Set your Readwise access token</span>
            <code className="bg-gray-700 px-2 py-0.5 rounded text-sm">/sync</code>
            <span>Sync highlights from Readwise</span>
            <code className="bg-gray-700 px-2 py-0.5 rounded text-sm">/quiz</code>
            <span>Get a quiz question</span>
            <code className="bg-gray-700 px-2 py-0.5 rounded text-sm">/summary</code>
            <span>Get a random highlight</span>
          </div>
        </div>
      </div>
    </main>
  );
}
