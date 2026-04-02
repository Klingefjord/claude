import { PrismaNeonHttp } from "@prisma/adapter-neon";
import { PrismaClient } from "../../generated/prisma/client.js";

let prisma: PrismaClient;

declare global {
  var __db__: PrismaClient | undefined;
}

function createClient() {
  const adapter = new PrismaNeonHttp(process.env.DATABASE_URL!, {});
  return new PrismaClient({ adapter });
}

if (process.env.NODE_ENV === "production") {
  prisma = createClient();
} else {
  if (!global.__db__) {
    global.__db__ = createClient();
  }
  prisma = global.__db__;
}

export { prisma };
