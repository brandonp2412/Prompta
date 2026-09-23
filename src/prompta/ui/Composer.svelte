<script lang="ts">
  import { tick } from "svelte";
  import AttachmentPicker from "./AttachmentPicker.svelte";
  import { appActions } from "./appActions.svelte";
  import { appViewState } from "./appViewState.svelte";
  import { nextSlashCommandIndex } from "./clientLogic";

  const commands = [
    { command: "/add ", name: "/add", description: "Add a repeating scheduled job", id: "slashCommandAdd" },
    { command: "/list", name: "/list", description: "List and manage scheduled jobs", id: "slashCommandList" },
    { command: "/logs", name: "/logs", description: "View Prompta service logs", id: "slashCommandLogs" },
    { command: "/at ", name: "/at", description: "Run a prompt at a date and time", id: "slashCommandAt" },
  ] as const;

  let messageInput: HTMLTextAreaElement;
  let slashDismissed = $state(false);
  let lastFocusRequest = 0;
  let lastSelectEndRequest = 0;

  const visibleCommands = $derived.by(() => {
    const value = appViewState.composerValue;
    const firstToken = value.split(/\s/, 1)[0].toLowerCase();
    const show =
      !slashDismissed && value.startsWith("/") && !value.includes("\n") && !value.includes(" ");

    return show
      ? commands.filter((item) => item.command.trim().toLowerCase().startsWith(firstToken))
      : [];
  });

  const slashOpen = $derived(visibleCommands.length > 0);
  const activeCommand = $derived(
    visibleCommands.find((item) => item.command === appViewState.activeSlashCommand) ??
      visibleCommands[0] ??
      null,
  );

  function resize(value: string) {
    if (!messageInput) return;
    messageInput.style.overflowY = "hidden";
    if (!value) {
      messageInput.style.height = "34px";
      return;
    }
    messageInput.style.height = "auto";
    const contentHeight = messageInput.scrollHeight;
    messageInput.style.height = String(Math.min(180, contentHeight)) + "px";
    messageInput.style.overflowY = contentHeight > 180 ? "auto" : "hidden";
  }

  async function insertSlashCommand(command: string) {
    slashDismissed = true;
    appViewState.activeSlashCommand = "";
    appViewState.composerValue = command;
    appActions.onComposerInput(command);
    await tick();
    messageInput.focus();
    messageInput.setSelectionRange(command.length, command.length);
  }

  function moveSlashSelection(direction: number) {
    if (!visibleCommands.length) return;
    const currentIndex = visibleCommands.findIndex(
      (item) => item.command === (activeCommand?.command ?? ""),
    );
    const nextIndex = nextSlashCommandIndex(visibleCommands.length, currentIndex, direction);
    appViewState.activeSlashCommand = visibleCommands[nextIndex]?.command ?? "";
  }

  function handleInput() {
    slashDismissed = false;
    appViewState.activeSlashCommand = "";
    appActions.onComposerInput(appViewState.composerValue);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (slashOpen) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        moveSlashSelection(event.key === "ArrowUp" ? -1 : 1);
        return;
      }

      if (event.key === "Tab" || (event.key === "Enter" && !event.isComposing)) {
        if (activeCommand) {
          event.preventDefault();
          void insertSlashCommand(activeCommand.command);
          return;
        }
      }

      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        slashDismissed = true;
        appViewState.activeSlashCommand = "";
        return;
      }
    }

    const mobileInput =
      matchMedia("(max-width: 780px)").matches || matchMedia("(pointer: coarse)").matches;

    if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !mobileInput) {
      event.preventDefault();
      appActions.onSubmit();
    }
  }

  $effect(() => {
    resize(appViewState.composerValue);
  });

  $effect(() => {
    const request = appViewState.composerFocusRequest;
    if (!messageInput || request === lastFocusRequest) return;
    lastFocusRequest = request;
    requestAnimationFrame(() => messageInput.focus());
  });

  $effect(() => {
    const request = appViewState.composerSelectEndRequest;
    if (!messageInput || request === lastSelectEndRequest) return;
    lastSelectEndRequest = request;
    requestAnimationFrame(() => {
      messageInput.focus();
      const end = appViewState.composerValue.length;
      messageInput.setSelectionRange(end, end);
    });
  });
</script>

<footer class="composer-footer" id="composerFooter">
  <form
    class="composer-bar"
    id="messageForm"
    onsubmit={(event) => {
      event.preventDefault();
      appActions.onSubmit();
    }}
  >
    <AttachmentPicker>
      <textarea
        bind:this={messageInput}
        bind:value={appViewState.composerValue}
        id="messageInput"
        rows="1"
        placeholder={appViewState.composerPlaceholder}
        aria-label="Message Prompta"
        role="combobox"
        aria-controls="slashMenu"
        aria-autocomplete="list"
        aria-haspopup="listbox"
        aria-expanded={slashOpen}
        aria-activedescendant={slashOpen && activeCommand ? activeCommand.id : undefined}
        disabled={appViewState.composerDisabled}
        oninput={handleInput}
        onkeydown={handleKeydown}
      ></textarea>
      {#if slashOpen}
        <div
          class="slash-menu"
          id="slashMenu"
          role="listbox"
          tabindex="-1"
          aria-label="Prompta commands"
        >
          {#each visibleCommands as item (item.command)}
            <button
              type="button"
              id={item.id}
              role="option"
              aria-selected={activeCommand?.command === item.command}
              onpointermove={() => (appViewState.activeSlashCommand = item.command)}
              onclick={() => void insertSlashCommand(item.command)}
            >
              <strong>{item.name}</strong><span>{item.description}</span>
            </button>
          {/each}
        </div>
      {/if}
    </AttachmentPicker>
    <div class="composer-submit">
      <button
        type="button"
        class="icon-button composer-new-chat-button"
        id="newChatButton"
        aria-label="Start a new chat"
        title="New chat"
        onclick={appActions.onNewChat}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M13 4H7a4 4 0 0 0-4 4v8a4 4 0 0 0 4 4h8l4 2v-7"></path>
          <path d="M18 3v6M15 6h6"></path>
        </svg>
      </button>
      <button
        type="submit"
        class="send-button"
        id="sendButton"
        data-action={appViewState.composerAction}
        aria-label={appViewState.composerAction === "stop" ? "Stop response" : "Send message"}
        title={appViewState.composerAction === "stop" ? "Stop response" : "Send message"}
        disabled={appViewState.composerActionDisabled}
      >
        {#if appViewState.composerAction === "stop"}
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect
              x="7.5"
              y="7.5"
              width="9"
              height="9"
              rx="1.5"
              fill="currentColor"
              stroke="none"
            ></rect>
          </svg>
        {:else}
          <svg viewBox="0 0 24 24" aria-hidden="true"
            ><path d="M12 19V5M6 11l6-6 6 6"></path></svg
          >
        {/if}
      </button>
    </div>
  </form>
  <div class="composer-status" id="composerStatus">{appViewState.composerStatus}</div>
</footer>
