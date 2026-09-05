const CHAT_STORAGE_KEY = "domesticllm.chat-history.v1";
const ACTIVE_CHAT_KEY = "domesticllm.active-chat.v1";
const MAX_CHATS = 30;
const MAX_STORED_MESSAGES = 120;
const DEFAULT_SYSTEM_PROMPT = "Sei un assistente utile, diretto e competente.";
const DEFAULT_SETTINGS = Object.freeze({
  temperature: 0.7,
  maxTokens: 1024,
  topP: 0.95,
  topK: 40,
  minP: 0,
  repeatPenalty: 1,
  presencePenalty: 0,
  frequencyPenalty: 0,
  seed: -1,
  stop: "",
  context: 4096,
  parallel: 1,
  flashAttention: "auto",
  kvCache: "q8_0"
});

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function uniqueId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function clampNumber(value, minimum, maximum, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(maximum, Math.max(minimum, number)) : fallback;
}

function normalizeSettings(value = {}) {
  return {
    temperature: clampNumber(value.temperature, 0, 2, DEFAULT_SETTINGS.temperature),
    maxTokens: Math.round(clampNumber(value.maxTokens, 1, 8192, DEFAULT_SETTINGS.maxTokens)),
    topP: clampNumber(value.topP, 0, 1, DEFAULT_SETTINGS.topP),
    topK: Math.round(clampNumber(value.topK, 0, 200, DEFAULT_SETTINGS.topK)),
    minP: clampNumber(value.minP, 0, 1, DEFAULT_SETTINGS.minP),
    repeatPenalty: clampNumber(value.repeatPenalty, 0, 2, DEFAULT_SETTINGS.repeatPenalty),
    presencePenalty: clampNumber(value.presencePenalty, -2, 2, DEFAULT_SETTINGS.presencePenalty),
    frequencyPenalty: clampNumber(value.frequencyPenalty, -2, 2, DEFAULT_SETTINGS.frequencyPenalty),
    seed: Math.round(clampNumber(value.seed, -1, 2147483647, DEFAULT_SETTINGS.seed)),
    stop: typeof value.stop === "string" ? value.stop.slice(0, 4000) : "",
    context: [2048, 4096, 8192, 16384].includes(Number(value.context)) ? Number(value.context) : DEFAULT_SETTINGS.context,
    parallel: [1, 2, 3, 4].includes(Number(value.parallel)) ? Number(value.parallel) : DEFAULT_SETTINGS.parallel,
    flashAttention: ["auto", "on", "off"].includes(value.flashAttention) ? value.flashAttention : DEFAULT_SETTINGS.flashAttention,
    kvCache: ["q4_0", "q8_0", "f16"].includes(value.kvCache) ? value.kvCache : DEFAULT_SETTINGS.kvCache
  };
}

