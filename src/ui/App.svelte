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
    <div class="brand">Prompta</div>
    <div class="server-name">{serverName}</div>
  </header>

  <JobsPage />
</main>
