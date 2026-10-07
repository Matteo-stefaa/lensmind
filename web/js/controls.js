import { t } from "./i18n.js";
import { getSettings, onSettings, writeSetting } from "./store.js";
import { el, toast } from "./ui.js";

const TYPING = "input[type=text], input[type=number], input[type=datetime-local]";

export function initControls() {
  onSettings(render);
}

function render({ groups }) {
  const box = document.getElementById("groups");
  // Do not rebuild the list under the user's fingers while they type.
  if (box.contains(document.activeElement) && document.activeElement.matches(TYPING)) return;
  const open = new Set([...box.querySelectorAll("details[open]")].map((node) => node.dataset.group));
  box.replaceChildren(
    ...groups.map((group) => {
      const details = el("details", { open: open.has(group.name) }, el("summary", { text: group.label }), ...group.settings.map(row));
      details.dataset.group = group.name;
      return details;
    }),
  );
}

function row(setting) {
  return el(
    "div",
    { className: setting.readonly ? "row readonly" : "row" },
    el("span", { className: "row-label", text: setting.label }),
    setting.readonly ? el("span", { className: "row-value", text: `${display(setting)} 🔒` }) : editor(setting),
  );
}

function display(setting) {
  if (setting.type === "toggle") {
    if (setting.value === 1) return t("on");
    if (setting.value === 0) return t("off");
    return t("unknown_state");
  }
  if (setting.type === "date") return new Date(setting.value * 1000).toLocaleString();
  return String(setting.value);
}

function editor(setting) {
  switch (setting.type) {
    case "choice":
      return choiceEditor(setting);
    case "range":
      return rangeEditor(setting);
    case "toggle":
      return toggleEditor(setting);
    case "date":
      return dateEditor(setting);
    default:
      return textEditor(setting);
  }
}

function choiceEditor(setting) {
  const select = el("select", { "aria-label": setting.label, onchange: () => commit(setting, select.value, [select]) });
  if (!setting.choices.includes(setting.value)) {
    select.append(
      el("option", { value: String(setting.value), text: t("current_value", { value: setting.value }), disabled: true, selected: true }),
    );
  }
  for (const choice of setting.choices) {
    select.append(el("option", { value: choice, text: choice, selected: choice === setting.value }));
  }
  return select;
}

function rangeEditor(setting) {
  const attributes = { min: setting.min, max: setting.max, step: setting.step || "any", value: setting.value };
  const slider = el("input", { type: "range", "aria-label": setting.label, ...attributes });
  const number = el("input", { type: "number", inputMode: "decimal", "aria-label": setting.label, ...attributes });
  slider.addEventListener("input", () => {
    number.value = slider.value;
  });
  slider.addEventListener("change", () => commit(setting, Number(slider.value), [slider, number]));
  number.addEventListener("change", () => commit(setting, Number(number.value), [slider, number]));
  return el("div", { className: "range" }, slider, number);
}

function toggleEditor(setting) {
  const box = el("input", { type: "checkbox", className: "switch", checked: setting.value === 1, "aria-label": setting.label });
  box.indeterminate = setting.value !== 0 && setting.value !== 1;
  box.addEventListener("change", () => commit(setting, box.checked ? 1 : 0, [box]));
  return box;
}

function textEditor(setting) {
  const input = el("input", { type: "text", value: String(setting.value), "aria-label": setting.label });
  const save = el("button", { type: "button", text: t("save"), onclick: () => commit(setting, input.value, [input, save]) });
  return el("div", { className: "inline" }, input, save);
}

function dateEditor(setting) {
  const input = el("input", { type: "datetime-local", step: 1, value: toLocalInput(setting.value), "aria-label": setting.label });
  const now = el("button", {
    type: "button",
    text: t("now"),
    onclick: () => commit(setting, Math.floor(Date.now() / 1000), [input, now]),
  });
  input.addEventListener("change", () => {
    const millis = new Date(input.value).getTime();
    if (!Number.isNaN(millis)) commit(setting, Math.floor(millis / 1000), [input, now]);
  });
  return el("div", { className: "inline" }, input, now);
}

function toLocalInput(seconds) {
  const date = new Date(seconds * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

async function commit(setting, value, controls) {
  for (const control of controls) control.disabled = true;
  try {
    await writeSetting(setting.name, value);
  } catch (error) {
    toast(error.message);
    render(getSettings()); // put the controls back to the last known values
  } finally {
    for (const control of controls) control.disabled = false;
  }
}
