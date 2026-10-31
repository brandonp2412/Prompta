export function chatUrl(id: string): string {
  const url = new URL(window.location.href);
  for (const name of ["new", "edit", "run", "draft"]) url.searchParams.delete(name);
  url.searchParams.set("view", "chats");
  url.searchParams.set("run", id);
  url.hash = "";
  return url.href;
}
