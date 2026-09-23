<script lang="ts">
  import type { Snippet } from "svelte";
  import { registerAttachmentPicker } from "./uiControllers";

  type AttachmentPickerOptions = {
    onChange: () => void;
    setStatus: (message: string) => void;
  };

  let { children }: { children: Snippet } = $props();

  let files = $state.raw<File[]>([]);
  let menuOpen = $state(false);
  let disabled = $state(false);
  let fileInput: HTMLInputElement;
  let photoInput: HTMLInputElement;
  let cameraInput: HTMLInputElement;
  let pickerButton: HTMLButtonElement;
  let options: AttachmentPickerOptions | null = null;

  function notifyChange() {
    options?.onChange();
  }

  function truncate(value: string, length = 28) {
    return value.length > length ? value.slice(0, Math.max(1, length - 1)).trimEnd() + "…" : value;
  }

  function add(nextFiles: File[]) {
    const next = [...files];

    for (const file of nextFiles) {
      if (next.length >= 5) break;
      if (!next.some((item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) next.push(file);
    }

    files = next;
    notifyChange();
    if (nextFiles.length && next.length >= 5) options?.setStatus("Prompta supports up to 5 attachments per message.");
  }

  function select(kind: "file" | "photo" | "camera") {
    menuOpen = false;
    (kind === "photo" ? photoInput : kind === "camera" ? cameraInput : fileInput).click();
  }

  function read(input: HTMLInputElement) {
    const selected = Array.from(input.files || []);
    input.value = "";
    add(selected);
  }

  function payload(file: File) {
    if (file.size > 25 * 1024 * 1024) throw new Error(file.name + " is larger than 25 MB");
    return new Promise<{ name: string; type: string; data: string }>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(reader.error || new Error("Could not read " + file.name));
      reader.onload = () => {
        const result = typeof reader.result === "string" ? reader.result : "";
        resolve({ name: file.name, type: file.type || "application/octet-stream", data: result.slice(result.indexOf(",") + 1) });
      };
      reader.readAsDataURL(file);
    });
  }

  export function configure(next: AttachmentPickerOptions) { options = next; }
  export function clear() { files = []; fileInput.value = ""; photoInput.value = ""; cameraInput.value = ""; notifyChange(); }
  export function closeMenu(restoreFocus = false) { menuOpen = false; if (restoreFocus) pickerButton.focus(); }
  export function count() { return files.length; }
  export function snapshot() { return [...files]; }
  export function setDisabled(next: boolean) { disabled = next; if (next) menuOpen = false; }
  export async function serialize() {
    if (files.reduce((total, file) => total + file.size, 0) > 25 * 1024 * 1024) throw new Error("Attachments exceed the 25 MB Prompta upload limit");
    return Promise.all(files.map(payload));
  }

  registerAttachmentPicker({ configure, clear, closeMenu, count, serialize, setDisabled, snapshot });

  function closeOnOutsideClick(event: MouseEvent) {
    if (menuOpen && !(event.target as HTMLElement).closest(".composer-tools")) menuOpen = false;
  }
</script>

<svelte:document onclick={closeOnOutsideClick} />

<div class="composer-input-shell">
  <div class="attachment-chips" id="attachmentChips" hidden={files.length === 0}>
    {#each files as file, index (file.name + file.size + file.lastModified)}
      <span class="attachment-chip" data-dom-key={"attachment:" + index + ":" + file.name}>
        <span title={file.name}>{truncate(file.name)}</span>
        <button type="button" aria-label="Remove attachment" disabled={disabled} onclick={() => { files = files.filter((_, itemIndex) => itemIndex !== index); notifyChange(); }}>×</button>
      </span>
    {/each}
  </div>
  {@render children()}
</div>
<div class="composer-tools">
  <button bind:this={pickerButton} type="button" class="icon-button attachment-button" id="attachmentButton" aria-label="Add attachment" title="Add file or photo" aria-haspopup="menu" aria-controls="attachmentMenu" aria-expanded={menuOpen} disabled={disabled} onclick={() => menuOpen = !menuOpen}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
  </button>
  {#if menuOpen}
    <div class="attachment-menu" id="attachmentMenu" role="menu" tabindex="-1" aria-label="Add attachment" onkeydown={(event) => { if (event.key === "Escape") closeMenu(true); }}>
      <button type="button" role="menuitem" onclick={() => select("file")}>Upload file</button>
      <button type="button" role="menuitem" onclick={() => select("photo")}>Upload photo</button>
      <button type="button" role="menuitem" onclick={() => select("camera")}>Take photo</button>
    </div>
  {/if}
  <input bind:this={fileInput} id="fileUploadInput" type="file" hidden onchange={() => read(fileInput)}>
  <input bind:this={photoInput} id="photoUploadInput" type="file" accept="image/*" hidden onchange={() => read(photoInput)}>
  <input bind:this={cameraInput} id="cameraUploadInput" type="file" accept="image/*" capture="environment" hidden onchange={() => read(cameraInput)}>
</div>
