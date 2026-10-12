// Pure decisions of the assistant panel, kept free of the DOM so they can be tested with Node.

// How a proposal card looks: the server state, except that a proposal still pending
// after a newer message was accepted can no longer be applied.
export function cardState(proposal, current) {
  if (proposal.state === "pending" && !current) return "superseded";
  return proposal.state;
}

export function formatValue(value) {
  return typeof value === "number" ? String(Number(value.toFixed(3))) : String(value);
}

// One change as "Label: old → new".
export function changeLine(change) {
  return `${change.label || change.name}: ${formatValue(change.old)} → ${formatValue(change.new)}`;
}

// Send `text`, starting a session when there is none. A 404 means the server restarted
// and forgot the conversation: start a new one and send once more.
export async function sendMessage(client, sessionId, text) {
  let id = sessionId ?? (await client.startChat()).id;
  try {
    return { sessionId: id, turn: await client.sendChat(id, text) };
  } catch (error) {
    if (error.status !== 404) throw error;
    id = (await client.startChat()).id;
    return { sessionId: id, turn: await client.sendChat(id, text) };
  }
}
