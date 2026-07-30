import { ref } from "vue";

/* Draggable divider state for a side panel.

   Pointer capture instead of document mouse listeners: capture keeps the
   move events coming even when the cursor crosses an iframe (the PDF viewer
   swallows mousemove, which made the drag freeze intermittently).

   Clamp in JS, not only in CSS: an unclamped ref keeps drifting past the
   panel's min/max while the visual stays pinned, so reversing direction did
   nothing until the cursor travelled all the way back — the "stuck" feel. */
export function useResize(initialWidth, fromLeft, min = 200, max = 700) {
  const width = ref(initialWidth);
  const dragging = ref(false);

  function start(e) {
    e.preventDefault();
    const el = e.currentTarget;
    const startX = e.clientX, startW = width.value;
    // max may be a function (e.g. window-relative) — resolve per drag
    const maxW = typeof max === "function" ? max() : max;
    dragging.value = true;
    // Selection and cursor flicker over other panels while dragging
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    el.setPointerCapture(e.pointerId);
    const move = ev => {
      const w = fromLeft ? startW + ev.clientX - startX : startW - ev.clientX + startX;
      width.value = Math.min(maxW, Math.max(min, w));
    };
    const up = ev => {
      dragging.value = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      if (el.hasPointerCapture(ev.pointerId)) el.releasePointerCapture(ev.pointerId);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }

  return { width, dragging, start };
}
