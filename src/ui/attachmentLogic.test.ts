import { describe, expect, test } from "bun:test";

import { attachmentMenuTargetIndex, MAX_ATTACHMENTS, mergeAttachments } from "./attachmentLogic";

type FakeFile = {
  name: string;
  size: number;
  lastModified: number;
};

function fakeFile(name: string, size = 1, lastModified = 1): FakeFile {
  return { name, size, lastModified };
}

describe("attachment menu keyboard navigation", () => {
  test("moves through menu items and wraps at either end", () => {
    expect(attachmentMenuTargetIndex("ArrowDown", 0, 3)).toBe(1);
    expect(attachmentMenuTargetIndex("ArrowDown", 2, 3)).toBe(0);
    expect(attachmentMenuTargetIndex("ArrowUp", 2, 3)).toBe(1);
    expect(attachmentMenuTargetIndex("ArrowUp", 0, 3)).toBe(2);
  });

  test("supports Home and End and ignores unrelated keys", () => {
    expect(attachmentMenuTargetIndex("Home", 1, 3)).toBe(0);
    expect(attachmentMenuTargetIndex("End", 1, 3)).toBe(2);
    expect(attachmentMenuTargetIndex("Enter", 1, 3)).toBeNull();
    expect(attachmentMenuTargetIndex("ArrowDown", 0, 0)).toBeNull();
  });

  test("starts keyboard navigation at the expected edge when no item is focused", () => {
    expect(attachmentMenuTargetIndex("ArrowDown", -1, 3)).toBe(0);
    expect(attachmentMenuTargetIndex("ArrowUp", -1, 3)).toBe(2);
  });
});

describe("attachment batching", () => {
  test("accepts a full batch up to the advertised attachment limit", () => {
    const incoming = Array.from({ length: MAX_ATTACHMENTS }, (_, index) =>
      fakeFile(`file-${index}.txt`, index + 1, index + 1),
    );

    expect(mergeAttachments([], incoming)).toEqual({
      files: incoming,
      omitted: 0,
    });
  });

  test("reports only unique files omitted by the attachment limit", () => {
    const existing = [
      fakeFile("one.txt", 1, 1),
      fakeFile("two.txt", 2, 2),
      fakeFile("three.txt", 3, 3),
      fakeFile("four.txt", 4, 4),
    ];
    const duplicate = fakeFile("four.txt", 4, 4);
    const accepted = fakeFile("five.txt", 5, 5);
    const omitted = fakeFile("six.txt", 6, 6);

    expect(mergeAttachments(existing, [duplicate, accepted, omitted])).toEqual({
      files: [...existing, accepted],
      omitted: 1,
    });
  });

  test("does not warn when selecting exactly the final available slot", () => {
    const existing = Array.from({ length: MAX_ATTACHMENTS - 1 }, (_, index) =>
      fakeFile(`file-${index}.txt`, index + 1, index + 1),
    );
    const finalFile = fakeFile("final.txt", 99, 99);

    expect(mergeAttachments(existing, [finalFile])).toEqual({
      files: [...existing, finalFile],
      omitted: 0,
    });
  });

  test("keeps file and photo inputs batch-selectable but not the camera input", async () => {
    const source = await Bun.file(new URL("./AttachmentPicker.svelte", import.meta.url)).text();

    expect(source.match(/\bmultiple\b/g)?.length).toBe(2);
    expect(
      source.match(/id="fileUploadInput"[\s\S]*?multiple[\s\S]*?onchange=\{read\}/),
    ).not.toBeNull();
    expect(
      source.match(/id="photoUploadInput"[\s\S]*?multiple[\s\S]*?onchange=\{read\}/),
    ).not.toBeNull();

    const cameraInput = source.match(/id="cameraUploadInput"[\s\S]*?\/>/)?.[0];
    expect(cameraInput).toBeDefined();
    expect(cameraInput ?? "").not.toContain("multiple");
  });
});
