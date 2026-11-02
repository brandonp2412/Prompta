import { afterEach, expect, test } from "bun:test";
import { createChatsPageController } from "../src/ui/ChatsPageController";
import type { RunDetail } from "../src/ui/resultFormatting";

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

const detail = (id: string): RunDetail => ({
  send_id: id,
  job_name: "",
  title: "Chat " + id,
  preview: "Answer " + id,
  user_text: "Prompt " + id,
  assistant_text: "Answer " + id,
  source: "test",
  images: [],
  status: "completed",
  has_response: true,
  last_reply_revision: "",
  last_read_revision: "",
  last_reply_at: 10,
  created_at: 10,
  updated_at: 10,
  finished_at: 10,
  accepted_at: 10,
});

test("hover prefetch is coalesced and makes selected chat content available immediately", async () => {
  const requests: string[] = [];
  globalThis.fetch = Object.assign(
    async (input: RequestInfo | URL) => {
      const path = String(input);
      requests.push(path);
      const id = path.endsWith("/turns")
        ? (path.split("/").at(-2) ?? "")
        : (path.split("/").at(-1) ?? "");
      if (path.endsWith("/turns")) {
        return Response.json({
          turns: [
            {
              reply_id: "",
              user_text: "Prompt " + id,
              assistant_text: "Answer " + id,
              status: "completed",
              created_at: 10,
              updated_at: 10,
            },
          ],
        });
      }
      return Response.json(detail(id));
    },
    { preconnect: originalFetch.preconnect },
  );
  const props = {
    view: "chats" as const,
    selectedRunId: null,
    newChatOpen: false,
    onSelect: () => {},
    onNavigate: () => {},
    onNewChat: () => {},
    onQueued: () => {},
  };
  const model = createChatsPageController(props);
  await Promise.all([model.prefetchRun("recent"), model.prefetchRun("recent")]);
  expect(requests).toHaveLength(2);
  model.syncProps({ ...props, selectedRunId: "recent" });
  expect(model.detail.value?.send_id).toBe("recent");
  expect(model.turns.value[0]?.assistant_text).toBe("Answer recent");
  expect(model.switchingChat.value).toBe(true);
  expect(requests).toHaveLength(2);
});
