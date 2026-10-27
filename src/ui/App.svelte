<script lang="ts">
  import { onMount } from "svelte";
  import ChatsPage from "./ChatsPage.svelte";

  let { serverName }: { serverName: string } = $props();
  let view = $state<"jobs" | "chats">("jobs");
  let selectedRunId = $state<string | null>(null);

  function syncRoute() {
    const params = new URLSearchParams(window.location.search);
    view = params.get("view") === "chats" ? "chats" : "jobs";
    selectedRunId = view === "chats" ? params.get("run") : null;
  }

  function navigate(nextView: "jobs" | "chats", run: string | null = null) {
    const url = new URL(window.location.href);
    url.searchParams.delete("new");
    url.searchParams.delete("edit");
    url.searchParams.delete("run");
    if (nextView === "chats") {
      url.searchParams.set("view", "chats");
      if (run) url.searchParams.set("run", run);
    } else url.searchParams.delete("view");
    window.history.pushState(null, "", url);
    syncRoute();
  }

  function newChat() {
    const url = new URL(window.location.href);
    url.searchParams.delete("view");
    url.searchParams.delete("run");
    url.searchParams.delete("edit");
    url.searchParams.set("new", "once");
    window.history.pushState(null, "", url);
    syncRoute();
    // A mounted Jobs editor also observes popstate; this opens Run once explicitly.
    window.dispatchEvent(new PopStateEvent("popstate"));
  }

  onMount(() => {
    syncRoute();
    window.addEventListener("popstate", syncRoute);
    return () => window.removeEventListener("popstate", syncRoute);
  });
</script>

<svelte:head>
  <title>Prompta · {view === "chats" ? "Chats" : "Jobs"} · {serverName}</title>
  <meta name="apple-mobile-web-app-title" content={"Prompta " + serverName} />
</svelte:head>

<main class="jobs-app">
  <ChatsPage {view} {serverName} {selectedRunId}
    onSelect={(id) => navigate("chats", id)}
    onNavigate={(nextView) => navigate(nextView)}
    onNewChat={newChat} />
</main>
