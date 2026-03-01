(function () {
  "use strict";

  const state = {
    ws: null,
    reconnectAttempts: 0,
    flows: [],
    selectedFlowId: null,
    selectedFlow: null,
    queue: { pending: [], active: null },
    config: null,
    prettyJson: true,
    loadingFlow: false,
    pollTimer: null,
  };

  const el = {
    statusDot: document.getElementById("statusDot"),
    statusText: document.getElementById("statusText"),
    errorMessage: document.getElementById("errorMessage"),
    flowList: document.getElementById("flowList"),
    queueHead: document.getElementById("queueHead"),
    queueCount: document.getElementById("queueCount"),
    searchInput: document.getElementById("searchInput"),
    methodFilter: document.getElementById("methodFilter"),
    statusFilter: document.getElementById("statusFilter"),
    interceptEnabled: document.getElementById("interceptEnabled"),
    prettyJson: document.getElementById("prettyJson"),
    themeToggle: document.getElementById("themeToggle"),
    exportSelected: document.getElementById("exportSelected"),
    clearAll: document.getElementById("clearAll"),
    requestPanel: document.getElementById("requestPanel"),
    responsePanel: document.getElementById("responsePanel"),
    headersPanel: document.getElementById("headersPanel"),
    modifyPanel: document.getElementById("modifyPanel"),
    tabs: Array.from(document.querySelectorAll(".tab")),
    panels: {
      request: document.getElementById("requestPanel"),
      response: document.getElementById("responsePanel"),
      headers: document.getElementById("headersPanel"),
      modify: document.getElementById("modifyPanel"),
    },
  };

  function setStatus(connected) {
    el.statusDot.classList.toggle("connected", connected);
    el.statusText.textContent = connected ? "connected" : "disconnected";
  }

  function setMessage(text) {
    if (!text) {
      el.errorMessage.style.display = "none";
      el.errorMessage.textContent = "";
      return;
    }
    el.errorMessage.style.display = "block";
    el.errorMessage.textContent = text;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      throw new Error("Invalid API response");
    }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || payload.detail || `API error (${response.status})`);
    }
    return payload.data;
  }

  async function refreshFlows() {
    const query = new URLSearchParams();
    query.set("limit", "200");
    const search = el.searchInput.value.trim();
    if (search) query.set("search", search);
    const method = el.methodFilter.value;
    if (method) query.set("method", method);
    const status = el.statusFilter.value;
    if (status) query.set("status", status);

    state.flows = await api(`/api/flows?${query.toString()}`);
    renderFlowList();
  }

  async function refreshQueue() {
    state.queue = await api("/api/flows/queue");
    renderQueue();
  }

  async function refreshConfig() {
    state.config = await api("/api/config");
    el.interceptEnabled.checked = !!state.config.intercept_enabled;
  }

  function scheduleReconnect() {
    setStatus(false);
    setMessage("Realtime stream disconnected. Using polling fallback.");
    const delay = Math.min(30000, 500 * 2 ** state.reconnectAttempts);
    state.reconnectAttempts += 1;
    setTimeout(connectWebSocket, delay);
  }

  function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    state.ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    state.ws.addEventListener("open", () => {
      state.reconnectAttempts = 0;
      setStatus(true);
      setMessage("");
    });

    state.ws.addEventListener("close", () => {
      scheduleReconnect();
    });

    state.ws.addEventListener("error", () => {
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.close();
      }
    });

    state.ws.addEventListener("message", (event) => {
      let message = null;
      try {
        message = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      onWsMessage(message);
    });
  }

  function onWsMessage(message) {
    switch (message.event) {
      case "init":
        state.config = message.data.config;
        state.queue = message.data.queue;
        state.flows = message.data.flows;
        el.interceptEnabled.checked = !!state.config.intercept_enabled;
        renderQueue();
        renderFlowList();
        break;
      case "config.updated":
        state.config = message.data || state.config;
        if (state.config) {
          el.interceptEnabled.checked = !!state.config.intercept_enabled;
        }
        break;
      case "flow.created":
      case "flow.updated":
      case "flow.completed":
      case "flow.dropped":
        if (!message.data || !message.data.id) {
          break;
        }
        upsertFlowSummary(message.data);
        renderFlowList();
        if (state.selectedFlowId === message.data.id) {
          loadFlowDetail(state.selectedFlowId);
        }
        break;
      case "queue.updated":
        state.queue = message.data;
        renderQueue();
        break;
      case "error":
        setMessage(String(message.data && message.data.message ? message.data.message : "Unknown server error"));
        break;
      case "ping":
        sendPong();
        break;
      case "flows.cleared":
        state.flows = [];
        state.selectedFlow = null;
        state.selectedFlowId = null;
        state.queue = { pending: [], active: null };
        renderQueue();
        renderFlowList();
        renderPanels();
        break;
      default:
        break;
    }
  }

  function sendPong() {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify({ event: "pong", data: { ts: Date.now() } }));
  }

  function upsertFlowSummary(summary) {
    const index = state.flows.findIndex((item) => item.id === summary.id);
    if (index === -1) {
      state.flows.unshift(summary);
      return;
    }
    state.flows[index] = { ...state.flows[index], ...summary };
  }

  function renderQueue() {
    el.queueHead.textContent = state.queue.active || "none";
    el.queueCount.textContent = String((state.queue.pending || []).length);
  }

  function renderFlowList() {
    el.flowList.innerHTML = "";
    for (const flow of state.flows) {
      const item = document.createElement("div");
      item.className = "flow-item";
      if (flow.id === state.selectedFlowId) item.classList.add("active");
      item.dataset.flowId = flow.id;

      const row = document.createElement("div");
      row.className = "flow-row";

      const method = document.createElement("span");
      method.className = "method";
      method.textContent = String(flow.method || "UNK").toUpperCase();

      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = `${flow.status}${flow.queue_position ? ` #${flow.queue_position}` : ""}`;

      const url = document.createElement("div");
      url.className = "flow-url";
      url.textContent = truncate(flow.url || "", 80);

      row.appendChild(method);
      row.appendChild(badge);
      item.appendChild(row);
      item.appendChild(url);
      item.addEventListener("click", () => {
        state.selectedFlowId = flow.id;
        loadFlowDetail(flow.id);
        renderFlowList();
      });
      el.flowList.appendChild(item);
    }
  }

  function truncate(text, max) {
    return text.length > max ? `${text.slice(0, max)}...` : text;
  }

  function safeJson(text) {
    if (!state.prettyJson) return String(text || "");
    if (!text) return "";
    try {
      return JSON.stringify(JSON.parse(text), null, 2);
    } catch (error) {
      return String(text);
    }
  }

  function renderPanels() {
    if (!state.selectedFlow) {
      el.requestPanel.innerHTML = `<div class="block"><h3>Request</h3><pre>No flow selected</pre></div>`;
      el.responsePanel.innerHTML = `<div class="block"><h3>Response</h3><pre>No flow selected</pre></div>`;
      el.headersPanel.innerHTML = `<div class="block"><h3>Headers</h3><pre>No flow selected</pre></div>`;
      el.modifyPanel.innerHTML = `<div class="block"><h3>Modify</h3><pre>No flow selected</pre></div>`;
      return;
    }

    const flow = state.selectedFlow;
    const req = flow.request || {};
    const resp = flow.response || null;

    el.requestPanel.innerHTML = "";
    el.responsePanel.innerHTML = "";
    el.headersPanel.innerHTML = "";
    el.modifyPanel.innerHTML = "";

    appendBlock(el.requestPanel, "URL", req.url || "");
    appendBlock(el.requestPanel, "Method", req.method || "");
    appendBlock(el.requestPanel, "Body", safeJson(req.body_text || ""));
    appendBlock(el.requestPanel, "Status", flow.status || "");

    if (resp) {
      appendBlock(el.responsePanel, "Status Code", String(resp.status_code || ""));
      appendBlock(el.responsePanel, "Reason", resp.reason || "");
      appendBlock(el.responsePanel, "Body", safeJson(resp.body_text || ""));
    } else {
      appendBlock(el.responsePanel, "Response", "No response captured");
    }

    appendBlock(el.headersPanel, "Request Headers", req.headers_raw || "");
    appendBlock(el.headersPanel, "Response Headers", resp ? resp.headers_raw || "" : "");

    const wrap = document.createElement("div");
    wrap.className = "block";
    const title = document.createElement("h3");
    title.textContent = "Decide";
    wrap.appendChild(title);

    if (flow.status === "pending_response") {
      const statusCodeInput = document.createElement("input");
      statusCodeInput.id = "editStatusCode";
      statusCodeInput.value = String((resp && resp.status_code) || 200);
      wrap.appendChild(statusCodeInput);

      const reasonInput = document.createElement("input");
      reasonInput.id = "editReason";
      reasonInput.value = (resp && resp.reason) || "OK";
      reasonInput.style.marginTop = "8px";
      wrap.appendChild(reasonInput);

      const respHeadersInput = document.createElement("textarea");
      respHeadersInput.id = "editRespHeaders";
      respHeadersInput.value = (resp && resp.headers_raw) || "";
      respHeadersInput.style.marginTop = "8px";
      wrap.appendChild(respHeadersInput);

      const respBodyInput = document.createElement("textarea");
      respBodyInput.id = "editRespBody";
      respBodyInput.value = (resp && resp.body_text) || "";
      respBodyInput.style.marginTop = "8px";
      wrap.appendChild(respBodyInput);

      const actions = document.createElement("div");
      actions.className = "actions";
      const forward = document.createElement("button");
      forward.className = "primary";
      forward.textContent = "Forward Response";
      const drop = document.createElement("button");
      drop.className = "danger";
      drop.textContent = "Drop Response";
      actions.appendChild(forward);
      actions.appendChild(drop);
      wrap.appendChild(actions);
      el.modifyPanel.appendChild(wrap);

      forward.addEventListener("click", async () => {
        await submitResponseDecision("forward");
      });
      drop.addEventListener("click", async () => {
        await submitResponseDecision("drop");
      });
      return;
    }

    const methodInput = document.createElement("input");
    methodInput.id = "editMethod";
    methodInput.value = req.method || "GET";
    wrap.appendChild(methodInput);

    const urlInput = document.createElement("input");
    urlInput.id = "editUrl";
    urlInput.value = req.url || "";
    urlInput.style.marginTop = "8px";
    wrap.appendChild(urlInput);

    const headersInput = document.createElement("textarea");
    headersInput.id = "editHeaders";
    headersInput.value = req.headers_raw || "";
    headersInput.style.marginTop = "8px";
    wrap.appendChild(headersInput);

    const bodyInput = document.createElement("textarea");
    bodyInput.id = "editBody";
    bodyInput.value = req.body_text || "";
    bodyInput.style.marginTop = "8px";
    wrap.appendChild(bodyInput);

    const interceptRespLabel = document.createElement("label");
    interceptRespLabel.style.display = "block";
    interceptRespLabel.style.marginTop = "8px";
    const interceptRespCheckbox = document.createElement("input");
    interceptRespCheckbox.type = "checkbox";
    interceptRespCheckbox.id = "interceptResp";
    interceptRespCheckbox.checked = !!(flow.metadata && flow.metadata.intercept_response);
    interceptRespLabel.appendChild(interceptRespCheckbox);
    interceptRespLabel.appendChild(document.createTextNode(" Intercept response"));
    wrap.appendChild(interceptRespLabel);

    const actions = document.createElement("div");
    actions.className = "actions";
    const forward = document.createElement("button");
    forward.className = "primary";
    forward.textContent = "Forward Request";
    const drop = document.createElement("button");
    drop.className = "danger";
    drop.textContent = "Drop Request";
    actions.appendChild(forward);
    actions.appendChild(drop);
    wrap.appendChild(actions);
    el.modifyPanel.appendChild(wrap);

    const queueHead = state.queue.active;
    const isPendingRequest = flow.status === "pending_request";
    if (isPendingRequest && queueHead && queueHead !== flow.id) {
      forward.disabled = true;
      drop.disabled = true;
      setMessage(`Flow ${flow.id} is not queue head. Active is ${queueHead}`);
    }

    forward.addEventListener("click", async () => {
      await submitRequestDecision("forward");
    });
    drop.addEventListener("click", async () => {
      await submitRequestDecision("drop");
    });
  }

  function appendBlock(parent, titleText, bodyText) {
    const block = document.createElement("div");
    block.className = "block";
    const title = document.createElement("h3");
    title.textContent = titleText;
    const pre = document.createElement("pre");
    pre.textContent = bodyText || "(empty)";
    block.appendChild(title);
    block.appendChild(pre);
    parent.appendChild(block);
  }

  async function loadFlowDetail(flowId) {
    if (!flowId) return;
    state.loadingFlow = true;
    try {
      const flow = await api(`/api/flows/${encodeURIComponent(flowId)}`);
      state.selectedFlow = flow;
      renderPanels();
      setMessage("");
    } catch (error) {
      setMessage(error.message);
    } finally {
      state.loadingFlow = false;
    }
  }

  async function submitRequestDecision(action) {
    if (!state.selectedFlow) return;
    const flow = state.selectedFlow;
    if (flow.status !== "pending_request") {
      setMessage("Selected flow is not pending_request");
      return;
    }

    const payload = {
      action,
      method: document.getElementById("editMethod").value,
      url: document.getElementById("editUrl").value,
      headers_raw: document.getElementById("editHeaders").value,
      body_text: document.getElementById("editBody").value,
      intercept_response: document.getElementById("interceptResp").checked,
    };

    try {
      await api(`/api/flows/${encodeURIComponent(flow.id)}/request/decision`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setMessage("");
      await Promise.all([refreshFlows(), refreshQueue()]);
      await loadFlowDetail(flow.id);
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function submitResponseDecision(action) {
    if (!state.selectedFlow) return;
    const flow = state.selectedFlow;
    if (flow.status !== "pending_response") {
      setMessage("Selected flow is not pending_response");
      return;
    }

    const statusCodeRaw = document.getElementById("editStatusCode").value;
    const statusCode = Number.parseInt(statusCodeRaw, 10);
    const payload = {
      action,
      status_code: Number.isFinite(statusCode) ? statusCode : 200,
      reason: document.getElementById("editReason").value,
      headers_raw: document.getElementById("editRespHeaders").value,
      body_text: document.getElementById("editRespBody").value,
    };

    try {
      await api(`/api/flows/${encodeURIComponent(flow.id)}/response/decision`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setMessage("");
      await Promise.all([refreshFlows(), refreshQueue()]);
      await loadFlowDetail(flow.id);
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function exportSelected() {
    if (!state.selectedFlow) {
      setMessage("Select a flow first");
      return;
    }
    const blob = new Blob([JSON.stringify(state.selectedFlow, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `flow_${state.selectedFlow.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function clearAll() {
    if (!window.confirm("Clear all captured flows?")) return;
    try {
      await api("/api/flows/clear", { method: "POST" });
      await Promise.all([refreshFlows(), refreshQueue()]);
      state.selectedFlow = null;
      state.selectedFlowId = null;
      renderPanels();
    } catch (error) {
      setMessage(error.message);
    }
  }

  function bindEvents() {
    el.searchInput.addEventListener("input", debounce(() => refreshFlows().catch((error) => setMessage(error.message)), 300));
    el.methodFilter.addEventListener("change", () => refreshFlows().catch((error) => setMessage(error.message)));
    el.statusFilter.addEventListener("change", () => refreshFlows().catch((error) => setMessage(error.message)));

    el.interceptEnabled.addEventListener("change", async (event) => {
      if (!state.config) return;
      try {
        const payload = { ...state.config, intercept_enabled: event.target.checked };
        state.config = await api("/api/config", {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } catch (error) {
        event.target.checked = !event.target.checked;
        setMessage(error.message);
      }
    });

    el.prettyJson.addEventListener("change", (event) => {
      state.prettyJson = event.target.checked;
      renderPanels();
    });

    el.themeToggle.addEventListener("click", () => {
      document.body.classList.toggle("light");
      el.themeToggle.textContent = document.body.classList.contains("light") ? "Dark" : "Light";
    });

    el.exportSelected.addEventListener("click", () => exportSelected());
    el.clearAll.addEventListener("click", () => clearAll());

    for (const tab of el.tabs) {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        for (const each of el.tabs) each.classList.remove("active");
        tab.classList.add("active");
        for (const panelKey of Object.keys(el.panels)) {
          el.panels[panelKey].classList.toggle("active", panelKey === target);
        }
      });
    }
  }

  function startBackgroundPolling() {
    if (state.pollTimer) return;
    state.pollTimer = setInterval(async () => {
      try {
        await Promise.all([refreshFlows(), refreshQueue()]);
        if (state.selectedFlowId) {
          await loadFlowDetail(state.selectedFlowId);
        }
      } catch (error) {
        setMessage(error.message);
      }
    }, 3000);
  }

  function debounce(fn, delayMs) {
    let timer = null;
    return function () {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => fn(), delayMs);
    };
  }

  async function boot() {
    bindEvents();
    renderPanels();
    connectWebSocket();
    startBackgroundPolling();
    try {
      await Promise.all([refreshConfig(), refreshFlows(), refreshQueue()]);
    } catch (error) {
      setMessage(error.message);
    }
  }

  boot().catch((error) => setMessage(error.message));
})();
