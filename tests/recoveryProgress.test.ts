import { expect, test } from "bun:test";
import { recoveryProgress } from "../src/ui/resultFormatting";

test("recovery progress explains pending, paced, and nonrecoverable local reads", () => {
  expect(recoveryProgress(undefined, 100)).toBeNull();
  expect(
    recoveryProgress(
      {
        attempt_count: 0,
        last_attempt_at: 0,
        next_attempt_at: 0,
        eligible: false,
      },
      100,
    ),
  ).toBeNull();
  expect(
    recoveryProgress(
      {
        attempt_count: 0,
        last_attempt_at: 0,
        next_attempt_at: 0,
        eligible: true,
      },
      100,
    ),
  ).toBe("First check pending");
  expect(
    recoveryProgress(
      {
        attempt_count: 1,
        last_attempt_at: 100,
        next_attempt_at: 280,
        eligible: true,
      },
      101,
    ),
  ).toBe("next check ~3 min");
  expect(
    recoveryProgress(
      {
        attempt_count: 4,
        last_attempt_at: 100,
        next_attempt_at: 200,
        eligible: true,
      },
      201,
    ),
  ).toBe("Next check queued");
});
