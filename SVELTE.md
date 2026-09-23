# Svelte migration status

Prompta now uses Svelte 5 for all application UI surfaces. The migration is
complete: `src/prompta/ui/app.ts` is limited to data loading, reconciliation,
persistence, and command orchestration, while Svelte components and state modules
own application view state, markup, interaction handlers, and reactive updates.

## Already migrated

- `App.svelte` owns the application shell and sidebar layout.
- `SidebarList.svelte` renders the sidebar from shared Svelte state.
- `ConversationMessages.svelte` renders keyed conversation messages from a
  Svelte store, preserving live message node identity.
- `AttachmentPicker.svelte`, `JobsDialog.svelte`, `ChangelogDialog.svelte`,
  and `LogsPanel.svelte` own their markup and local interaction state.
- Sidebar state, conversation state, and the migrated shell actions are exposed
  through Svelte 5 state modules.
- The old standalone imperative sidebar, dialog, logs, attachment, DOM-patch,
  and conversation-renderer implementations have been removed.

## Completed conversions

### 1. Move application view state into a Svelte store

Create a typed `appViewState.svelte.ts` store for the remaining shell state:

- heading title and metadata;
- sync icon status and accessible label;
- server label, cache summary, and changelog head;
- empty/conversation/log visibility;
- composer value, placeholder, disabled state, status text, and primary action;
- pin/share/update-notice state; and
- search value and slash-menu selection.

`app.ts` should update this state with store actions. `App.svelte` should read
it with Svelte bindings and class/attribute directives. No application view
state should be represented by an element lookup or a DOM property assignment.

### 2. Remove the `requiredElement` registry

After the view state exists, delete `requiredElement()` and the `els` object
from `app.ts`. Components should own their element references with
`bind:this` only when an imperative browser API genuinely requires one, such as
focus, selection, scrolling, or a native dialog method.

### 3. Move all event ownership into components

The remaining document-level and element-level listeners should become Svelte
handlers:

- search input and global `/`/Escape handling;
- composer input, submit, Enter, Tab, Escape, and arrow-key behavior;
- slash-menu pointer and selection events;
- pin, share, new-chat, and update-notice actions;
- hash and page lifecycle events where a Svelte window/document handler is
  appropriate; and
- resize/visual-viewport handling through a small lifecycle utility.

The handlers may call typed actions exported by a controller module, but
`app.ts` must not call `addEventListener()` for application UI interactions.

### 4. Delete the manual DOM patching layer

Remove `patchDomNode`, `patchDomChildren`, `patchHtmlChildren`, and the SVG
string constants. The send/stop button should be a Svelte conditional with
stable button identity. Svelte keyed blocks should own list reconciliation;
the existing stable message keys must be retained.

### 5. Make the composer declarative

Extract the composer into a component with typed callbacks for send, stop,
slash commands, attachments, and new-chat. Use `bind:value`, derived state for
the send/stop action, and a reactive textarea sizing action. Draft persistence
can remain in a service module, but it should consume the component's value
through an explicit callback or store instead of reading a textarea element.

### 6. Make conversation metadata declarative

Move heading, sync status, empty state, viewport busy state, and composer
status into `App.svelte` props/state. Chat switching may still use
`requestAnimationFrame` for the transition and native scroll APIs for viewport
restoration, but it should not toggle classes, `hidden`, or ARIA attributes by
querying shell nodes.

### 7. Move time refresh into reactive state

The 30-second time refresh should update timestamp data in the sidebar and
conversation stores. Remove the `querySelectorAll()` loops that mutate time
labels in place. Components should derive relative labels from a shared clock
tick, while preserving message keys and scroll position.

### 8. Keep browser APIs at narrow component boundaries

The final imperative code should be limited to APIs that Svelte cannot model:

- `focus()` and selection range management;
- `scrollTop`/scroll restoration;
- native `HTMLDialogElement` methods;
- clipboard and file APIs; and
- EventSource/service-worker/browser notification integration.

These operations should live in `onMount`, component actions, or small
dedicated services, with cleanup in `onDestroy`/returned lifecycle callbacks.

## Completion criteria

The migration is complete. The validated completion criteria are:

1. `app.ts` contains data loading, reconciliation, persistence, and command
   orchestration only.
2. It has no `querySelector`, `createElement`, `innerHTML`, `textContent`,
   `classList`, `hidden`, `setAttribute`, or application `addEventListener`
   calls.
3. All application markup is rendered by `.svelte` components.
4. Conversation and sidebar blocks retain stable keys during live updates.
5. `bun run check` passes, including the DOM-rebuild guard and UI tests.
6. The built bundle is deployed to nox and the UI service responds successfully.

