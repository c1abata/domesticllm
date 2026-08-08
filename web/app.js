"use strict";

const elements = Object.fromEntries([
  "api-key", "connect", "connection-state", "model", "reasoning", "temperature",
  "max-tokens", "messages", "composer", "prompt", "send", "stop", "clear",
  "request-state", "ttft", "duration", "prompt-tokens", "output-tokens"
].map((id) => [id, document.getElementById(id)]));

const state = { key: "", messages: [], controller: null };

function setConnected(online, label) {
  elements["connection-state"].classList.toggle("online", online);
  elements["connection-state"].classList.toggle("offline", !online);
  elements["connection-state"].querySelector("span").textContent = label;
  elements.prompt.disabled = !online;
  elements.send.disabled = !online;
  elements.model.disabled = !online;
}

function authorization() {
  return { "Authorization": `Bearer ${state.key}` };
}

function addMessage(role, content = "") {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const label = document.createElement("div");
  label.className = "role";
  label.textContent = role === "user" ? "TU" : role === "assistant" ? "MODELLO" : "SISTEMA";
  const reasoning = document.createElement("p");
  reasoning.className = "reasoning";
  reasoning.hidden = true;
  const text = document.createElement("p");
  text.textContent = content;
  article.append(label, reasoning, text);
  elements.messages.append(article);
  elements.messages.scrollTop = elements.messages.scrollHeight;
  return { article, reasoning, text };
}

function showError(message) {
  const view = addMessage("error", message);
  view.article.querySelector(".role").textContent = "ERRORE";
}

async function connect() {
  const key = elements["api-key"].value.trim();
  if (!key || /[\r\n]/.test(key)) {
    showError("Inserisci una gateway key valida.");
    return;
  }
  elements.connect.disabled = true;
  elements["request-state"].textContent = "verifica gateway";
  try {
    const response = await fetch("/v1/models", { headers: { "Authorization": `Bearer ${key}` } });
    if (!response.ok) throw new Error(`Gateway HTTP ${response.status}`);
    const catalog = await response.json();
    const models = Array.isArray(catalog.data) ? catalog.data : [];
    if (!models.length) throw new Error("Nessun modello attivo");
    state.key = key;
    sessionStorage.setItem("domesticllm.gatewayKey", key);
    elements.model.replaceChildren();
    for (const model of models) {
      if (!model || typeof model.id !== "string") continue;
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = `${model.id} · ${model.domesticllm_lane || "local"}`;
      elements.model.append(option);
    }
    setConnected(true, `${models.length} modelli online`);
    elements.prompt.focus();
    elements["request-state"].textContent = "pronto";
  } catch (error) {
    state.key = "";
    sessionStorage.removeItem("domesticllm.gatewayKey");
    setConnected(false, "accesso negato");
    showError(error.message);
    elements["request-state"].textContent = "connessione fallita";
  } finally {
    elements.connect.disabled = false;
  }
}

function consumeEvent(raw, view, turn) {
  if (!raw || raw === "[DONE]") return;
  let event;
  try { event = JSON.parse(raw); } catch { return; }
  if (event.usage) turn.usage = event.usage;
  const choice = Array.isArray(event.choices) ? event.choices[0] : null;
  if (!choice) return;
  const delta = choice.delta || {};
  const reasoning = delta.reasoning_content || delta.reasoning || "";
  const content = delta.content || "";
  if ((reasoning || content) && !turn.firstTokenAt) {
    turn.firstTokenAt = performance.now();
    elements.ttft.textContent = `${((turn.firstTokenAt - turn.startedAt) / 1000).toFixed(2)} s`;
  }
  if (reasoning) {
    turn.reasoning += reasoning;
    view.reasoning.hidden = false;
    view.reasoning.textContent = turn.reasoning;
  }
  if (content) {
    turn.content += content;
    view.text.textContent = turn.content;
  }
  if (reasoning || content) elements.messages.scrollTop = elements.messages.scrollHeight;
}

async function send(event) {
  event.preventDefault();
  const prompt = elements.prompt.value.trim();
  if (!prompt || state.controller) return;
  const model = elements.model.value;
  state.messages.push({ role: "user", content: prompt });
  addMessage("user", prompt);
  elements.prompt.value = "";
  const view = addMessage("assistant", "In attesa del primo token…");
  const turn = { startedAt: performance.now(), firstTokenAt: 0, content: "", reasoning: "", usage: {} };
  const payload = {
    model,
    messages: state.messages,
    max_tokens: Number(elements["max-tokens"].value),
    max_completion_tokens: Number(elements["max-tokens"].value),
    temperature: Number(elements.temperature.value),
    stream: true,
    stream_options: { include_usage: true }
  };
  if (elements.reasoning.value === "direct") {
    payload.thinking = { type: "disabled" };
    payload.chat_template_kwargs = { enable_thinking: false };
  } else {
    payload.reasoning_effort = elements.reasoning.value;
  }
  state.controller = new AbortController();
  elements.send.disabled = true;
  elements.stop.disabled = false;
  elements["request-state"].textContent = "prefill / generazione";
  try {
    const response = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { ...authorization(), "Content-Type": "application/json", "Accept": "text/event-stream" },
      body: JSON.stringify(payload),
      signal: state.controller.signal
    });
    if (!response.ok) throw new Error(`Inferenza HTTP ${response.status}: ${(await response.text()).slice(0, 300)}`);
    if (!response.body) throw new Error("Risposta streaming non disponibile");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data:")) consumeEvent(line.slice(5).trim(), view, turn);
      }
      if (done) break;
    }
    if (buffer.startsWith("data:")) consumeEvent(buffer.slice(5).trim(), view, turn);
    const answer = turn.content || turn.reasoning;
    if (!answer) throw new Error("Stream completato senza contenuto");
    view.text.textContent = turn.content || turn.reasoning;
    if (!turn.content) view.reasoning.hidden = true;
    state.messages.push({ role: "assistant", content: answer });
    elements["request-state"].textContent = "completato";
  } catch (error) {
    if (error.name === "AbortError") {
      view.text.textContent = turn.content || "Richiesta fermata dall'operatore.";
      elements["request-state"].textContent = "fermato";
    } else {
      view.article.classList.add("error");
      view.text.textContent = error.message;
      elements["request-state"].textContent = "errore";
    }
  } finally {
    const elapsed = (performance.now() - turn.startedAt) / 1000;
    elements.duration.textContent = `${elapsed.toFixed(1)} s`;
    elements["prompt-tokens"].textContent = turn.usage.prompt_tokens ?? "—";
    elements["output-tokens"].textContent = turn.usage.completion_tokens ?? "—";
    state.controller = null;
    elements.send.disabled = !state.key;
    elements.stop.disabled = true;
    elements.prompt.focus();
  }
}

function clearSession() {
  if (state.controller) return;
  state.messages = [];
  elements.messages.replaceChildren();
  addMessage("system", "Nuova sessione locale. La cache lato server resta gestita dal runtime.");
  for (const id of ["ttft", "duration", "prompt-tokens", "output-tokens"]) elements[id].textContent = "—";
}

elements.connect.addEventListener("click", connect);
elements.composer.addEventListener("submit", send);
elements.stop.addEventListener("click", () => state.controller?.abort());
elements.clear.addEventListener("click", clearSession);
elements.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.ctrlKey) elements.composer.requestSubmit();
});

const savedKey = sessionStorage.getItem("domesticllm.gatewayKey");
if (savedKey) {
  elements["api-key"].value = savedKey;
  connect();
}
