import { createRoot } from "react-dom/client";
import App from "./App";

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
});

if ("serviceWorker" in navigator && window.isSecureContext) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("./sw.js", { scope: "./" }).catch((error: unknown) => {
      console.warn("Prompta service worker registration failed", error);
    });
  });
}

const target = document.querySelector<HTMLElement>("#app");
if (!target) throw new Error("Missing #app mount target");

const serverName = target.dataset.serverName?.trim() || "local";
createRoot(target).render(<App serverName={serverName} />);
