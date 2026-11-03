import { expect, test } from "bun:test";
import {
  activeSlashCommand,
  exactSlashCommand,
  isCommandOnlyDraft,
  slashCommands,
  suggestedSlashCommands,
} from "../src/ui/slashCommands";

test("all command names and aliases resolve uniquely", () => {
  const names = new Set<string>();
  for (const command of slashCommands) {
    for (const name of [command.name, ...command.aliases]) {
      expect(names.has(name)).toBe(false);
      names.add(name);
      expect(exactSlashCommand(`/${name}`)?.id).toBe(command.id);
      expect(exactSlashCommand(`/${name.toUpperCase()}  `)?.id).toBe(command.id);
    }
  }
  expect(slashCommands.length).toBeGreaterThanOrEqual(10);
});

test("command suggestions include aliases and prioritize exact names", () => {
  expect(suggestedSlashCommands("q")[0].id).toBe("jobs");
  expect(suggestedSlashCommands("settings")[0].id).toBe("settings");
  expect(suggestedSlashCommands("")).toHaveLength(slashCommands.length);
});

test("slash matching applies only to a standalone command at the cursor", () => {
  expect(activeSlashCommand("/jo", 3)).toBe("jo");
  expect(activeSlashCommand("/", 1)).toBe("");
  expect(activeSlashCommand("hello /jo", 9)).toBeNull();
  expect(activeSlashCommand("/jobs more", 5)).toBeNull();
  expect(activeSlashCommand("/jobs", 2)).toBeNull();
  expect(isCommandOnlyDraft("/jobs  ")).toBe(true);
  expect(isCommandOnlyDraft("/jobs with text")).toBe(false);
  expect(exactSlashCommand("/unknown")).toBeUndefined();
});
