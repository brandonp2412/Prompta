import { expect, test } from "bun:test";
import { localRejectionDetail } from "../src/ui/localMutation";

test("definite FastAPI 4xx rejections show the real reason", async () => {
  const response = Response.json(
    { detail: "This chat already has 20 unresolved follow-ups" },
    { status: 409 },
  );
  expect(await localRejectionDetail(response, "Generic failure")).toBe(
    "This chat already has 20 unresolved follow-ups",
  );
});

test("legacy error payloads remain actionable", async () => {
  const response = Response.json(
    { error: "Request ID belongs to a different message" },
    { status: 400 },
  );
  expect(await localRejectionDetail(response, "Generic failure")).toBe(
    "Request ID belongs to a different message",
  );
});

test("non-string or malformed error responses never leak raw markup", async () => {
  expect(
    await localRejectionDetail(
      Response.json({ detail: [{ msg: "invalid" }] }, { status: 422 }),
      "Invalid message",
    ),
  ).toBe("Invalid message");
  expect(
    await localRejectionDetail(
      new Response("<html>Proxy error</html>", { status: 400 }),
      "Local failure",
    ),
  ).toBe("Local failure");
  expect(
    await localRejectionDetail(
      Response.json({ detail: "x".repeat(301) }, { status: 400 }),
      "Local failure",
    ),
  ).toBe("Local failure");
});
