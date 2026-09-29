<script lang="ts">
  import JobsPage from "./JobsPage.svelte";

  let { serverName }: { serverName: string } = $props();
</script>

<svelte:head>
  <title>Prompta · Jobs · {serverName}</title>
  <meta name="apple-mobile-web-app-title" content={"Prompta " + serverName} />
</svelte:head>

<main class="jobs-app">
  <header class="app-header">
    <div>
      <div class="brand">Prompta</div>
      <p>Scheduled job manager · {serverName}</p>
    </div>
    <span class="jobs-only-badge">Jobs only</span>
  </header>

  <JobsPage />
</main>
