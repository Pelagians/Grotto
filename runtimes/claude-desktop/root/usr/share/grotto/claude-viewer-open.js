(() => {
  "use strict";

  const scriptUrl = document.currentScript?.src || window.location.href;
  const eventUrl = new URL("grotto-claude-open-url.json", scriptUrl);
  const pollIntervalMs = 750;
  const maxEventAgeMs = 15 * 60 * 1000;

  let lastEventId = sessionStorage.getItem("grottoClaudeOpenEventId") || "";
  let currentUrl = "";
  let overlay;
  let link;
  let hostname;

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
        width: min(520px, 100%);
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
      #grotto-claude-open-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }
      #grotto-claude-open-actions a,
      #grotto-claude-open-actions button {
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
      #grotto-claude-open-link {
        background: #f2eee8;
        color: #171512;
      }
      #grotto-claude-copy,
      #grotto-claude-dismiss {
        background: #25211c;
        color: #f6f3ee;
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
          <button id="grotto-claude-copy" type="button">Copy link</button>
          <button id="grotto-claude-dismiss" type="button">Dismiss</button>
        </div>
      </section>
    `;
    document.body.appendChild(overlay);

    link = overlay.querySelector("#grotto-claude-open-link");
    hostname = overlay.querySelector("#grotto-claude-open-host");
    overlay.querySelector("#grotto-claude-copy").addEventListener("click", copyCurrentUrl);
    overlay.querySelector("#grotto-claude-dismiss").addEventListener("click", hideOverlay);
    link.addEventListener("click", () => {
      hideOverlay();
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
