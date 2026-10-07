import { t } from "./i18n.js";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body) {
  const options = { method };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError(t("network_error"), 0);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      // keep the status text
    }
    throw new ApiError(detail, response.status);
  }
  return response;
}

export const api = {
  status: async () => (await request("GET", "/api/status")).json(),
  settings: async () => (await request("GET", "/api/settings")).json(),
  set: async (name, value) =>
    (await request("PUT", `/api/settings/${encodeURIComponent(name)}`, { value })).json(),
  capture: async () => (await request("POST", "/api/capture")).json(),
  preview: async () => (await request("GET", "/api/preview")).blob(),
  stopLiveview: () => request("POST", "/api/liveview/stop"),
  photos: async (limit = 60) => (await request("GET", `/api/photos?limit=${limit}`)).json(),
};
