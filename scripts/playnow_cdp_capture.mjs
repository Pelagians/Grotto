#!/usr/bin/env node

import { writeFile } from "node:fs/promises";

const arguments_ = new Map(
  process.argv.slice(2).map((value) => {
    const separator = value.indexOf("=");
    return separator === -1
      ? [value, true]
      : [value.slice(0, separator), value.slice(separator + 1)];
  }),
);
const endpoint = String(arguments_.get("--cdp") || "http://127.0.0.1:9222").replace(/\/$/, "");
const pageUrl = new URL(String(arguments_.get("--url") || ""));
const outputPath = String(arguments_.get("--output") || "");
const eventId = String(arguments_.get("--event-id") || "");

function isAllowedPlayNowUrl(value) {
  return value.protocol === "https:" &&
    (value.hostname === "playnow.com" || value.hostname.endsWith(".playnow.com")) &&
    value.pathname.startsWith("/sports/sports/event/") &&
    !value.search && !value.hash;
}

if (!isAllowedPlayNowUrl(pageUrl) || !outputPath || !eventId) {
  throw new Error("INVALID_CAPTURE_ARGUMENTS");
}

const targets = await fetch(`${endpoint}/json/list`).then((response) => {
  if (!response.ok) throw new Error(`ATTACHMENT_FAILED:${response.status}`);
  return response.json();
});
const target = targets.find((item) => {
  if (item.type !== "page") return false;
  try {
    const value = new URL(item.url);
    return value.protocol === "https:" &&
      (value.hostname === "playnow.com" || value.hostname.endsWith(".playnow.com"));
  } catch {
    return false;
  }
});
if (!target?.webSocketDebuggerUrl) throw new Error("PLAYNOW_ORIGIN_NOT_OPEN");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let commandId = 0;
function command(method, params = {}, timeoutMs = 10000) {
  commandId += 1;
  const id = commandId;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      socket.removeEventListener("message", onMessage);
      reject(new Error(`ATTACHMENT_FAILED:${method}`));
    }, timeoutMs);
    function onMessage(event) {
      const message = JSON.parse(String(event.data));
      if (message.id !== id) return;
      clearTimeout(timeout);
      socket.removeEventListener("message", onMessage);
      if (message.error) reject(new Error(`ATTACHMENT_FAILED:${method}`));
      else resolve(message.result);
    }
    socket.addEventListener("message", onMessage);
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const result = await command("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (result.exceptionDetails) throw new Error("ATTACHMENT_FAILED:evaluation");
  return result.result.value;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

await command("Page.navigate", { url: pageUrl.href });
let ready = false;
for (let attempt = 0; attempt < 30; attempt += 1) {
  await delay(500);
  ready = Boolean(await evaluate(`Boolean(
    document.querySelector("main [role='tab']") &&
    document.querySelector("main [class*='eventMarketWrapper']")
  )`));
  if (ready) break;
}
if (!ready) {
  socket.close();
  throw new Error("PLAYNOW_EVENT_NOT_READY");
}
const loaded = await evaluate(`(() => {
  const current = new URL(location.href);
  return current.origin + current.pathname;
})()`);
if (loaded !== pageUrl.origin + pageUrl.pathname) {
  socket.close();
  throw new Error("NAVIGATION_TARGET_MISMATCH");
}

const tabs = ["Popular", "Passing", "Rushing", "Receiving", "Quarters & Halves", "Team"];
const observations = [];
for (const tab of tabs) {
  const clickResult = await evaluate(`(() => {
    const label = ${JSON.stringify(tab)};
    const candidates = Array.from(document.querySelectorAll("main [role='tab']"))
      .filter((node) => String(node.innerText || "").trim() === label);
    const target = candidates.find((node) => node.offsetParent !== null) || candidates[0];
    if (!target) return "TAB_NOT_FOUND";
    target.click();
    return "CLICKED";
  })()`);
  if (clickResult === "CLICKED") {
    for (let attempt = 0; attempt < 10; attempt += 1) {
      await delay(500);
      const state = await evaluate(`(() => {
        const active = Array.from(document.querySelectorAll("main [role='tab']"))
          .filter((node) => String(node.className || "").includes("Active"))
          .map((node) => String(node.innerText || "").trim());
        return {
          pending: active.includes("Pending"),
          markets: document.querySelectorAll("main [class*='eventMarketWrapper']").length
        };
      })()`);
      if (!state.pending && state.markets > 0) break;
    }
  }
  const captured = JSON.parse(await evaluate(`JSON.stringify({
    observed_at: new Date().toISOString(),
    title: document.title,
    url: location.origin + location.pathname,
    tab_status: ${JSON.stringify(clickResult)},
    active_tabs: Array.from(document.querySelectorAll("main [role='tab']"))
      .filter((node) => String(node.className || "").includes("Active"))
      .map((node) => String(node.innerText || "").trim())
      .filter((value, index, values) => value && values.indexOf(value) === index),
    markets: Array.from(document.querySelectorAll("main [class*='eventMarketWrapper']"))
      .slice(0, 250)
      .map((node) => ({
        text: String(node.innerText || "").trim().slice(0, 5000),
        selections: Array.from(node.querySelectorAll("button"))
          .filter((button) => String(button.innerText || "").trim() !== "Show More")
          .map((button) => ({
            text: String(button.innerText || "").trim().slice(0, 500),
            disabled: Boolean(button.disabled)
          }))
      }))
      .filter((market) => market.text)
  })`));
  observations.push({ requested_tab: tab, ...captured });
}

socket.close();
const artifact = {
  schema_version: "playnow-cdp-observation-v1",
  event_id: eventId,
  requested_url: pageUrl.origin + pageUrl.pathname,
  capture_started_at: observations[0]?.observed_at || new Date().toISOString(),
  capture_finished_at: observations.at(-1)?.observed_at || new Date().toISOString(),
  account_data_captured: false,
  wagering_interactions: false,
  observations,
};
await writeFile(outputPath, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");
console.log(JSON.stringify({
  event_id: eventId,
  observations: observations.length,
  market_counts: observations.map((item) => [item.requested_tab, item.markets.length]),
  capture_started_at: artifact.capture_started_at,
  capture_finished_at: artifact.capture_finished_at,
}));
