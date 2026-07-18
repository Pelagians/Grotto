(() => {
  "use strict";

  const scriptUrl = document.currentScript?.src || window.location.href;
  const eventUrl = new URL("grotto-claude-open-url.json", scriptUrl);
  const callbackUrl = new URL("grotto/claude-callback", scriptUrl);
  const pollIntervalMs = 750;
  const maxEventAgeMs = 15 * 60 * 1000;

  let lastEventId = sessionStorage.getItem("grottoClaudeOpenEventId") || "";
  let currentUrl = "";
  let overlay;
  let link;
  let hostname;
  let callbackInput;
  let callbackStatus;

  function isSafeEvent(event) {
    if (!event || event.version !== 1 || typeof event.id !== "string") {
      return false;
    }
    if (!event.id || event.id === lastEventId || typeof event.url !== "string") {
      return false;
    }

    let parsed;
    try {
      parsed = new URL(event.url);
    } catch (_error) {
      return false;
    }

    if (parsed.protocol !== "https:") {
      return false;
    }

    if (typeof event.created_at !== "number") {
      return false;
    }

    const age = Date.now() - event.created_at;
    return age >= -30000 && age <= maxEventAgeMs;
  }

  function isClaudeCallback(value) {
    return typeof value === "string" && value.trim().startsWith("claude://");
  }

  function setCallbackStatus(message, isError = false) {
    if (!callbackStatus) {
      return;
    }
    callbackStatus.textContent = message;
    callbackStatus.dataset.error = isError ? "true" : "false";
  }

  function copyCurrentUrl() {
    if (!currentUrl) {
      return;
    }

    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(currentUrl).catch(() => {});
      return;
    }

    const input = document.createElement("textarea");
    input.value = currentUrl;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }

  async function pasteCallback() {
    callbackInput.focus();
    if (!navigator.clipboard?.readText) {
      setCallbackStatus("Paste the copied claude:// link into the field.", true);
      return;
    }

    try {
      const value = (await navigator.clipboard.readText()).trim();
      if (!isClaudeCallback(value)) {
        setCallbackStatus("The clipboard does not contain a claude:// link.", true);
        return;
      }
      callbackInput.value = value;
      setCallbackStatus("Callback link pasted. Send it to remote Claude.");
    } catch (_error) {
      setCallbackStatus("Clipboard access was blocked. Paste the link manually.", true);
    }
  }

  async function sendCallback() {
    const uri = callbackInput.value.trim();
    if (!isClaudeCallback(uri)) {
      setCallbackStatus("Paste a claude:// callback link first.", true);
      callbackInput.focus();
      return;
    }

    setCallbackStatus("Sending callback to remote Claude…");
    try {
      const response = await fetch(callbackUrl, {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-Grotto-Claude-Relay": "1",
        },
        body: JSON.stringify({ uri }),
      });

      let payload = {};
      try {
        payload = await response.json();
      } catch (_error) {
        payload = {};
      }

      if (!response.ok || payload.ok !== true) {
        throw new Error(payload.error || `callback relay returned HTTP ${response.status}`);
      }

      callbackInput.value = "";
      setCallbackStatus("Callback delivered. Return to Claude Desktop in Selkies.");
    } catch (error) {
      setCallbackStatus(`Unable to deliver callback: ${error.message}`, true);
    }
  }

  function hideOverlay() {
    if (overlay) {
      overlay.hidden = true;
    }
  }

  function ensureOverlay() {
    if (overlay) {
      return;
    }

    const style = document.createElement("style");
    style.textContent = `
      #grotto-claude-open-overlay {
        position: fixed;
        inset: 0;
        z-index: 2147483647;
        display: grid;
        place-items: center;
        padding: 24px;
        background: rgba(3, 5, 8, 0.68);
        backdrop-filter: blur(6px);
        font-family: system-ui, sans-serif;
      }
      #grotto-claude-open-overlay[hidden] { display: none; }
      #grotto-claude-open-card {
        width: min(620px, 100%);
        max-height: calc(100vh - 48px);
        overflow: auto;
        padding: 24px;
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 16px;
        background: #171512;
        color: #f6f3ee;
        box-shadow: 0 18px 70px rgba(0, 0, 0, 0.5);
      }
      #grotto-claude-open-card h2 {
        margin: 0 0 10px;
        font-size: 22px;
      }
      #grotto-claude-open-card p {
        margin: 0 0 16px;
        color: #cdc6bc;
        line-height: 1.45;
      }
      #grotto-claude-open-host {
        display: block;
        margin: 12px 0 20px;
        padding: 10px 12px;
        border-radius: 8px;
        background: #25211c;
        color: #f6f3ee;
        overflow-wrap: anywhere;
        font-family: ui-monospace, monospace;
        font-size: 13px;
      }
      #grotto-claude-open-actions,
      #grotto-claude-callback-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }
      #grotto-claude-open-actions a,
      #grotto-claude-open-actions button,
      #grotto-claude-callback-actions button {
        box-sizing: border-box;
        min-height: 42px;
        padding: 10px 16px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.18);
        font: inherit;
        font-weight: 650;
        cursor: pointer;
        text-decoration: none;
      }
      #grotto-claude-open-link,
      #grotto-claude-send-callback {
        background: #f2eee8;
        color: #171512;
      }
      #grotto-claude-copy,
      #grotto-claude-dismiss,
      #grotto-claude-paste-callback {
        background: #25211c;
        color: #f6f3ee;
      }
      #grotto-claude-callback-section {
        margin-top: 22px;
        padding-top: 20px;
        border-top: 1px solid rgba(255, 255, 255, 0.14);
      }
      #grotto-claude-callback-section h3 {
        margin: 0 0 8px;
        font-size: 17px;
      }
      #grotto-claude-callback-input {
        box-sizing: border-box;
        width: 100%;
        min-height: 84px;
        margin: 0 0 10px;
        padding: 10px 12px;
        resize: vertical;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 8px;
        background: #0f0e0c;
        color: #f6f3ee;
        font: 13px/1.4 ui-monospace, monospace;
      }
      #grotto-claude-callback-status {
        display: block;
        min-height: 20px;
        margin-top: 10px;
        color: #b8d9b4;
        font-size: 13px;
      }
      #grotto-claude-callback-status[data-error="true"] {
        color: #ffb4ab;
      }
    `;
    document.head.appendChild(style);

    overlay = document.createElement("div");
    overlay.id = "grotto-claude-open-overlay";
    overlay.hidden = true;
    overlay.innerHTML = `
      <section id="grotto-claude-open-card" role="dialog" aria-modal="true" aria-labelledby="grotto-claude-open-title">
        <h2 id="grotto-claude-open-title">Continue Claude sign-in</h2>
        <p>Claude Desktop needs to open a secure page in the browser you are using for this Selkies session.</p>
        <span id="grotto-claude-open-host"></span>
        <div id="grotto-claude-open-actions">
          <a id="grotto-claude-open-link" target="_blank" rel="noopener noreferrer">Open sign-in page</a>
          <button id="grotto-claude-copy" type="button">Copy sign-in link</button>
          <button id="grotto-claude-dismiss" type="button">Dismiss</button>
        </div>
        <section id="grotto-claude-callback-section">
          <h3>Return authentication to remote Claude</h3>
          <p>After signing in, cancel the browser's attempt to open Claude on this device. Copy the link address from the <strong>Open Claude</strong> button, return to this Selkies tab, and paste the resulting <code>claude://</code> link below.</p>
          <textarea id="grotto-claude-callback-input" spellcheck="false" autocomplete="off" placeholder="claude://…"></textarea>
          <div id="grotto-claude-callback-actions">
            <button id="grotto-claude-paste-callback" type="button">Paste callback</button>
            <button id="grotto-claude-send-callback" type="button">Send to remote Claude</button>
          </div>
          <span id="grotto-claude-callback-status" aria-live="polite"></span>
        </section>
      </section>
    `;
    document.body.appendChild(overlay);

    link = overlay.querySelector("#grotto-claude-open-link");
    hostname = overlay.querySelector("#grotto-claude-open-host");
    callbackInput = overlay.querySelector("#grotto-claude-callback-input");
    callbackStatus = overlay.querySelector("#grotto-claude-callback-status");
    overlay.querySelector("#grotto-claude-copy").addEventListener("click", copyCurrentUrl);
    overlay.querySelector("#grotto-claude-dismiss").addEventListener("click", hideOverlay);
    overlay.querySelector("#grotto-claude-paste-callback").addEventListener("click", pasteCallback);
    overlay.querySelector("#grotto-claude-send-callback").addEventListener("click", sendCallback);
    link.addEventListener("click", () => {
      setCallbackStatus("Complete sign-in in the new tab, then copy its Open Claude link back here.");
    });
  }

  function showEvent(event) {
    ensureOverlay();
    currentUrl = event.url;
    const parsed = new URL(currentUrl);
    link.href = currentUrl;
    hostname.textContent = parsed.hostname;
    lastEventId = event.id;
    sessionStorage.setItem("grottoClaudeOpenEventId", lastEventId);
    overlay.hidden = false;
    link.focus();
  }

  async function poll() {
    try {
      const requestUrl = new URL(eventUrl);
      requestUrl.searchParams.set("_", Date.now().toString());
      const response = await fetch(requestUrl, {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!response.ok) {
        return;
      }
      const event = await response.json();
      if (isSafeEvent(event)) {
        showEvent(event);
      }
    } catch (_error) {
      // Dashboard startup and concurrent file writes can briefly produce 404 or
      // incomplete JSON. The next poll retries without disrupting the session.
    }
  }

  window.setInterval(poll, pollIntervalMs);
  poll();
})();
