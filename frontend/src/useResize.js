import { ref } from "vue";

/* Draggable divider state for a side panel. CSS min/max-width on the panel
   still clamps the visual result, same as the old direct style.width writes. */
export function useResize(initialWidth, fromLeft) {
  const width = ref(initialWidth);
  const dragging = ref(false);

  function start(e) {
    e.preventDefault();
    const startX = e.clientX, startW = width.value;
    dragging.value = true;
    const move = ev => {
      width.value = fromLeft ? startW + ev.clientX - startX : startW - ev.clientX + startX;
    };
    const up = () => {
      dragging.value = false;
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  }

  return { width, dragging, start };
}
