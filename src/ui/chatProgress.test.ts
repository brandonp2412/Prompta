import { expect, test } from "bun:test";
import { chatProgressLabel } from "./chatProgress";

const appSource = await Bun.file(new URL("./App.svelte", import.meta.url)).text();
const conversationMessagesSource = await Bun.file(
  new URL("./ConversationMessages.svelte", import.meta.url),
).text();

test("cooldown counts down without claiming a retry has started", () => {
  const progress = { phase: "rate_limited", retry_at: 180 };
  expect(chatProgressLabel(progress, 60)).toBe("Waiting for account cooldown · next retry in 2m");
  expect(chatProgressLabel(progress, 181)).toBe("Waiting for account cooldown · retry due");
});
test("delivery receipt is distinct from an assistant response", () => {
  expect(chatProgressLabel({ phase: "succeeded" })).toContain("Confirmed received");
  expect(chatProgressLabel({ phase: "responding" })).toBe("Responding");
  expect(chatProgressLabel({ phase: "recovering" })).toBe("Recovering connection");
  expect(chatProgressLabel({ phase: "queued", queue_position: 4 })).toBe("Queued · #4");
});

test("run progress only renders inside the latest Prompta run bubble", () => {
  expect(appSource).not.toContain("<ChatProgress");
  expect(conversationMessagesSource).toContain('import ChatProgress from "./ChatProgress.svelte";');
  expect(conversationMessagesSource).toContain("latestPendingActivityKey");
  expect(conversationMessagesSource).toContain("<ChatProgress />");
});
