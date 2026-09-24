import { expect, test } from "bun:test";
import { chatProgressLabel } from "./chatProgress";

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
