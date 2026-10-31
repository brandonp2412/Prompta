import { describe, expect, test } from "bun:test";
import { createDrawerSwipe } from "../src/ui/drawerSwipe";

Object.assign(globalThis, {
  window: { matchMedia: () => ({ matches: true }) },
  innerWidth: 390,
});

function touch(x: number, y = 100, identifier = 1) {
  return { clientX: x, clientY: y, identifier };
}

function event(x: number, y = 100, identifier = 1) {
  let prevented = false;
  const point = touch(x, y, identifier);
  return {
    value: {
      touches: [point],
      changedTouches: [point],
      preventDefault() { prevented = true; },
    } as unknown as TouchEvent,
    get prevented() { return prevented; },
  };
}

function setup(open = false, list = false) {
  let time = 0;
  const drawerOpen = { value: open };
  const drawerProgress = { value: null as number | null };
  const swipe = createDrawerSwipe({
    drawerOpen,
    drawerProgress,
    isList: () => list,
    drawerWidth: () => 320,
    clock: { now: () => time },
  });
  return { drawerOpen, drawerProgress, ...swipe, advance: (ms: number) => { time += ms; } };
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
