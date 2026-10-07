import { api } from "./api.js";
import { t } from "./i18n.js";

let running = false;
let generation = 0;
let frameUrl = null;

export function isRunning() {
  return running;
}

export function showMessage(text) {
  const overlay = document.getElementById("vf-overlay");
  overlay.textContent = text;
  overlay.hidden = !text;
}

function updateButton() {
  document.getElementById("lv-toggle").classList.toggle("active", running);
}

export function start() {
  if (running) return;
  running = true;
  const run = ++generation;
  showMessage("");
  updateButton();
  loop(run);
}

export function stop({ beacon = false } = {}) {
  if (!running) return;
  running = false;
  generation++;
  updateButton();
  showMessage(t("liveview_off"));
  // While the page is being hidden a normal fetch may be dropped; a beacon is not.
  if (beacon && navigator.sendBeacon) navigator.sendBeacon("/api/liveview/stop");
  else api.stopLiveview().catch(() => {});
}

// One frame at a time: the next request leaves only after the previous frame is shown.
async function loop(run) {
  const img = document.getElementById("vf-img");
  while (running && run === generation) {
    try {
      const blob = await api.preview();
      if (run !== generation) return;
      const url = URL.createObjectURL(blob);
      await new Promise((resolve) => {
        img.onload = resolve;
        img.onerror = resolve;
        img.src = url;
      });
      if (frameUrl) URL.revokeObjectURL(frameUrl);
      frameUrl = url;
    } catch (error) {
      if (run !== generation) return;
      running = false;
      updateButton();
      showMessage(error.message);
      return;
    }
  }
}
