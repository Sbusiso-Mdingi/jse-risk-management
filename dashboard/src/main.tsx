import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./theme.css";
import { App } from "./App";

const embedded = window.self !== window.top || new URLSearchParams(location.search).has("embed");
if (embedded) document.body.classList.add("embedded");
const root = document.getElementById("root")!;

// Let the host page size the iframe to the content.
if (embedded) {
  let last = 0;
  const post = (force = false) => {
    const height = Math.ceil(root.getBoundingClientRect().height);
    if (height === last && !force) return;
    last = height;
    window.parent.postMessage({ type: "preview:height", height }, "*");
  };
  if ("ResizeObserver" in window) new ResizeObserver(() => post()).observe(root);
  window.addEventListener("load", () => post());
  // The host may attach its listener after the first report, so it can ask again.
  window.addEventListener("message", (e) => e.data?.type === "preview:measure" && post(true));
  setInterval(() => post(), 1000);
}

createRoot(root).render(
  <StrictMode>
    <App embedded={embedded} />
  </StrictMode>,
);
