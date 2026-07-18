"use strict";

const {
  applyFramelessTitlebarMainPatch,
} = require("../../frameless-titlebar/patch.js");

const NEW_WINDOW_MENU_INSERTION = String.raw`([A-Za-z_$][\w$]*)\.multiWindow&&([A-Za-z_$][\w$]*)\.insert\(([A-Za-z_$][\w$]*)\+\+,new ([A-Za-z_$][\w$]*)\.MenuItem\(([A-Za-z_$][\w$]*)\)\),(?=\2\.insert\(\3\+\+,new \4\.MenuItem\()`;
const LINUX_GUARD = "process.platform!==`linux`&&";

function applyGrottoRemoveNewWindowMenuPatch(currentSource) {
  const guardedInsertion = new RegExp(
    `process\\.platform!==\`linux\`&&${NEW_WINDOW_MENU_INSERTION}`,
  );
  if (guardedInsertion.test(currentSource)) {
    return currentSource;
  }

  const matches = Array.from(
    currentSource.matchAll(new RegExp(NEW_WINDOW_MENU_INSERTION, "g")),
  );
  if (matches.length !== 1) {
    console.warn(
      `WARN: Expected one File -> New Window menu insertion, found ${matches.length} - skipping Grotto single-window menu patch`,
    );
    return currentSource;
  }

  const [match] = matches;
  return (
    currentSource.slice(0, match.index) +
    LINUX_GUARD +
    match[0] +
    currentSource.slice(match.index + match[0].length)
  );
}

const descriptors = [
  {
    id: "frameless-linux-window-controls",
    phase: "main-bundle",
    order: 20_720,
    ciPolicy: "required-upstream",
    apply: applyFramelessTitlebarMainPatch,
  },
  {
    id: "linux-single-window-menu",
    phase: "main-bundle",
    order: 20_730,
    ciPolicy: "required-upstream",
    apply: applyGrottoRemoveNewWindowMenuPatch,
  },
];

module.exports = {
  descriptors,
  applyGrottoRemoveNewWindowMenuPatch,
};