document.addEventListener("alpine:init", () => {
  Alpine.data("domesticApp", () => ({
    models: [],
    hostStatus: null,
    connectionState: "loading",
    chats: [],
    activeChatId: "",
    modelId: "",
    systemPrompt: DEFAULT_SYSTEM_PROMPT,
    settings: clone(DEFAULT_SETTINGS),
    draft: "",
    busy: false,
    busyLabel: "Preparazione del modello…",
    errorMessage: "",
    storageWarning: "",
    mobilePanel: null,
    statusTimer: null,
    saveTimer: null,
    busyTimer: null,

    async init() {
      this.loadHistory();
      if (!this.chats.length) this.newChat(false);
      else {
        let savedChatId = "";
        try { savedChatId = localStorage.getItem(ACTIVE_CHAT_KEY) || ""; }
        catch { this.storageWarning = "Il browser impedisce l’accesso allo storico locale."; }
        this.selectChat(savedChatId || this.chats[0].id, false);
      }
      await this.loadModelsAndStatus();
      this.statusTimer = setInterval(() => this.refreshStatus(), 5000);
      window.addEventListener("beforeunload", () => this.saveHistory());
    },

    get activeChat() {
      return this.chats.find((chat) => chat.id === this.activeChatId) || null;
    },

    get selectedModel() {
      return this.models.find((model) => model.id === this.modelId) || null;
    },

    get selectedModelReady() {
      return Boolean(this.selectedModel?.ready);
    },

    get groupedChats() {
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      const groups = { "Oggi": [], "Ultimi 7 giorni": [], "Meno recenti": [] };
      [...this.chats].sort((a, b) => b.updatedAt - a.updatedAt).forEach((chat) => {
        const age = today - chat.updatedAt;
        if (chat.updatedAt >= today) groups["Oggi"].push(chat);
        else if (age < 7 * 86400000) groups["Ultimi 7 giorni"].push(chat);
        else groups["Meno recenti"].push(chat);
      });
      return Object.entries(groups).filter(([, items]) => items.length).map(([label, items]) => ({ label, items }));
    },

    get connectionClass() {
      return this.connectionState === "ready" ? "ready" : this.connectionState === "error" ? "error" : "";
    },

    get connectionLabel() {
      if (this.connectionState === "error") return "Gateway non raggiungibile";
      if (this.connectionState === "loading") return "Connessione…";
      return this.hostStatus?.active_model ? `Attivo: ${this.hostStatus.active_model}` : "Gateway pronto";
    },

    get sessionSummary() {
      if (!this.hostStatus?.active_model) return "nessuna sessione attiva";
      const seconds = Math.round(this.hostStatus.session?.elapsed_seconds || 0);
      return `sessione attiva da ${this.formatDuration(seconds)}`;
    },

    get sessionRequests() {
      const count = this.hostStatus?.session?.requests || 0;
      return `${count} ${count === 1 ? "richiesta" : "richieste"}`;
    },

    get prefillRate() {
      const value = this.hostStatus?.session?.last_generation?.prefill_tokens_per_second;
      return Number.isFinite(value) ? `${value.toFixed(1)} tok/s` : "—";
    },

    get generationRate() {
      const value = this.hostStatus?.session?.last_generation?.generation_tokens_per_second;
      return Number.isFinite(value) ? `${value.toFixed(1)} tok/s` : "—";
    },

    get generatedTokens() {
      const value = this.hostStatus?.session?.last_generation?.generated_tokens;
      return Number.isFinite(value) ? value.toLocaleString("it-IT") : "—";
    },

    loadHistory() {
      try {
        const parsed = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || "[]");
        if (!Array.isArray(parsed)) return;
        this.chats = parsed.slice(0, MAX_CHATS).map((chat) => ({
          id: typeof chat.id === "string" ? chat.id : uniqueId(),
          title: typeof chat.title === "string" ? chat.title.slice(0, 80) : "Conversazione",
          createdAt: Number(chat.createdAt) || Date.now(),
          updatedAt: Number(chat.updatedAt) || Date.now(),
          model: typeof chat.model === "string" ? chat.model : "",
          systemPrompt: typeof chat.systemPrompt === "string" ? chat.systemPrompt.slice(0, 10000) : DEFAULT_SYSTEM_PROMPT,
          settings: normalizeSettings(chat.settings),
          draft: typeof chat.draft === "string" ? chat.draft.slice(0, 50000) : "",
          messages: Array.isArray(chat.messages) ? chat.messages.slice(-MAX_STORED_MESSAGES).filter((message) => ["user", "assistant"].includes(message.role) && typeof message.content === "string").map((message) => ({ id: typeof message.id === "string" ? message.id : uniqueId(), role: message.role, content: message.content.slice(0, 100000), at: Number(message.at) || Date.now() })) : []
        }));
      } catch {
        this.storageWarning = "Lo storico salvato non era leggibile ed è stato ignorato.";
        this.chats = [];
      }
    },

    saveHistory() {
      try {
        const serializable = [...this.chats].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_CHATS).map((chat) => ({ ...chat, messages: chat.messages.slice(-MAX_STORED_MESSAGES) }));
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(serializable));
        localStorage.setItem(ACTIVE_CHAT_KEY, this.activeChatId);
      } catch {
        this.storageWarning = "Spazio locale esaurito: esporta o cancella alcune conversazioni per continuare a salvarle.";
      }
    },

    newChat(closePanel = true) {
      this.persistChatSettings();
      const now = Date.now();
      const chat = { id: uniqueId(), title: "Nuova chat", createdAt: now, updatedAt: now, model: this.modelId, systemPrompt: DEFAULT_SYSTEM_PROMPT, settings: clone(DEFAULT_SETTINGS), draft: "", messages: [] };
      this.chats.unshift(chat);
      this.activeChatId = chat.id;
      this.systemPrompt = chat.systemPrompt;
      this.settings = clone(chat.settings);
      this.draft = "";
      if (this.models.length) {
        const available = this.models.find((model) => model.ready);
        this.modelId = available?.id || this.models[0].id;
        chat.model = this.modelId;
        this.applyRecommendedSettings(false);
      }
      this.chats = this.chats.slice(0, MAX_CHATS);
      this.saveHistory();
      if (closePanel) this.mobilePanel = null;
      this.$nextTick(() => { this.resizeComposer(); this.$refs.composer?.focus(); });
    },

    selectChat(id, closePanel = true) {
      this.persistChatSettings();
      const chat = this.chats.find((item) => item.id === id) || this.chats[0];
      if (!chat) return;
      this.activeChatId = chat.id;
      this.modelId = chat.model;
      this.systemPrompt = chat.systemPrompt;
      this.settings = normalizeSettings(chat.settings);
      this.draft = chat.draft || "";
      this.errorMessage = "";
      if (closePanel) this.mobilePanel = null;
      this.saveHistory();
      this.$nextTick(() => { this.resizeComposer(); this.scrollBottom(false); });
    },

    renameChat(id) {
      const chat = this.chats.find((item) => item.id === id);
      if (!chat) return;
      const title = window.prompt("Titolo della conversazione", chat.title);
      if (title?.trim()) {
        chat.title = title.trim().slice(0, 80);
        chat.updatedAt = Date.now();
        this.saveHistory();
      }
    },

    deleteChat(id) {
      const chat = this.chats.find((item) => item.id === id);
      if (!chat || !window.confirm(`Eliminare “${chat.title}”?`)) return;
      this.chats = this.chats.filter((item) => item.id !== id);
      if (this.activeChatId === id) {
        if (this.chats.length) this.selectChat(this.chats[0].id);
        else this.newChat();
      }
      this.saveHistory();
    },

    clearHistory() {
      if (!window.confirm("Eliminare definitivamente tutte le conversazioni salvate in questo browser?")) return;
      this.chats = [];
      try {
        localStorage.removeItem(CHAT_STORAGE_KEY);
        localStorage.removeItem(ACTIVE_CHAT_KEY);
      } catch { this.storageWarning = "Il browser non consente di modificare lo storico locale."; }
      this.newChat();
    },

    exportHistory() {
      const payload = { version: 1, exportedAt: new Date().toISOString(), conversations: this.chats };
      const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `domesticllm-chat-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    },

    persistDraft() {
      if (!this.activeChat) return;
      this.activeChat.draft = this.draft.slice(0, 50000);
      clearTimeout(this.saveTimer);
      this.saveTimer = setTimeout(() => this.saveHistory(), 250);
    },

    persistChatSettings() {
      if (!this.activeChat) return;
      this.activeChat.model = this.modelId;
      this.activeChat.systemPrompt = this.systemPrompt.slice(0, 10000);
      this.activeChat.settings = normalizeSettings(this.settings);
      this.activeChat.draft = this.draft.slice(0, 50000);
      this.saveHistory();
    },

    async loadModelsAndStatus() {
      try {
        const [catalog, status] = await Promise.all([this.getJson("/ui/models"), this.getJson("/ui/status")]);
        this.models = Array.isArray(catalog.data) ? catalog.data : [];
        this.hostStatus = status;
        this.connectionState = "ready";
        const selectedIsValid = this.models.some((model) => model.id === this.modelId && model.ready);
        if (!selectedIsValid) {
          this.modelId = this.models.find((model) => model.ready)?.id || this.models[0]?.id || "";
          if (this.activeChat) this.activeChat.model = this.modelId;
          this.applyRecommendedSettings(false);
        }
        this.saveHistory();
      } catch (error) {
        this.connectionState = "error";
        this.errorMessage = `Connessione al gateway non riuscita: ${error.message}`;
      }
    },

    async refreshStatus() {
      try {
        this.hostStatus = await this.getJson("/ui/status");
        this.connectionState = "ready";
      } catch {
        this.connectionState = "error";
      }
    },

    async getJson(path) {
      const response = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    },

    onModelChanged() {
      this.applyRecommendedSettings(false);
      this.persistChatSettings();
    },

    applyRecommendedSettings(save = true) {
      const recommended = this.selectedModel?.defaults || {};
      this.settings = normalizeSettings({ ...DEFAULT_SETTINGS, ...recommended });
      if (save) this.persistChatSettings();
    },

    useSuggestion(text) {
      this.draft = text;
      this.persistDraft();
      this.$nextTick(() => { this.resizeComposer(); this.$refs.composer?.focus(); });
    },

    handleEnter(event) {
      if (!event.shiftKey && !event.isComposing) {
        event.preventDefault();
        this.sendMessage();
      }
    },

    resizeComposer() {
      const textarea = this.$refs.composer;
      if (!textarea) return;
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
    },

    async sendMessage() {
      const content = this.draft.trim();
      if (!content || this.busy) return;
      if (!this.selectedModelReady) {
        this.errorMessage = "Seleziona un modello disponibile prima di inviare il messaggio.";
        return;
      }
      const chat = this.activeChat;
      if (!chat) return;
      const now = Date.now();
      chat.messages.push({ id: uniqueId(), role: "user", content, at: now });
      if (chat.title === "Nuova chat") chat.title = content.replace(/\s+/g, " ").slice(0, 58) || "Conversazione";
      chat.updatedAt = now;
      chat.draft = "";
      this.draft = "";
      this.busy = true;
      this.busyLabel = this.hostStatus?.active_model === this.modelId ? "Generazione in corso…" : "Caricamento del modello…";
      this.errorMessage = "";
      clearTimeout(this.busyTimer);
      this.busyTimer = setTimeout(() => { this.busyLabel = "Generazione in corso…"; }, 1800);
      this.saveHistory();
      this.$nextTick(() => { this.resizeComposer(); this.scrollBottom(); });

      const normalized = normalizeSettings(this.settings);
      const stop = normalized.stop.split("\n").map((item) => item.trim()).filter(Boolean);
      const messages = chat.messages.map(({ role, content: messageContent }) => ({ role, content: messageContent }));
      if (this.systemPrompt.trim()) messages.unshift({ role: "system", content: this.systemPrompt.trim() });
      const payload = {
        model: this.modelId,
        messages,
        temperature: normalized.temperature,
        max_tokens: normalized.maxTokens,
        top_p: normalized.topP,
        top_k: normalized.topK,
        min_p: normalized.minP,
        repeat_penalty: normalized.repeatPenalty,
        presence_penalty: normalized.presencePenalty,
        frequency_penalty: normalized.frequencyPenalty,
        seed: normalized.seed,
        runtime: { context: normalized.context, parallel: normalized.parallel, flash_attention: normalized.flashAttention, kv_cache: normalized.kvCache }
      };
      if (stop.length) payload.stop = stop;
      const encoded = JSON.stringify(payload);
      if (new Blob([encoded]).size > 15 * 1024 * 1024) {
        this.errorMessage = "La conversazione è troppo grande per una singola richiesta. Avvia una nuova chat o riduci la cronologia.";
        this.busy = false;
        return;
      }

      try {
        const response = await fetch("/ui/chat", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: encoded });
        let result;
        try { result = await response.json(); }
        catch { throw new Error(`Risposta non valida dal backend (HTTP ${response.status})`); }
        if (!response.ok) throw new Error(this.friendlyError(result, response.status));
        const answer = result.choices?.[0]?.message?.content;
        if (typeof answer !== "string" || !answer.trim()) throw new Error("Il modello ha restituito una risposta vuota.");
        chat.messages.push({ id: uniqueId(), role: "assistant", content: answer, at: Date.now() });
        chat.updatedAt = Date.now();
        this.saveHistory();
        await this.refreshStatus();
      } catch (error) {
        this.errorMessage = error.message || "Errore inatteso durante la generazione.";
      } finally {
        clearTimeout(this.busyTimer);
        this.busy = false;
        this.$nextTick(() => this.scrollBottom());
      }
    },

    friendlyError(result, status) {
      const type = result?.error?.type;
      const message = result?.error?.message;
      if (type === "model_busy" || status === 429) return "Il motore sta completando un’altra richiesta. Attendi qualche secondo e riprova.";
      if (type === "model_not_admitted") return `Il modello non è disponibile su questo host: ${message || "profilo non ammesso"}`;
      if (status === 503) return `Il motore non è pronto: ${message || "controlla lo stato del servizio"}`;
      return message || `Richiesta non riuscita (HTTP ${status}).`;
    },

    scrollBottom(smooth = true) {
      const element = this.$refs.messages;
      if (element) element.scrollTo({ top: element.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    },

    async copyMessage(content) {
      try { await navigator.clipboard.writeText(content); }
      catch { this.errorMessage = "Il browser non consente di copiare automaticamente il messaggio."; }
    },

    modelShortName(id) {
      return this.models.find((model) => model.id === id)?.label || id || "modello";
    },

    formatTime(timestamp) {
      return new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" }).format(new Date(timestamp));
    },

    formatDuration(seconds) {
      if (seconds < 60) return `${seconds}s`;
      const minutes = Math.floor(seconds / 60);
      if (minutes < 60) return `${minutes}m`;
      return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
    }
  }));
});
