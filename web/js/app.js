import { api } from "./api.js";
import { initControls } from "./controls.js";
import { setLastShot, showGallery } from "./gallery.js";
import { setLanguage, t } from "./i18n.js";
import { findSetting, onSettings, refreshSettings } from "./store.js";
import { initTiles } from "./tiles.js";
import { toast } from "./ui.js";
import * as viewfinder from "./viewfinder.js";

const SCREENS = { "#/": "screen-main", "#/controls": "screen-controls", "#/gallery": "screen-gallery" };
const STATUS_POLL_MS = 15000;
let connected = false;
let capturing = false;

function route() {
  const hash = SCREENS[location.hash] ? location.hash : "#/";
  for (const [key, id] of Object.entries(SCREENS)) document.getElementById(id).hidden = key !== hash;
  if (hash === "#/gallery") showGallery();
  if (hash !== "#/") viewfinder.stop();
}

async function refreshStatus() {
  let status;
  try {
    status = await api.status();
  } catch (error) {
    status = { connected: false, detail: error.message };
  }
  if (status.language) setLanguage(status.language);
  const camera = status.camera;
  document.getElementById("conn-dot").classList.toggle("on", status.connected);
  document.getElementById("cam-model").textContent = status.connected ? camera.model : status.detail || t("not_connected");
  document.getElementById("cam-battery").textContent = status.connected && camera.battery ? `🔋 ${camera.battery}` : "";
  const wasConnected = connected;
  connected = status.connected;
  if (connected && !wasConnected) await refreshSettings().catch((error) => toast(error.message));
  if (!connected) viewfinder.showMessage(status.detail || t("not_connected"));
  else if (!viewfinder.isRunning()) viewfinder.showMessage(camera.liveview_blocked_reason || t("liveview_off"));
}

async function shoot() {
  if (capturing) return;
  capturing = true;
  const button = document.getElementById("shutter");
  const result = document.getElementById("last-result");
  button.disabled = true;
  result.textContent = t("capturing");
  try {
    const shot = await api.capture();
    setLastShot(shot);
    result.textContent = t("captured", { files: shot.files.map((file) => file.name).join(", ") });
  } catch (error) {
    result.textContent = "";
    toast(error.message);
  } finally {
    capturing = false;
    button.disabled = false;
  }
}

function showMode({ primary }) {
  const mode = primary.mode ? findSetting(primary.mode) : null;
  document.getElementById("cam-mode").textContent = mode ? String(mode.value) : "";
}

async function init() {
  setLanguage("it");
  initTiles();
  initControls();
  onSettings(showMode);
  document.getElementById("shutter").addEventListener("click", shoot);
  document.getElementById("lv-toggle").addEventListener("click", () => {
    if (viewfinder.isRunning()) viewfinder.stop();
    else viewfinder.start();
  });
  window.addEventListener("hashchange", route);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) viewfinder.stop({ beacon: true });
    else refreshStatus();
  });
  route();
  await refreshStatus();
  api.photos(1).then((shots) => shots[0] && setLastShot(shots[0])).catch(() => {});
  setInterval(refreshStatus, STATUS_POLL_MS);
}

init();
