export type AttachmentPickerController = {
  configure(options: { onChange: () => void; setStatus: (message: string) => void }): void;
  clear(): void;
  closeMenu(restoreFocus?: boolean): void;
  count(): number;
  serialize(): Promise<Array<{ name: string; type: string; data: string }>>;
  setDisabled(disabled: boolean): void;
  snapshot(): File[];
};

export type JobsDialogController = { open(clearComposer?: boolean): Promise<void>; close(): void };
export type ChangelogDialogController = { open(): Promise<void>; close(): void };
export type LogsPanelController = {
  load(): Promise<void>;
  setServerTitle(display: string): void;
};
let attachmentPicker: AttachmentPickerController | null = null;
let jobsDialog: JobsDialogController | null = null;
let changelogDialog: ChangelogDialogController | null = null;
let logsPanel: LogsPanelController | null = null;

export function registerAttachmentPicker(controller: AttachmentPickerController) {
  attachmentPicker = controller;
}

export function getAttachmentPicker() {
  if (!attachmentPicker) throw new Error("Attachment picker was not mounted");

  return attachmentPicker;
}

export function registerJobsDialog(controller: JobsDialogController) {
  jobsDialog = controller;
}

export function getJobsDialog() {
  if (!jobsDialog) throw new Error("Jobs dialog was not mounted");

  return jobsDialog;
}

export function registerChangelogDialog(controller: ChangelogDialogController) {
  changelogDialog = controller;
}

export function getChangelogDialog() {
  if (!changelogDialog) throw new Error("Changelog dialog was not mounted");

  return changelogDialog;
}

export function registerLogsPanel(controller: LogsPanelController) {
  logsPanel = controller;
}

export function getLogsPanel() {
  if (!logsPanel) throw new Error("Logs panel was not mounted");

  return logsPanel;
}
