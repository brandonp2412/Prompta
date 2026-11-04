import { describe, expect, test } from "bun:test";
import { createDrawerSwipe } from "../src/ui/drawerSwipe";

Object.assign(globalThis, {
  window: { matchMedia: () => ({ matches: true }) },
  innerWidth: 390,
});

function touch(x: number, y = 100, identifier = 1) {
  return { clientX: x, clientY: y, identifier };
}

function event(
  x: number,
  y = 100,
  identifier = 1,
  target: { closest: (selector: string) => boolean } | null = null,
) {
  let prevented = false;
  const point = touch(x, y, identifier);
  return {
    value: {
      touches: [point],
      changedTouches: [point],
      target,
      preventDefault() {
        prevented = true;
      },
    } as unknown as TouchEvent,
    get prevented() {
      return prevented;
    },
  };
}

function setup(
  open = false,
  list = false,
  position?: number,
  onProgress?: (progress: number, width: number) => void,
) {
  let time = 0;
  const drawerOpen = { value: open };
  const drawerProgress = { value: null as number | null };
  const swipe = createDrawerSwipe({
    drawerOpen,
    drawerProgress,
    isList: () => list,
    drawerWidth: () => 320,
    drawerPosition: () => position ?? (drawerOpen.value ? 1 : 0),
    onProgress,
    clock: { now: () => time },
  });
  return {
    drawerOpen,
    drawerProgress,
    ...swipe,
    advance: (ms: number) => {
      time += ms;
    },
  };
}

describe("drawer swipe", () => {
  test("opens with a deliberate horizontal edge drag", () => {
    const ui = setup();
    ui.startSwipe(event(20).value);
    ui.advance(30);
    const move = event(150);
    ui.moveSwipe(move.value);
    expect(move.prevented).toBe(true);
    expect(ui.drawerProgress.value).toBeCloseTo(130 / 320);
    ui.advance(200);
    ui.finishSwipe(event(150).value);
    expect(ui.drawerOpen.value).toBe(true);
    expect(ui.drawerProgress.value).toBeNull();
  });

  test("touch painting bypasses per-move signal updates", () => {
    const painted: { progress: number; width: number }[] = [];
    const ui = setup(false, false, undefined, (progress, width) => {
      painted.push({ progress, width });
    });
    ui.startSwipe(event(20).value);
    ui.moveSwipe(event(80).value);
    ui.moveSwipe(event(160).value);
    expect(painted).toEqual([
      { progress: 60 / 320, width: 320 },
      { progress: 140 / 320, width: 320 },
    ]);
    expect(ui.drawerProgress.value).toBeNull();
    ui.finishSwipe(event(160).value);
    expect(ui.drawerOpen.value).toBe(true);
  });

  test("blocks scrolling from the first horizontal movement through vertical drift", () => {
    const ui = setup();
    ui.startSwipe(event(20).value);
    const initial = event(23, 101);
    ui.moveSwipe(initial.value);
    expect(initial.prevented).toBe(true);
    ui.moveSwipe(event(50, 105).value);
    const diagonal = event(160, 200);
    ui.moveSwipe(diagonal.value);
    expect(diagonal.prevented).toBe(true);
    expect(ui.drawerProgress.value).toBeCloseTo(140 / 320);
  });

  test("does not hijack vertical scrolling or non-edge touches", () => {
    const ui = setup();
    ui.startSwipe(event(170).value);
    ui.moveSwipe(event(300).value);
    expect(ui.drawerProgress.value).toBeNull();
    ui.startSwipe(event(20).value);
    const vertical = event(28, 145);
    ui.moveSwipe(vertical.value);
    expect(vertical.prevented).toBe(false);
    ui.moveSwipe(event(160).value);
    expect(ui.drawerProgress.value).toBeNull();
    ui.finishSwipe(event(160).value);
    expect(ui.drawerOpen.value).toBe(false);
  });

  test("leaves chat list gestures alone", () => {
    const ui = setup(false, true);
    ui.startSwipe(event(20).value);
    ui.moveSwipe(event(180).value);
    expect(ui.drawerProgress.value).toBeNull();
  });

  test("closes with a leftward drag", () => {
    const ui = setup(true);
    ui.startSwipe(event(240).value);
    ui.advance(30);
    ui.moveSwipe(event(60).value);
    ui.advance(200);
    ui.finishSwipe(event(60).value);
    expect(ui.drawerOpen.value).toBe(false);
  });

  test("quick short fling opens below the distance threshold", () => {
    const ui = setup();
    ui.startSwipe(event(20).value);
    ui.advance(20);
    ui.moveSwipe(event(55).value);
    expect(ui.drawerProgress.value).toBeCloseTo(35 / 320);
    ui.advance(10);
    ui.finishSwipe(event(55).value);
    expect(ui.drawerOpen.value).toBe(true);
  });

  test("continues from the visible position when reversing an unfinished animation", () => {
    const ui = setup(false, false, 0.4);
    ui.startSwipe(event(20).value);
    ui.advance(20);
    ui.moveSwipe(event(52).value);
    expect(ui.drawerProgress.value).toBeCloseTo(0.5);
    ui.finishSwipe(event(52).value);
    expect(ui.drawerOpen.value).toBe(true);
  });

  test("does not close the drawer when a modal or editable surface is touched", () => {
    for (const protectedSelector of [
      ".settings-backdrop",
      ".sidebar-profile-menu",
      "input",
      "textarea",
      "select",
      "[contenteditable]",
      "pre",
    ]) {
      const ui = setup(true);
      const target = { closest: (selector: string) => selector.includes(protectedSelector) };
      ui.startSwipe(event(240, 100, 1, target).value);
      ui.moveSwipe(event(40).value);
      ui.finishSwipe(event(40).value);
      expect(ui.drawerProgress.value).toBeNull();
      expect(ui.drawerOpen.value).toBe(true);
    }
  });

  test("cancels a partial drag", () => {
    const ui = setup();
    ui.startSwipe(event(20).value);
    ui.advance(20);
    ui.moveSwipe(event(180).value);
    ui.cancelSwipe();
    expect(ui.drawerProgress.value).toBeNull();
    expect(ui.drawerOpen.value).toBe(false);
  });
});
