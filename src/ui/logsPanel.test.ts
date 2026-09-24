import { describe, expect, test } from "bun:test";

const logsPanelSource = await Bun.file(new URL("./LogsPanel.svelte", import.meta.url)).text();

describe("split service logs", () => {
  test("offers every Prompta service and requests only the selected service", () => {
    expect(logsPanelSource).toContain("prompta-ui.service");
    expect(logsPanelSource).toContain("prompta-scheduler.service");
    expect(logsPanelSource).toContain("prompta-delivery-worker.service");
    expect(logsPanelSource).toContain("prompta-conversation-worker.service");
    expect(logsPanelSource).toContain("prompta-browser.service");
    expect(logsPanelSource).toContain('aria-label="Log service"');
    expect(logsPanelSource).toContain(
      'new URLSearchParams({ limit: "800", service: requestedService })',
    );
    expect(logsPanelSource).toContain("if (requestedService !== selectedService) return;");
  });
});
