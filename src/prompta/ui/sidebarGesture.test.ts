import { describe, expect, test } from "bun:test";
import { sidebarDragDirection, sidebarDragPosition, sidebarDragShouldOpen } from "./sidebarGesture";

describe("mobile sidebar drag", () => {
  test("locks horizontal drags without stealing vertical scrolling", () => {
    expect(sidebarDragDirection(6, 2)).toBe("pending");
    expect(sidebarDragDirection(20, 5)).toBe("horizontal");
    expect(sidebarDragDirection(8, 20)).toBe("vertical");
  });

  test("tracks a closed sidebar from any screen position", () => {
    expect(sidebarDragPosition(false, 320, 280, 280)).toEqual({ x: -320, progress: 0 });
    expect(sidebarDragPosition(false, 320, 280, 400)).toEqual({ x: -200, progress: 0.375 });
    expect(sidebarDragPosition(false, 320, 120, 440)).toEqual({ x: 0, progress: 1 });
  });

  test("tracks an open sidebar 1:1 with leftward movement from any start point", () => {
    expect(sidebarDragPosition(true, 320, 300, 140)).toEqual({ x: -160, progress: 0.5 });
    expect(sidebarDragPosition(true, 320, 200, 80)).toEqual({ x: -120, progress: 0.625 });
    expect(sidebarDragPosition(true, 320, 300, -40)).toEqual({ x: -320, progress: 0 });
  });

  test("settles by velocity first and progress otherwise", () => {
    expect(sidebarDragShouldOpen(0.4, 0.1)).toBe(true);
    expect(sidebarDragShouldOpen(-0.4, 0.9)).toBe(false);
    expect(sidebarDragShouldOpen(0, 0.49)).toBe(false);
    expect(sidebarDragShouldOpen(0, 0.5)).toBe(true);
  });
});
