import { t } from "./i18n.js";
import { findSetting, onSettings, writeSetting } from "./store.js";
import { el, toast } from "./ui.js";

const ROLES = ["shutter", "aperture", "iso", "exposure_comp"];

export function initTiles() {
  document.getElementById("sheet").addEventListener("click", (event) => {
    if (event.target.id === "sheet") closeSheet();
  });
  onSettings(render);
}

function format(role, value) {
  if (role === "exposure_comp" && Number(value) > 0) return `+${value}`;
  return String(value);
}

function render({ primary }) {
  const tiles = [];
  for (const role of ROLES) {
    const setting = primary[role] ? findSetting(primary[role]) : null;
    if (!setting) continue;
    tiles.push(
      el(
        "button",
        { type: "button", className: setting.readonly ? "tile readonly" : "tile", onclick: () => pick(role, setting) },
        el("span", { className: "tile-label", text: t(`role_${role}`) }),
        el("span", { className: "tile-value", text: format(role, setting.value) + (setting.readonly ? " 🔒" : "") }),
      ),
    );
  }
  document.getElementById("tiles").replaceChildren(...tiles);
}

function pick(role, setting) {
  if (setting.readonly) {
    toast(t("readonly_hint", { label: t(`role_${role}`) }));
    return;
  }
  if (setting.type !== "choice") {
    location.hash = "#/controls";
    return;
  }
  const list = document.getElementById("sheet-list");
  document.getElementById("sheet-title").textContent = t(`role_${role}`);
  list.replaceChildren(
    ...setting.choices.map((choice) =>
      el("button", {
        type: "button",
        className: choice === setting.value ? "current" : "",
        text: format(role, choice),
        onclick: () => choose(setting.name, choice),
      }),
    ),
  );
  document.getElementById("sheet").hidden = false;
  list.querySelector(".current")?.scrollIntoView({ block: "center" });
}

async function choose(name, value) {
  closeSheet();
  try {
    await writeSetting(name, value);
  } catch (error) {
    toast(error.message);
  }
}

function closeSheet() {
  document.getElementById("sheet").hidden = true;
}
