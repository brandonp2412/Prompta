import { describe, expect, test } from "bun:test";
import { sidebarDragDirection, sidebarDragPosition, sidebarDragShouldOpen } from "./sidebarGesture";

describe("mobile sidebar drag", () => {
  test("locks horizontal drags without stealing vertical scrolling", () => {
    expect(sidebarDragDirection(6, 2)).toBe("pending");
    expect(sidebarDragDirection(20, 5)).toBe("horizontal");
    expect(sidebarDragDirection(8, 20)).toBe("vertical");
  });

  test("tracks a closed sidebar from fully hidden to fully open", () => {
    expect(sidebarDragPosition(false, 320, 0, 0)).toEqual({ x: -320, progress: 0 });
    expect(sidebarDragPosition(false, 320, 0, 160)).toEqual({ x: -160, progress: 0.5 });
    expect(sidebarDragPosition(false, 320, 0, 400)).toEqual({ x: 0, progress: 1 });
  });

  test("tracks an open sidebar while dragging it closed", () => {
    expect(sidebarDragPosition(true, 320, 300, 140)).toEqual({ x: -160, progress: 0.5 });
    expect(sidebarDragPosition(true, 320, 300, -40)).toEqual({ x: -320, progress: 0 });
  });

  test("settles by velocity first and progress otherwise", () => {
    expect(sidebarDragShouldOpen(0.4, 0.1)).toBe(true);
    expect(sidebarDragShouldOpen(-0.4, 0.9)).toBe(false);
    expect(sidebarDragShouldOpen(0, 0.49)).toBe(false);
    expect(sidebarDragShouldOpen(0, 0.5)).toBe(true);
  });
});
