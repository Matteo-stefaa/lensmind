import { api } from "./api.js";

let current = { groups: [], primary: {} };
const listeners = new Set();

export function getSettings() {
  return current;
}

export function onSettings(listener) {
  listeners.add(listener);
  listener(current);
}

export function findSetting(name) {
  for (const group of current.groups) for (const setting of group.settings) if (setting.name === name) return setting;
  return null;
}

function publish() {
  for (const listener of listeners) listener(current);
}

export async function refreshSettings() {
  current = await api.settings();
  publish();
}

export async function writeSetting(name, value) {
  const updated = await api.set(name, value);
  current = {
    ...current,
    groups: current.groups.map((group) => ({
      ...group,
      settings: group.settings.map((setting) => (setting.name === name ? updated : setting)),
    })),
  };
  publish();
  // Other settings can follow: in A mode the camera picks the shutter speed.
  refreshSettings().catch(() => {});
  return updated;
}
