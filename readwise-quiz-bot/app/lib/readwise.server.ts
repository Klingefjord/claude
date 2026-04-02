import { prisma } from "./db.server";

const READWISE_BASE_URL = "https://readwise.io/api/v2";

interface ReadwiseHighlight {
  id: number;
  text: string;
  note: string;
  book_id: number;
}

interface ReadwiseBook {
  id: number;
  title: string;
  author: string;
  source_url: string | null;
  highlights: ReadwiseHighlight[];
}

interface ExportResponse {
  count: number;
  nextPageCursor: string | null;
  results: ReadwiseBook[];
}

export async function validateToken(token: string): Promise<boolean> {
  const res = await fetch(`${READWISE_BASE_URL}/auth/`, {
    headers: { Authorization: `Token ${token}` },
  });
  return res.status === 204;
}

export async function fetchHighlights(
  token: string,
  updatedAfter?: string
): Promise<{ text: string; note: string; readwiseId: number; bookTitle: string; bookAuthor: string; sourceUrl: string | null }[]> {
  const highlights: {
    text: string;
    note: string;
    readwiseId: number;
    bookTitle: string;
    bookAuthor: string;
    sourceUrl: string | null;
  }[] = [];

  let pageCursor: string | null = null;

  do {
    const params = new URLSearchParams();
    if (pageCursor) params.set("pageCursor", pageCursor);
    if (updatedAfter) params.set("updatedAfter", updatedAfter);

    const res = await fetch(`${READWISE_BASE_URL}/export/?${params}`, {
      headers: { Authorization: `Token ${token}` },
    });

    if (!res.ok) {
      throw new Error(`Readwise API error: ${res.status} ${res.statusText}`);
    }

    const data: ExportResponse = await res.json();
    pageCursor = data.nextPageCursor;

    for (const book of data.results) {
      for (const hl of book.highlights) {
        highlights.push({
          readwiseId: hl.id,
          text: hl.text,
          note: hl.note,
          bookTitle: book.title,
          bookAuthor: book.author,
          sourceUrl: book.source_url,
        });
      }
    }
  } while (pageCursor);

  return highlights;
}

export async function syncHighlightsForUser(userId: string): Promise<number> {
  const user = await prisma.user.findUniqueOrThrow({
    where: { id: userId },
  });

  if (!user.readwiseToken) {
    throw new Error("No Readwise token configured");
  }

  const updatedAfter = user.lastSyncedAt?.toISOString();
  const highlights = await fetchHighlights(user.readwiseToken, updatedAfter);

  let count = 0;
  for (const hl of highlights) {
    await prisma.highlight.upsert({
      where: { readwiseId: hl.readwiseId },
      create: {
        readwiseId: hl.readwiseId,
        text: hl.text,
        note: hl.note || null,
        bookTitle: hl.bookTitle,
        bookAuthor: hl.bookAuthor || null,
        sourceUrl: hl.sourceUrl,
        userId: user.id,
      },
      update: {
        text: hl.text,
        note: hl.note || null,
        bookTitle: hl.bookTitle,
        bookAuthor: hl.bookAuthor || null,
        sourceUrl: hl.sourceUrl,
      },
    });
    count++;
  }

  await prisma.user.update({
    where: { id: user.id },
    data: { lastSyncedAt: new Date() },
  });

  return count;
}
