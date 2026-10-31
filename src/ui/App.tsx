import { useEffect, useState } from "react";
import ChatsPage from "./ChatsPage";
import { retryLiveConnection, subscribeLiveStatus } from "./liveUpdates";

type View = "jobs" | "chats";
type Route = { view: View; selectedRunId: string | null; newChatOpen: boolean };
function currentRoute(): Route {
  const params = new URLSearchParams(window.location.search);
  const view: View = params.get("view") === "jobs" ? "jobs" : "chats";
  const selectedRunId = view === "chats" ? params.get("run") : null;
  return {
    view,
    selectedRunId,
    newChatOpen: view === "chats" && !selectedRunId && params.get("draft") === "new",
  };
}

export default function App({ serverName }: { serverName: string }) {
  const [route, setRoute] = useState(currentRoute);
  const [updatesDelayed, setUpdatesDelayed] = useState(false);

  useEffect(() => {
    const syncRoute = () => setRoute(currentRoute());
    window.addEventListener("popstate", syncRoute);
    const unsubscribe = subscribeLiveStatus(setUpdatesDelayed);
    return () => {
      unsubscribe();
      window.removeEventListener("popstate", syncRoute);
    };
  }, []);

  useEffect(() => {
    document.title = `Prompta · ${route.view === "chats" ? "Chats" : "Jobs"} · ${serverName}`;
  }, [route.view, serverName]);

  function navigate(nextView: View, run: string | null = null) {
    const url = new URL(window.location.href);
    for (const name of ["new", "edit", "run", "draft"]) url.searchParams.delete(name);
    url.searchParams.set("view", nextView);
    if (nextView === "chats" && run) url.searchParams.set("run", run);
    window.history.pushState(null, "", url);
    setRoute(currentRoute());
  }

  function newChat() {
    const url = new URL(window.location.href);
    for (const name of ["run", "edit", "new"]) url.searchParams.delete(name);
    url.searchParams.set("view", "chats");
    url.searchParams.set("draft", "new");
    window.history.pushState(null, "", url);
    setRoute(currentRoute());
  }

  return (
    <main className="jobs-app">
      {updatesDelayed && (
        <div
          className={"live-updates-warning" + (route.view === "chats" ? " chat-view" : "")}
          role="status"
        >
          <span>Live updates delayed. Checking automatically.</span>
          <button type="button" onClick={retryLiveConnection}>
            Refresh now
          </button>
        </div>
      )}
      <ChatsPage
        view={route.view}
        selectedRunId={route.selectedRunId}
        newChatOpen={route.newChatOpen}
        onSelect={(id) => navigate("chats", id)}
        onNavigate={(nextView) => navigate(nextView)}
        onNewChat={newChat}
        onQueued={(id) => navigate("chats", id)}
      />
    </main>
  );
}
