export type SlashCommandId =
  | "new"
  | "chats"
  | "jobs"
  | "settings"
  | "search"
  | "refresh"
  | "markread"
  | "copy"
  | "open"
  | "stop"
  | "clear"
  | "help";

export type SlashCommand = {
  id: SlashCommandId;
  name: string;
  aliases: readonly string[];
  description: string;
  icon: string;
};

export const slashCommands: readonly SlashCommand[] = [
  {
    id: "new",
    name: "new",
    aliases: ["n", "create", "fresh"],
    description: "Start a new chat",
    icon: "＋",
  },
  {
    id: "chats",
    name: "chats",
    aliases: ["c", "home", "inbox"],
    description: "Go to chats",
    icon: "▤",
  },
  {
    id: "jobs",
    name: "jobs",
    aliases: ["j", "queue", "tasks"],
    description: "Open Jobs",
    icon: "◷",
  },
  {
    id: "settings",
    name: "settings",
    aliases: ["prefs", "config", "options"],
    description: "Open settings",
    icon: "⚙",
  },
  {
    id: "search",
    name: "search",
    aliases: ["s", "find"],
    description: "Search your chats",
    icon: "⌕",
  },
  {
    id: "refresh",
    name: "refresh",
    aliases: ["reload", "sync"],
    description: "Refresh chats and queue",
    icon: "↻",
  },
  {
    id: "markread",
    name: "markread",
    aliases: ["readall", "markall"],
    description: "Mark every chat as read",
    icon: "✓",
  },
  {
    id: "copy",
    name: "copy",
    aliases: ["link", "share"],
    description: "Copy the current chat link",
    icon: "↗",
  },
  {
    id: "open",
    name: "open",
    aliases: ["gpt", "chatgpt"],
    description: "Open this chat in ChatGPT",
    icon: "↗",
  },
  {
    id: "stop",
    name: "stop",
    aliases: ["cancel", "halt"],
    description: "Stop the current response",
    icon: "■",
  },
  {
    id: "clear",
    name: "clear",
    aliases: ["discard", "reset"],
    description: "Clear composer text",
    icon: "×",
  },
  {
    id: "help",
    name: "help",
    aliases: ["commands", "?"],
    description: "Show every slash command",
    icon: "?",
  },
];

export function activeSlashCommand(text: string, cursor: number): string | null {
  if (cursor !== text.length) return null;
  const match = /^\/([a-z0-9?-]*)$/i.exec(text);
  return match ? match[1] : null;
}

export function suggestedSlashCommands(query: string): SlashCommand[] {
  const needle = query.toLocaleLowerCase();
  return slashCommands
    .filter(
      ({ name, aliases }) =>
        name.includes(needle) || aliases.some((alias) => alias.includes(needle)),
    )
    .sort((a, b) => {
      const rank = (command: SlashCommand) => {
        if (command.name === needle) return 0;
        if (command.aliases.includes(needle)) return 1;
        if (command.name.startsWith(needle)) return 2;
        if (command.aliases.some((alias) => alias.startsWith(needle))) return 3;
        return 4;
      };
      return rank(a) - rank(b);
    });
}

export function exactSlashCommand(text: string): SlashCommand | undefined {
  const match = /^\/([a-z0-9?-]+)\s*$/i.exec(text);
  if (!match) return undefined;
  const name = match[1].toLocaleLowerCase();
  return slashCommands.find((command) => command.name === name || command.aliases.includes(name));
}

export function isCommandOnlyDraft(text: string): boolean {
  return /^\/[a-z0-9?-]+\s*$/i.test(text);
}
