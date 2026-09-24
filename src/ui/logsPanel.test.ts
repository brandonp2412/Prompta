import { describe, expect, test } from "bun:test";

const logsPanelSource = await Bun.file(new URL("./LogsPanel.svelte", import.meta.url)).text();

describe("split service logs", () => {
  test("offers every Prompta service and requests only the selected service", () => {
    expect(logsPanelSource).toContain("prompta-ui.service");
    expect(logsPanelSource).toContain("prompta-scheduler.service");
    expect(logsPanelSource).toContain("prompta-delivery-worker.service");
    expect(logsPanelSource).toContain("prompta-conversation-worker.service");
    expect(logsPanelSource).toContain("prompta-browser.service");
    expect(logsPanelSource).toContain('id="logService" name="service" aria-label="Log service"');
    expect(logsPanelSource).toContain(
      'new URLSearchParams({ limit: "800", service: requestedService })',
    );
    expect(logsPanelSource).toContain(
      "if (controller.signal.aborted || requestedService !== selectedService) return;",
    );
  });

  test("serializes polling and reports fetch health instead of always claiming live", () => {
    expect(logsPanelSource).toContain("activeRequest?.abort();");
    expect(logsPanelSource).toContain("signal: controller.signal");
    expect(logsPanelSource).toContain('syncState = "live";');
    expect(logsPanelSource).toContain('syncState = "retrying";');
    expect(logsPanelSource).toContain('role="status"');
    expect(logsPanelSource).toContain('aria-live="polite"');
    expect(logsPanelSource).toContain("refreshTimer = setTimeout(() => void poll(), 2000);");
    expect(logsPanelSource).not.toContain("setInterval");
  });
});
