/* Conversation state stays in this tab. Document text is always rendered as text. */
(() => {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const form = byId("chat-form");
  const question = byId("question");
  const send = byId("send");
  const messages = byId("messages");
  const notice = byId("setup-notice");
  let history = [];
  let ready = false;
  let busy = false;
  let epoch = 0;
  let controller = null;
  let botName = "eve-ah";
  let suggestedQuestions = [];

  function updateSend() {
    send.disabled = !ready || busy || !question.value.trim();
  }

  function addMessage(role, text, status = "", extraClass = "") {
    const article = document.createElement("article");
    article.className = `message ${role} ${extraClass}`.trim();
    const heading = document.createElement("div");
    heading.className = "message-heading";
    const avatar = document.createElement("span");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "Y" : "e.";
    avatar.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.textContent = role === "user" ? "You" : botName;
    heading.append(avatar, name);
    if (status) {
      const label = document.createElement("span");
      label.className = "answer-status";
      label.textContent = status;
      heading.append(label);
    }
    const body = document.createElement("p");
    body.className = "message-body";
    body.textContent = text;
    article.append(heading, body);
    messages.append(article);
    return article;
  }

  function ask(prompt) {
    if (!ready || busy) return;
    question.value = prompt;
    updateSend();
    form.requestSubmit();
  }

  function promptButton(label, prompt = label, className = "prompt-chip") {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    button.addEventListener("click", () => ask(prompt));
    return button;
  }

  function renderGuides(info) {
    suggestedQuestions = Array.isArray(info.suggested_questions) ? info.suggested_questions.slice(0, 6) : [];
    const suggestions = byId("welcome-suggestions");
    suggestions.replaceChildren(...suggestedQuestions.map((item) => promptButton(item)));
    byId("suggestion-guide").hidden = suggestedQuestions.length === 0;

    const topics = Array.isArray(info.topics) ? info.topics.slice(0, 8) : [];
    const topicGuides = byId("topic-guides");
    topicGuides.replaceChildren(...topics.map((topic) => {
      const button = promptButton(topic.name, `What can you tell me about ${topic.name}?`, "topic-chip");
      button.title = topic.description || topic.name;
      return button;
    }));
    byId("topic-guide").hidden = topics.length === 0;
  }

  function addRecoveryPrompts(article, grounding) {
    const recoveryTypes = new Set(["action", "live_data", "out_of_scope", "insufficient", "clarification"]);
    if (!recoveryTypes.has(grounding) || suggestedQuestions.length === 0) return;
    const prompts = document.createElement("div");
    prompts.className = "message-prompts";
    prompts.setAttribute("aria-label", "Suggested questions");
    prompts.append(...suggestedQuestions.slice(0, 3).map((item) => promptButton(item)));
    article.append(prompts);
  }

  function sourceTitle(name) {
    const leaf = String(name || "Source").split("/").pop().replace(/\.[^.]+$/, "");
    return leaf.split(/[-_]+/).filter(Boolean).map((word) => word[0].toUpperCase() + word.slice(1)).join(" ");
  }

  function displayAnswer(answer, sources) {
    let displayed = answer;
    sources.forEach((source, index) => {
      displayed = displayed.split(`[${source.id}]`).join(`[${index + 1}]`);
    });
    return displayed;
  }

  function showSources(sources) {
    byId("sources").replaceChildren();
    const hasSources = sources.length > 0;
    byId("evidence-panel").hidden = !hasSources;
    document.querySelector(".conversation-layout").classList.toggle("has-evidence", hasSources);
    sources.forEach((source, index) => {
      const card = document.createElement("details");
      card.className = "source-card";
      const summary = document.createElement("summary");
      summary.textContent = `[${index + 1}] ${sourceTitle(source.name)}`;
      const meta = document.createElement("span");
      meta.className = "source-meta";
      meta.textContent = `${source.name}${source.page ? ` · Page ${source.page}` : ""}`;
      summary.append(meta);
      const excerpt = document.createElement("p");
      excerpt.textContent = source.text;
      card.append(summary, excerpt);
      byId("sources").append(card);
    });
  }

  function boundedHistory(turns) {
    const bounded = turns.slice(-12).map((turn) => ({
      role: turn.role,
      content: turn.content.slice(0, 8000),
    }));
    while (bounded.reduce((total, turn) => total + turn.content.length, 0) > 20000) {
      bounded.shift();
    }
    return bounded;
  }

  async function readJson(response) {
    try {
      return await response.json();
    } catch {
      throw new Error("The server returned an unreadable response. Please try again.");
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = question.value.trim();
    if (!message || busy || !ready) return;
    const requestEpoch = epoch;
    const requestHistory = boundedHistory(history);
    controller = new AbortController();
    busy = true;
    updateSend();
    byId("welcome").hidden = true;
    question.value = "";
    addMessage("user", message);
    showSources([]);
    const pending = addMessage("assistant", "Finding the best way to help…", "", "pending");
    pending.setAttribute("aria-busy", "true");
    form.scrollIntoView({ block: "nearest" });
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history: requestHistory }),
        signal: controller.signal,
      });
      const data = await readJson(response);
      if (requestEpoch !== epoch) return;
      if (!response.ok) throw new Error(data.error?.message || "Unable to answer right now. Please try again.");
      if (typeof data.answer !== "string" || !Array.isArray(data.sources)) {
        throw new Error("The server returned an incomplete answer. Please try again.");
      }
      pending.remove();
      const labels = { documents: "Source-backed answer", capability: "What I can help with", clarification: "A little more detail needed", general: "General knowledge · not from your documents", insufficient: "More detail needed", small_talk: "Conversation", action: "I can explain, but not complete actions", live_data: "Published information only", out_of_scope: "Try another topic" };
      const responseType = data.response_type || data.grounding;
      const assistant = addMessage("assistant", displayAnswer(data.answer, data.sources), labels[responseType] || "");
      addRecoveryPrompts(assistant, responseType);
      showSources(data.sources);
      history = boundedHistory([...requestHistory, { role: "user", content: message }, { role: "assistant", content: data.answer }]);
    } catch (error) {
      if (requestEpoch !== epoch || error.name === "AbortError") return;
      pending.remove();
      addMessage("assistant", error.message || "Connection lost. Please try again.", "Request failed", "error");
      question.value = message;
    } finally {
      if (requestEpoch === epoch) {
        busy = false;
        controller = null;
        updateSend();
        question.focus({ preventScroll: true });
        form.scrollIntoView({ block: "nearest" });
      }
    }
  });

  question.addEventListener("input", updateSend);
  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!send.disabled) form.requestSubmit();
    }
  });

  byId("clear-chat").addEventListener("click", () => {
    epoch += 1;
    controller?.abort();
    controller = null;
    busy = false;
    history = [];
    messages.replaceChildren();
    showSources([]);
    byId("welcome").hidden = false;
    question.value = "";
    updateSend();
    question.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  });

  async function connect() {
    try {
      const response = await fetch("/api/info");
      const info = await readJson(response);
      if (!response.ok) throw new Error("Could not load workspace settings.");
      ready = Boolean(info.ready);
      botName = info.name || "eve-ah";
      document.querySelectorAll("[data-bot-name]").forEach((element) => { element.textContent = botName; });
      document.title = `${botName} — Document chat`;
      if (info.welcome && info.welcome !== "Ask a question. Find the source.") {
        byId("welcome-copy").textContent = info.welcome;
      }
      renderGuides(info);
      byId("provider-label").textContent = info.provider || "Not configured";
      byId("provider-label").title = info.model || "";
      byId("mode-label").textContent = info.mode === "general" ? "General mode" : "Knowledge mode";
      byId("readiness-label").textContent = ready ? "Ready to explore" : "Setup required";
      if (!ready) {
        notice.textContent = "This workspace isn't ready yet. Configure your API key, index your documents with eve-ah ingest, then restart the server and refresh this page.";
        notice.hidden = false;
      }
    } catch (error) {
      ready = false;
      byId("provider-label").textContent = "Unavailable";
      byId("readiness-label").textContent = "Disconnected";
      notice.textContent = `${error.message} Check that the server is running, then refresh this page.`;
      notice.hidden = false;
    }
    updateSend();
  }

  connect();
})();
