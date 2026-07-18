#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  descriptors,
  applyGrottoRemoveNewWindowMenuPatch,
} = require("./patch.js");

function applyTwice(patch, source) {
  const patched = patch(source);
  assert.equal(patch(patched), patched);
  return patched;
}

function menuSource() {
  return [
    "let Rt=It.getMenuItemById(n.Bo.file)?.submenu;",
    "if(Rt){let e=0;",
    "l.multiWindow&&Rt.insert(e++,new c.MenuItem(I)),",
    "Rt.insert(e++,new c.MenuItem(N)),",
    "Rt.insert(e++,new c.MenuItem(F))}",
  ].join("");
}

test("omits only the first multi-window File menu item on Linux", () => {
  const patched = applyTwice(
    applyGrottoRemoveNewWindowMenuPatch,
    menuSource(),
  );

  assert.match(
    patched,
    /process\.platform!==`linux`&&l\.multiWindow&&Rt\.insert\(e\+\+,new c\.MenuItem\(I\)\)/,
  );
  assert.match(patched, /Rt\.insert\(e\+\+,new c\.MenuItem\(N\)\)/);
  assert.match(patched, /Rt\.insert\(e\+\+,new c\.MenuItem\(F\)\)/);
});

test("combined feature removes Linux overlay controls and preserves menus", () => {
  const source = [
    "case`quickChat`:case`primary`:return n===`darwin`?{titleBarStyle:`hiddenInset`}:n===`win32`||n===`linux`?{titleBarStyle:`hidden`,titleBarOverlay:n===`linux`?codexLinuxTitleBarOverlay(r):j9(r),...e===`quickChat`?{resizable:!0}:{}}:{titleBarStyle:`default`,...e===`quickChat`?{resizable:!0}:{}};",
    "setWindowZoom(e,t){let n=c.BrowserWindow.fromWebContents(e),r=n&&this.windowAppearances.get(n.id);n==null||r!==`primary`&&r!==`quickChat`||(process.platform===`darwin`?n.setWindowButtonPosition(A9(t)):(process.platform===`win32`||process.platform===`linux`)&&(this.windowZooms.set(n.id,t),n.setTitleBarOverlay(process.platform===`linux`?codexLinuxTitleBarOverlay(t):j9(t))))}",
    "installApplicationMenuTitleBarOverlaySync(e,t){if(process.platform!==`win32`&&process.platform!==`linux`||t!==`primary`&&t!==`quickChat`)return;let n=()=>{e.isDestroyed()||e.setTitleBarOverlay(process.platform===`linux`?codexLinuxTitleBarOverlay(this.windowZooms.get(e.id)):j9(this.windowZooms.get(e.id)))};return c.nativeTheme.on(`updated`,n),n(),()=>{c.nativeTheme.off(`updated`,n)}}",
    menuSource(),
  ].join("");

  const patched = descriptors.reduce(
    (current, descriptor) => descriptor.apply(current),
    source,
  );

  assert.match(
    patched,
    /n===`linux`\?\{titleBarStyle:`hidden`,\.\.\.e===`quickChat`\?\{resizable:!0\}:\{\}\}/,
  );
  assert.doesNotMatch(
    patched,
    /n===`linux`\?\{titleBarStyle:`hidden`,titleBarOverlay:/,
  );
  assert.match(patched, /getMenuItemById\(n\.Bo\.file\)\?\.submenu/);
  assert.match(
    patched,
    /process\.platform!==`linux`&&l\.multiWindow&&Rt\.insert/,
  );
});

test("feature descriptors fail builds on upstream drift", () => {
  assert.deepEqual(
    descriptors.map(({ id, ciPolicy }) => ({ id, ciPolicy })),
    [
      {
        id: "frameless-linux-window-controls",
        ciPolicy: "required-upstream",
      },
      {
        id: "linux-single-window-menu",
        ciPolicy: "required-upstream",
      },
    ],
  );
});
