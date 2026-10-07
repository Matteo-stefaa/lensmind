// Every user-facing string of the web app. The language comes from /api/status.
const STRINGS = {
  it: {
    back: "Indietro",
    controls_title: "Controlli manuali",
    gallery_title: "Galleria",
    shutter: "Scatta",
    controls: "Controlli manuali",
    liveview: "Live view",
    last_shot: "Ultimo scatto",
    not_connected: "Fotocamera non collegata",
    liveview_off: "Live view spento: tocca 👁 per accenderlo",
    capturing: "Scatto in corso…",
    captured: "Salvato: {files}",
    current_value: "(attuale) {value}",
    unknown_state: "sconosciuto",
    on: "On",
    off: "Off",
    save: "Salva",
    now: "Adesso",
    readonly_hint: "{label} non si può cambiare in questa modalità",
    no_photos: "Nessuno scatto",
    download: "Scarica {name}",
    close: "Chiudi",
    network_error: "Server non raggiungibile",
    role_shutter: "Tempo",
    role_aperture: "Diaframma",
    role_iso: "ISO",
    role_exposure_comp: "Comp. esp.",
  },
  en: {
    back: "Back",
    controls_title: "Manual controls",
    gallery_title: "Gallery",
    shutter: "Shoot",
    controls: "Manual controls",
    liveview: "Live view",
    last_shot: "Last shot",
    not_connected: "Camera not connected",
    liveview_off: "Live view off: tap 👁 to turn it on",
    capturing: "Shooting…",
    captured: "Saved: {files}",
    current_value: "(current) {value}",
    unknown_state: "unknown",
    on: "On",
    off: "Off",
    save: "Save",
    now: "Now",
    readonly_hint: "{label} cannot be changed in this mode",
    no_photos: "No shots yet",
    download: "Download {name}",
    close: "Close",
    network_error: "Server unreachable",
    role_shutter: "Shutter",
    role_aperture: "Aperture",
    role_iso: "ISO",
    role_exposure_comp: "Exp. comp.",
  },
};

let language = "it";

export function setLanguage(code) {
  if (STRINGS[code]) language = code;
  document.documentElement.lang = language;
  for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-label]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nLabel));
  }
}

export function t(key, params = {}) {
  let text = STRINGS[language][key] ?? STRINGS.en[key] ?? key;
  for (const [name, value] of Object.entries(params)) text = text.replaceAll(`{${name}}`, String(value));
  return text;
}
