// Actual Console handlers and event registrations in a tiny bubbling DOM fixture.
// No browser, playback, network requests, or writes to user data.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const appPath = process.argv[2] || fileURLToPath(new URL("../app.js", import.meta.url));
const source = readFileSync(appPath, "utf8");
const functionSource = name => {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Missing actual function ${name}`);
  const tail = source.slice(start), next = /\n(?:async )?function \w+\(/.exec(tail.slice(1));
  return next ? tail.slice(0, next.index + 1) : tail;
};
const registration = type => {
  const lines = source.split(/\r?\n/).filter(line => line.includes(`addEventListener("${type}", handleNowPlayingLyrics`));
  assert.equal(lines.length, 1, `Exactly one ${type} handler registration prevents double toggles`);
  return lines[0];
};
function node(tag = "div", parent = null, role = "") {
  const listeners = new Map();
  return { tag, parent, role, listeners,
    addEventListener(type, fn) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(fn); },
    closest() {
      for (let current = this; current; current = current.parent) {
        if (["button", "a", "input", "select", "textarea", "summary"].includes(current.tag) || current.role === "button") return current;
      }
      return null;
    },
    dispatch(type, patch = {}) {
      const event = { button: type === "contextmenu" ? 2 : 0, detail: 1, target: this, shiftKey: false,
        defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...patch };
      for (let current = this; current; current = current.parent) {
        for (const callback of current.listeners.get(type) || []) callback(event);
      }
      return event;
    }
  };
}
const card = node(), art = node("button", card), cover = node("img", art);
const body = node("div", card), title = node("strong", body), meta = node("p", body);
let toggles = 0, languages = [], options = [{ code: "en" }, { code: "zh" }];
const runtime = { hasMusic: true, els: { nowPlayingCard: card, nowPlayingArt: art },
  toggleNowPlayingLyrics() { toggles += 1; }, selectedTrack: () => ({}),
  musicLyricsLanguageOptions: () => options, cycleNowPlayingLyricsLanguage(direction) { languages.push(direction); } };
runInNewContext([functionSource("handleNowPlayingLyricsClick"), functionSource("handleNowPlayingLyricsContextMenu"),
  registration("click"), registration("contextmenu")].join("\n"), runtime);
for (const target of [art, cover, body, title, meta, card]) {
  const before = toggles; target.dispatch("click");
  assert.equal(toggles, before + 1, `${target.tag} opens/closes lyrics exactly once`);
  for (const shiftKey of [false, true]) {
    const count = languages.length, event = target.dispatch("contextmenu", { shiftKey });
    assert.equal(languages.length, count + 1); assert.equal(languages.at(-1), shiftKey ? -1 : 1);
    assert.equal(event.defaultPrevented, true);
  }
}
for (const target of [node("button", card), node("input", card), node("a", body), node("div", card, "button")]) {
  const before = toggles; target.dispatch("click"); assert.equal(toggles, before, "nested controls keep their own action");
}
for (const patch of [{ button: 2 }, { detail: 2 }]) {
  const before = toggles; card.dispatch("click", patch); assert.equal(toggles, before);
}
const outside = node("button"), before = toggles; outside.dispatch("click"); assert.equal(toggles, before);
for (options of [[], [{ code: "en" }]]) {
  const count = languages.length, event = card.dispatch("contextmenu");
  assert.equal(languages.length, count); assert.equal(event.defaultPrevented, false);
}
// Standalone layouts can still register the artwork when no enclosing card exists.
const isolatedArt = node("button"); runtime.els = { nowPlayingCard: null, nowPlayingArt: isolatedArt };
runInNewContext(registration("click"), runtime);
isolatedArt.dispatch("click"); assert.equal(toggles, before + 1);
console.log(JSON.stringify({ passed: true, source: appPath, targets: 6,
  scope: "Actual click/contextmenu handlers and bubbling registrations; synthetic DOM only" }));
