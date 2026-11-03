import catalog from "../static/mention-catalog.json";

export type Mention = (typeof catalog)[number];
export type MentionMatch = { start: number; end: number; query: string };
export type SelectedMention = { start: number; end: number; mention: Mention };

export const mentionCatalog: Mention[] = catalog;
const mentionsLongestFirst = [...mentionCatalog].sort((a, b) => b.name.length - a.name.length);

// The composer sends its text as-is, so indicators must reflect mentions that
// are still present in the draft (including drafts restored after navigation).
export function selectedDraftMentions(text: string): SelectedMention[] {
  const selected: SelectedMention[] = [];
  for (let start = 0; start < text.length; start += 1) {
    if (text[start] !== "@" || (start > 0 && !/[\s([{]/u.test(text[start - 1]))) continue;
    const mention = mentionsLongestFirst.find(({ name }) => {
      const end = start + name.length + 1;
      return (
        text.slice(start + 1, end).toLocaleLowerCase() === name.toLocaleLowerCase() &&
        (end === text.length || !/[\p{L}\p{N}_-]/u.test(text[end]))
      );
    });
    if (!mention) continue;
    const end = start + mention.name.length + 1;
    selected.push({ start, end, mention });
    start = end - 1;
  }
  return selected;
}

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
