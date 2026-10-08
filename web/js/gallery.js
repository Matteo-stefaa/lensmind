import { api } from "./api.js";
import { t } from "./i18n.js";
import { el, toast } from "./ui.js";

export async function showGallery() {
  const grid = document.getElementById("grid");
  let shots;
  try {
    shots = await api.photos(60);
  } catch (error) {
    toast(error.message);
    return;
  }
  if (shots.length === 0) {
    grid.replaceChildren(el("p", { className: "empty", text: t("no_photos") }));
    return;
  }
  grid.replaceChildren(
    ...shots.map((shot) =>
      el(
        "button",
        { type: "button", className: "cell", onclick: () => openShot(shot) },
        shot.thumb_url
          ? el("img", { src: shot.thumb_url, alt: shot.id, loading: "lazy" })
          : el("span", { text: shot.files.map((file) => file.name.split(".").pop()).join(" + ") }),
      ),
    ),
  );
}

function openShot(shot) {
  const view = document.getElementById("photo-view");
  const image = shot.files.find((file) => /\.jpe?g$/i.test(file.name));
  view.replaceChildren(
    el("button", {
      type: "button",
      className: "close",
      text: "✕",
      "aria-label": t("close"),
      onclick: () => {
        view.hidden = true;
      },
    }),
    image ? el("img", { src: image.url, alt: shot.id }) : null,
    el(
      "div",
      { className: "downloads" },
      ...shot.files.map((file) => el("a", { href: file.url, download: file.name, text: t("download", { name: file.name }) })),
    ),
  );
  view.hidden = false;
}

export function setLastShot(shot) {
  if (shot.thumb_url) document.getElementById("last-thumb-img").src = shot.thumb_url;
}
