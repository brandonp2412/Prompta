import catalog from "../static/mention-catalog.json";

export type Mention = (typeof catalog)[number];
export type MentionMatch = { start: number; end: number; query: string };

export const mentionCatalog: Mention[] = catalog;

export function activeMention(text: string, cursor: number): MentionMatch | null {
  if (cursor < 0 || cursor > text.length) return null;
  const before = text.slice(0, cursor);
  const match = /(?:^|[\s([{])@([\p{L}\p{N} _-]{0,48})$/u.exec(before);
  if (!match) return null;
  const start = cursor - match[1].length - 1;
  return { start, end: cursor, query: match[1] };
}

export function suggestedMentions(query: string): Mention[] {
  const normalized = query.toLocaleLowerCase().replace(/[-_]/g, " ").trim();
  const matches = mentionCatalog.filter(({ name }) =>
    name.toLocaleLowerCase().includes(normalized),
  );
  return matches
    .sort((a, b) => {
      const aStarts = a.name.toLocaleLowerCase().startsWith(normalized) ? 0 : 1;
      const bStarts = b.name.toLocaleLowerCase().startsWith(normalized) ? 0 : 1;
      return aStarts - bStarts;
    })
    .slice(0, 7);
}

export function insertMention(
  text: string,
  match: MentionMatch,
  name: string,
): { value: string; cursor: number } {
  const replacement = `@${name} `;
  return {
    value: text.slice(0, match.start) + replacement + text.slice(match.end),
    cursor: match.start + replacement.length,
  };
}
