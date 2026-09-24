export type StackPage = "prompta" | "changelog";

const STACK_PAGE_STATE_KEY = "__promptaStackPage";

type StackHistory = Pick<History, "back" | "pushState" | "state">;

function historyStateRecord(state: unknown): Record<string, unknown> {
  return state !== null && typeof state === "object" && !Array.isArray(state)
    ? (state as Record<string, unknown>)
    : {};
}

export function stackPageFromState(state: unknown): StackPage | null {
  const page = historyStateRecord(state)[STACK_PAGE_STATE_KEY];

  return page === "prompta" || page === "changelog" ? page : null;
}

export function pushStackPage(
  page: StackPage,
  historyApi: StackHistory = history,
  url = location.href,
) {
  historyApi.pushState(
    { ...historyStateRecord(historyApi.state), [STACK_PAGE_STATE_KEY]: page },
    "",
    url,
  );
}

export function popStackPage(page: StackPage, historyApi: StackHistory = history) {
  if (stackPageFromState(historyApi.state) !== page) return false;

  historyApi.back();

  return true;
}
