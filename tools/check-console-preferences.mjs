#!/usr/bin/env node
// Isolated preference fixtures: no browser, service, real storage, or network.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8").replace(/\r\n?/g, "\n");
function extract(name) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Missing ${name}`);
  const next = source.slice(start + 1).search(/\n(?:async )?function /);
  return source.slice(start, next < 0 ? undefined : start + 1 + next);
}
function declaration(name) {
  const line = source.match(new RegExp(`^(?:let|const) ${name} = .+;$`, "m"))?.[0];
  assert.ok(line, `Missing initial preference ${name}`);
  return line;
}
const preferences = ["selectedWallpaperPath", "selectedTrackPath", "language", "theme", "musicLyricsPanelHeight", "playbackMode", "downloadIntakeEnabled", "tutorialMode", "activeConsoleView", "activeBlenderView", "selectedDownloadMapPluginId", "selectedUpdateProduct"];
const keyNames = ["selectedWallpaper", "selectedTrack", "language", "theme", "lyricsHeight", "playbackMode", "downloadIntake", "tutorialMode", "consoleView", "blenderView", "downloadMapPlugin", "updateProduct", "volume", "lastModule", "publicLayoutInitialized", "moduleOrder", "moduleArchive", "moduleDeepArchive", "moduleDeleted"];
const storageKeys = Object.fromEntries(keyNames.map(key => [key, key]));
const normalizers = ["readConsolePreference", "normalizeUiLanguage", "normalizeTheme", "normalizePlaybackMode", "normalizeConsoleWorkspaceView", "normalizeBlenderWorkspaceView"];
const bootstrap = `${normalizers.map(extract).join("\n")}\n${preferences.map(declaration).join("\n")}\n({ ${preferences.join(", ")} })`;
let checks = 0;
function test(name, action) { action(); checks++; console.log(`PASS ${name}`); }

test("unavailable preference storage falls back without throwing or writing", () => {
  for (const mode of ["method", "getter"]) {
    const context = { storageKeys, playbackModes: ["repeatAll", "repeatOne", "playOnce"], requestedConsoleView: null };
    if (mode === "method") context.localStorage = { getItem() { throw new Error("SecurityError"); } };
    else Object.defineProperty(context, "localStorage", { get() { throw new Error("SecurityError"); } });
    const result = runInNewContext(bootstrap, context);
    assert.deepEqual(JSON.parse(JSON.stringify(result)), {
      selectedWallpaperPath: "", selectedTrackPath: "", language: "zh", theme: "light",
      musicLyricsPanelHeight: 0, playbackMode: "repeatAll", downloadIntakeEnabled: false,
      tutorialMode: false, activeConsoleView: "work", activeBlenderView: "character",
      selectedDownloadMapPluginId: "character-designer", selectedUpdateProduct: "console"
    });
  }
});

test("saved preferences are used and explicit Console links keep precedence", () => {
  const stored = new Map([["language", "en"], ["theme", "dark"], ["consoleView", "document"], ["selectedTrack", "saved.mp3"]]);
  const context = { storageKeys, playbackModes: ["repeatAll", "repeatOne", "playOnce"], requestedConsoleView: "transfer", localStorage: { getItem: key => stored.get(key) ?? null } };
  const result = runInNewContext(bootstrap, context);
  assert.equal(result.language, "en"); assert.equal(result.theme, "dark");
  assert.equal(result.activeConsoleView, "transfer"); assert.equal(result.selectedTrackPath, "saved.mp3");
  assert.deepEqual([...stored], [["language", "en"], ["theme", "dark"], ["consoleView", "document"], ["selectedTrack", "saved.mp3"]]);
});

test("theme and language still apply when saving the preference fails", () => {
  const calls = [], listeners = new Map();
  const context = {
    theme: "light", language: "zh", storageKeys,
    els: { languageToggle: { addEventListener: (name, action) => listeners.set(name, action) } },
    localStorage: { setItem() { throw new Error("QuotaExceededError"); } },
    applyTheme() { calls.push(["theme", context.theme]); },
    applyLanguage() { calls.push(["language", context.language]); },
    recordThemeChange(before, after) { calls.push(["history", before, after]); }
  };
  const start = source.indexOf('if (els.languageToggle) els.languageToggle.addEventListener("click",');
  const end = source.indexOf('\nif (els.themeToggle)', start);
  assert.ok(start >= 0 && end > start);
  runInNewContext(`${extract("normalizeTheme")}\n${extract("setTheme")}\n${source.slice(start, end)}`, context);
  context.setTheme("dark"); listeners.get("click")();
  assert.deepEqual(calls, [["theme", "dark"], ["history", "light", "dark"], ["language", "en"]]);
  context.setTheme("light", { record: false });
  assert.equal(context.theme, "light"); assert.equal(calls.length, 4);
});

test("missing or unreadable volume uses the default and explicit mute is retained", () => {
  const code = `${extract("readConsolePreference")}\n${["savedVolumePreference", "savedVolume", "initialVolume"].map(declaration).join("\n")}\ninitialVolume`;
  for (const [stored, expected] of [[null, 1 / 3], ["bad", 1 / 3], ["0", 0], ["0.8", 0.8], ["2", 1], ["-1", 0]]) {
    assert.equal(runInNewContext(code, { storageKeys, localStorage: { getItem: () => stored } }), expected);
  }
  assert.equal(runInNewContext(code, { storageKeys, localStorage: { getItem() { throw new Error("SecurityError"); } } }), 1 / 3);
});

test("navigation continues when its local preference is unavailable", () => {
  for (const failure of ["read", "write"]) {
    const calls = [];
    const context = {
      storageKeys, isModuleId: id => ["workspace", "music"].includes(id), persistConsoleState: id => calls.push(id),
      localStorage: { getItem() { if (failure === "read") throw new Error("SecurityError"); return "music"; }, setItem() { throw new Error("QuotaExceededError"); } }
    };
    runInNewContext(["readConsolePreference", "lastModuleId", "rememberActiveModule"].map(extract).join("\n"), context);
    assert.equal(context.lastModuleId(), failure === "read" ? "" : "music");
    context.rememberActiveModule("workspace");
    assert.deepEqual(calls, ["workspace"]);
  }
});

test("public layout storage failures do not interrupt initialization or mark completion", () => {
  for (const failure of ["read", "write"]) {
    const writes = [];
    const context = {
      storageKeys, consoleEdition: "public", releaseDefaults: {}, deviceLayoutDefaults: {},
      editionModuleSet: () => new Set(["workspace", "music"]), availableModules: () => [{ id: "workspace" }, { id: "music" }],
      isModuleId: id => ["workspace", "music"].includes(id),
      localStorage: { getItem() { if (failure === "read") throw new Error("SecurityError"); return null; }, setItem(key) { writes.push(key); throw new Error("QuotaExceededError"); } }
    };
    runInNewContext(["readConsolePreference", "ensureEditionModuleLayout"].map(extract).join("\n"), context);
    assert.doesNotThrow(() => context.ensureEditionModuleLayout());
    assert(!writes.includes(storageKeys.publicLayoutInitialized));
  }
});

console.log(`Console preferences: ${checks} isolated checks passed.`);
