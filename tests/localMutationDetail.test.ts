import { expect, test } from "bun:test";
import { localRejectionDetail } from "../src/ui/localMutation";

test("shows actionable FastAPI validation without exposing echoed input", async () => {
  const response = Response.json(
    {
      detail: [
        {
          type: "string_too_short",
          loc: ["body", "prompt"],
          msg: "String should have at least 1 character",
          input: "private prompt contents",
        },
      ],
    },
    { status: 422 },
  );
  const message = await localRejectionDetail(response, "Request rejected.");
  expect(message).toBe("prompt: String should have at least 1 character");
  expect(message).not.toContain("private prompt contents");
});

test("uses scalar application errors but bounds untrusted validation details", async () => {
  expect(
    await localRejectionDetail(Response.json({ detail: "Session expired" }, { status: 409 }), "Fallback"),
  ).toBe("Session expired");
  const oversized = Response.json(
    { detail: [{ loc: ["body", "images"], msg: "x".repeat(201) }] },
    { status: 422 },
  );
  expect(await localRejectionDetail(oversized, "Fallback")).toBe("Fallback");
  const unstructured = new Response("<h1>Bad Gateway</h1>", { status: 502 });
  expect(await localRejectionDetail(unstructured, "Offline")).toBe("Offline");
});
