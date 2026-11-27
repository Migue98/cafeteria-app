// Conserva el punto de navegación al deshabilitar botones y sustituir el carrito.
const cartFocus = new WeakMap();

// La API conserva UTC; la interfaz muestra la hora local del navegador.
const orderDateFormat = new Intl.DateTimeFormat(document.documentElement.lang || "es", {
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});
function formatOrderDates(root) {
  for (const element of root.querySelectorAll("time[datetime]")) {
    const date = new Date(element.dateTime);
    if (!Number.isNaN(date.getTime())) {
      element.textContent = orderDateFormat.format(date);
      element.title = `Hora local (${orderDateFormat.resolvedOptions().timeZone})`;
    }
  }
}
formatOrderDates(document);
document.addEventListener("htmx:load", (event) => formatOrderDates(event.detail.elt));

document.addEventListener("htmx:beforeRequest", (event) => {
  const active = document.activeElement;
  if (active?.matches("button[id]") && event.detail.elt.contains(active)) {
    cartFocus.set(event.detail.xhr, {
      id: active.id,
      inCart: Boolean(active.closest("#cart-panel")),
    });
  }
});

document.addEventListener("htmx:afterRequest", (event) => {
  const previous = cartFocus.get(event.detail.xhr);
  if (!previous) return;
  cartFocus.delete(event.detail.xhr);
  requestAnimationFrame(() => {
    // Si la persona ya siguió navegando durante la espera, respeta su nuevo foco.
    if (document.activeElement !== document.body && document.activeElement.id !== previous.id) return;
    const target = document.getElementById(previous.id)
      || (previous.inCart && document.getElementById("cart-title"));
    if (target && !target.disabled) target.focus({ preventScroll: true });
  });
});
