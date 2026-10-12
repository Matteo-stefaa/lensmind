// The assistant conversation on the main screen: messages, proposals, approval.
import { api } from "./api.js";
import { cardState, changeLine, sendMessage } from "./chat_logic.js";
import { t } from "./i18n.js";
import { refreshSettings } from "./store.js";
import { el, toast } from "./ui.js";

let sessionId = null;
let available = false;
let busy = false;
let latest = null; // { proposal, card, session, current } of the newest proposal

export function initAssistant() {
  document.getElementById("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text || busy || !available) return;
    input.value = "";
    send(text);
  });
  document.getElementById("chat-new").addEventListener("click", () => {
    if (busy) return;
    sessionId = null;
    latest = null;
    document.getElementById("chat").replaceChildren();
  });
  updateComposer();
}

export function setAssistantAvailable(flag) {
  available = flag;
  updateComposer();
}

function updateComposer() {
  document.getElementById("chat-input").disabled = !available;
  document.getElementById("chat-send").disabled = !available || busy;
  document.getElementById("chat-new").disabled = !available || busy;
  document.getElementById("assistant-off").hidden = available;
}

function append(node) {
  document.getElementById("chat").append(node);
  node.scrollIntoView({ block: "nearest", behavior: "smooth" });
  return node;
}

function bubble(kind, text) {
  return append(el("p", { className: `msg ${kind}`, text }));
}

async function send(text) {
  busy = true;
  updateComposer();
  bubble("user", text);
  const thinking = bubble("assistant thinking", t("thinking"));
  try {
    const result = await sendMessage(api, sessionId, text);
    sessionId = result.sessionId;
    // Only now has the server accepted the message: an unapproved proposal is superseded.
    if (latest) {
      latest.current = false;
      renderCard(latest);
    }
    thinking.remove();
    const turn = result.turn;
    if (turn.reply) bubble(turn.question ? "assistant question" : "assistant", turn.reply);
    if (turn.proposal) {
      const card = append(el("div", { className: "proposal" }));
      latest = { proposal: turn.proposal, card, session: sessionId, current: true };
      renderCard(latest);
    }
  } catch (error) {
    thinking.remove();
    bubble("error", error.message);
  } finally {
    busy = false;
    updateComposer();
  }
}

function stateText(proposal, state) {
  const failed = proposal.failed ?? { name: "", detail: "" };
  if (state === "applied") return t("proposal_applied");
  if (state === "partial") return t("proposal_partial", failed);
  if (state === "failed") return t("proposal_failed", failed);
  return t("proposal_superseded");
}

function renderCard(entry) {
  const { proposal, card } = entry;
  const state = cardState(proposal, entry.current);
  const rows = proposal.changes.map((change) =>
    el(
      "li",
      {},
      el("span", { className: "change", text: changeLine(change) }),
      el("span", { className: "reason", text: change.reason }),
    ),
  );
  const footer =
    state === "pending"
      ? el("button", { type: "button", text: t("apply"), onclick: (event) => apply(entry, event.currentTarget) })
      : el("p", { className: state === "applied" ? "proposal-state ok" : "proposal-state", text: stateText(proposal, state) });
  card.replaceChildren(el("p", { className: "proposal-summary", text: proposal.summary }), el("ul", {}, ...rows), footer);
}

async function apply(entry, button) {
  button.disabled = true;
  try {
    entry.proposal = await api.applyProposal(entry.session, entry.proposal.id);
    renderCard(entry);
    refreshSettings().catch(() => {});
  } catch (error) {
    toast(error.message);
    button.disabled = false;
  }
}
