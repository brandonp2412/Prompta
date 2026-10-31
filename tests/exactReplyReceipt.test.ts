import { expect, test } from "bun:test";
import { exactReplyReceiptState, type ExactReplyPayload } from "../src/ui/exactReplyReceipt";

const expected: ExactReplyPayload = {
  reply_id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  conversation_id: "00000000-0000-4000-8000-000000000001",
  parent_id: "00000000-0000-4000-8000-000000000002",
  text: "Continue with the saved branch",
};
const turn = {
  reply_id: expected.reply_id,
  send_id: "saved-run",
  conversation_id: expected.conversation_id,
  parent_id: expected.parent_id,
  user_text: expected.text,
  status: "prepared",
  queued_by_user: true,
};

test("only a matching, user-authorized exact reply acknowledges a receipt", () => {
  expect(exactReplyReceiptState(turn, expected, "saved-run")).toBe("accepted");
  for (const key of ["reply_id", "conversation_id", "parent_id", "user_text"] as const) {
    expect(exactReplyReceiptState({ ...turn, [key]: "different" }, expected, "saved-run")).toBe(
      "invalid",
    );
  }
  expect(exactReplyReceiptState({ ...turn, send_id: "another-run" }, expected, "saved-run")).toBe(
    "invalid",
  );
  expect(exactReplyReceiptState({ ...turn, queued_by_user: false }, expected, "saved-run")).toBe(
    "not_sent",
  );
  expect(exactReplyReceiptState({ ...turn, status: "unrecognized" }, expected, "saved-run")).toBe(
    "invalid",
  );
  expect(exactReplyReceiptState({ status: "prepared" }, expected, "saved-run")).toBe("invalid");
});

test("ambiguous and preflight failures never erase an uncertain idempotency key", () => {
  expect(
    exactReplyReceiptState({ ...turn, status: "outcome_unknown" }, expected, "saved-run"),
  ).toBe("uncertain");
  expect(
    exactReplyReceiptState({ ...turn, status: "preflight_failed" }, expected, "saved-run"),
  ).toBe("not_sent");
  for (const status of ["dispatching", "accepted", "generating", "completed", "interrupted"]) {
    expect(exactReplyReceiptState({ ...turn, status }, expected, "saved-run")).toBe("accepted");
  }
});
