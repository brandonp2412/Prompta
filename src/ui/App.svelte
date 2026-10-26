<script lang="ts">
  import { onMount } from "svelte";
  import ChatsPage from "./ChatsPage.svelte";
  import JobsPage from "./JobsPage.svelte";

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
  <header class="app-header">
    <div class="brand">Prompta</div>
    <nav class="app-nav" aria-label="Main navigation">
      <button class:active={view === "jobs"} onclick={() => navigate("jobs")} aria-current={view === "jobs" ? "page" : undefined}>Jobs</button>
      <button class:active={view === "chats"} onclick={() => navigate("chats")} aria-current={view === "chats" ? "page" : undefined}>Chats</button>
    </nav>
    <div class="server-name">{serverName}</div>
  </header>

  {#if view === "jobs"}<JobsPage />{:else}<ChatsPage {selectedRunId} onSelect={(id) => navigate("chats", id)} />{/if}
</main>
