import { describe, expect, test } from "bun:test";

const appSource = await Bun.file(new URL("./App.svelte", import.meta.url)).text();
const appLogicSource = await Bun.file(new URL("./app.ts", import.meta.url)).text();
const messagesSource = await Bun.file(
  new URL("./ConversationMessages.svelte", import.meta.url),
).text();

describe("queue and search controls", () => {
  test("replaces the slash shortcut with a clear button once search has text", () => {
    expect(appSource).toContain("{#if appViewState.searchValue}");
    expect(appSource).toContain('class="search-clear"');
    expect(appSource).toContain('type="text"');
    expect(appSource).toContain('role="searchbox"');
    expect(appSource).not.toContain('type="search"');
    expect(appSource).toContain('aria-label="Clear search"');
    expect(appSource).toContain('appViewState.searchValue = "";');
    expect(appSource).toContain('appActions.onSearch("");');
    expect(appSource).toContain("<kbd>/</kbd>");
  });

  test("retains queue ETA metadata from the initial enqueue response", () => {
    expect(appLogicSource).toContain("pending.queueEtaAt = Number(result.queue_eta_at || 0);");
    expect(appLogicSource).toContain(
      "coalescedReply.queueEtaAt = Number(result.queue_eta_at || 0);",
    );
  });

  test("exposes send-next controls for bumpable pending messages", () => {
    expect(messagesSource).toContain("message.pending_bump_key");
    expect(messagesSource).toContain('aria-label="Send queued message next"');
    expect(messagesSource).toContain("conversationState.onBump");
    expect(messagesSource).toContain(">Send next</button>");
  });
});
