#!/usr/bin/env node
// Read-only desktop policy checks. Uses isolated DOM fixtures, never the user's browser.
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const legacyIds = ["consoleDeveloperModeTop", "consoleDeveloperSettingsTop", "consoleUpdateTop"];
const managementIds = ["consoleDeveloperTools", "consoleUpdateAuto", "consoleUpdateRefresh", "consoleUpdateInstall", "consoleUninstall", "updateProductConsole", "updateProductWorld"];
const requiredPages = ["index.html", "music.html", "workspace.html", "reader.html", "resources.html", "subscription.html"];
const headerButtonIds = new Set(["languageToggle", "themeToggle", "moduleArchiveDrop"]);
const moduleIds = new Set(["manager", "workspace", "blender", "unity", "steamwork", "randomrealm", "music", "wallpaper"]);
const voidTags = new Set("area base br col embed hr img input link meta param source track wbr".split(" "));
let checks = 0;
function test(name, run) { run(); checks++; console.log(`PASS ${name}`); }

class Element {
  constructor(tag = "div", attributes = {}) {
    this.nodeType = 1; this.tagName = tag.toUpperCase(); this.attributes = { ...attributes };
    this.children = []; this.parentElement = null; this.hidden = "hidden" in attributes;
    this.disabled = "disabled" in attributes; this.checked = "checked" in attributes;
    this.textContent = ""; this.dataset = {};
    this.classList = { toggle() {} };
  }
  get id() { return this.attributes.id || ""; }
  set id(value) { this.attributes.id = String(value); }
  get className() { return this.attributes.class || ""; }
  append(...nodes) { for (const node of nodes) { node.remove(); node.parentElement = this; this.children.push(node); } }
  remove() {
    if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(node => node !== this);
    this.parentElement = null;
  }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  matches(selector) {
    return selector.split(",").some(part => {
      const value = part.trim();
      if (value.startsWith("#")) return this.id === value.slice(1);
      if (value.startsWith(".")) return this.className.split(/\s+/).includes(value.slice(1));
      const attr = value.match(/^\[([^=\]]+)(?:=["']([^"']*)["'])?\]$/);
      if (attr) return attr[1] in this.attributes && (attr[2] === undefined || this.attributes[attr[1]] === attr[2]);
      return this.tagName.toLowerCase() === value.toLowerCase();
    });
  }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
}

function parseDocument(html) {
  const document = new Element("document"); document.nodeType = 9;
  const stack = [document];
  // Scripts/styles are raw text, comments are inert. Quoted attributes may contain >.
  const tags = /<!--[\s\S]*?-->|<(script|style)\b(?:"[^"]*"|'[^']*'|[^'">])*?>[\s\S]*?<\/\1\s*>|<\/?[a-z][a-z0-9:-]*\b(?:"[^"]*"|'[^']*'|[^'">])*?>/gi;
  for (const match of html.matchAll(tags)) {
    const token = match[0];
    if (token.startsWith("<!--") || match[1]) continue;
    const tag = token.match(/^<\/?([a-z][a-z0-9:-]*)/i)[1].toLowerCase();
    if (token.startsWith("</")) {
      const index = stack.findLastIndex(node => node.tagName.toLowerCase() === tag);
      if (index > 0) stack.length = index;
      continue;
    }
    const attributes = {};
    const attrSource = token.slice(token.indexOf(tag) + tag.length, -1);
    for (const attr of attrSource.matchAll(/([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
      attributes[attr[1].toLowerCase()] = attr[2] ?? attr[3] ?? attr[4] ?? "";
    }
    const node = new Element(tag, attributes); stack.at(-1).append(node);
    if (!voidTags.has(tag) && !token.endsWith("/>")) stack.push(node);
  }
  document.body = document.querySelector("body");
  document.documentElement = document.querySelector("html");
  assert.ok(document.body, "desktop HTML requires a body");
  document.getElementById = id => document.querySelector(`#${id}`);
  return document;
}

function checkMarkup(name, html) {
  const document = parseDocument(html);
  checkHeaderActions(name, document);
  for (const id of legacyIds) assert.equal(document.querySelectorAll(`#${id}`).length, 0, `${name}: legacy ${id} must be absent, including hidden menus`);
  const managed = document.querySelectorAll(`[data-console-management], ${managementIds.map(id => `#${id}`).join(", ")}`);
  for (const node of managed) {
    assert.ok(node.closest('[data-module-panel="workspace"]'), `${name}: ${node.id || "management section"} belongs inside Console`);
    assert.equal(node.closest("header, .topbar, .top-actions"), null, `${name}: management must not be in the desktop header`);
  }
  const entry = document.getElementById("consoleDeveloperTools");
  if (entry) {
    assert.equal(document.querySelectorAll("#consoleDeveloperTools").length, 1, `${name}: one developer entry`);
    assert.ok(entry.closest(".work-view-more"), `${name}: developer entry stays in the Console more menu`);
    assert.ok(entry.hidden, `${name}: server capability reveals developer tools`);
    assert.ok("data-console-management" in entry.attributes, `${name}: developer entry is covered by management policy`);
  }
  return document;
}

function checkHeaderActions(name, document) {
  for (const header of document.querySelectorAll(".topbar, .top-actions")) {
    for (const node of header.querySelectorAll('button, a, input, select, textarea, summary, [role="button"], [role="link"], [tabindex]')) {
      const moduleId = node.attributes["data-module-id"] || node.dataset.moduleId;
      const moduleLink = node.tagName === "A" && node.closest("[data-module-nav]") && node.matches(".module-link") && moduleIds.has(moduleId);
      const archivedModule = node.tagName === "BUTTON" && node.closest("#moduleArchiveList") && node.matches(".archive-item") && moduleIds.has(moduleId);
      const statusButton = node.tagName === "BUTTON" && headerButtonIds.has(node.id);
      assert.ok(statusButton || moduleLink || archivedModule, `${name}: unexpected desktop header control ${node.id || node.tagName}; settings and updates belong inside Console`);
    }
  }
}

function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}(`); assert.ok(start >= 0, `missing function ${name}`);
  const open = source.indexOf("{", start); let depth = 0, quote = "", comment = "";
  for (let index = open; index < source.length; index++) {
    const ch = source[index], next = source[index + 1];
    if (comment === "line") { if (ch === "\n") comment = ""; continue; }
    if (comment === "block") { if (ch === "*" && next === "/") { comment = ""; index++; } continue; }
    if (quote) { if (ch === "\\") index++; else if (ch === quote) quote = ""; continue; }
    if (ch === "/" && next === "/") { comment = "line"; index++; continue; }
    if (ch === "/" && next === "*") { comment = "block"; index++; continue; }
    if (ch === '"' || ch === "'" || ch === "`") { quote = ch; continue; }
    if (ch === "{") depth++;
    if (ch === "}" && --depth === 0) return source.slice(start, index + 1);
  }
  throw new Error(`unterminated function ${name}`);
}

function policyHarness(source, html) {
  const document = parseDocument(html), events = new Map(), observers = [];
  class Observer {
    constructor(callback) { this.callback = callback; this.observations = []; this.connected = false; observers.push(this); }
    observe(target, options) { this.target = target; this.options = options; this.observations.push({ target, options }); this.connected = true; }
    disconnect() { this.connected = false; }
    deliver(records) { if (this.connected) this.callback(records); }
  }
  const context = { document, MutationObserver: Observer, window: { addEventListener(name, callback) { if (!events.has(name)) events.set(name, []); events.get(name).push(callback); } }, fetch() { throw new Error("Policy must not send requests"); }, localStorage: { setItem() { throw new Error("Policy must not change preferences"); } } };
  runInNewContext(["enforceDesktopConsoleControls", "startDesktopConsoleControlPolicy"].map(name => extractFunction(source, name)).join("\n"), context);
  const add = (id, parent = document.querySelector(".top-actions") || document.body, attributes = {}) => { const node = new Element("button", { ...attributes, id }); parent.append(node); return node; };
  const fire = name => { for (const callback of events.get(name) || []) callback(); };
  return { context, document, observers, add, fire };
}

function checkRuntime(name, source, pages) {
  test(`${name}: desktop policy starts before the first window session`, () => {
    assert.match(source, /^startDesktopConsoleControlPolicy\(\);/m);
    assert.ok(source.indexOf("\nstartDesktopConsoleControlPolicy();") < source.indexOf("\nstartConsoleWindowSession();"));
    assert.doesNotMatch(source, /els\.(?:consoleDeveloperModeTop|consoleDeveloperSettingsTop|consoleUpdateTop)|handleProductUpdateTop/);
    assert.doesNotMatch(source, /^\s*(?:consoleDeveloperModeTop|consoleDeveloperSettingsTop|consoleUpdateTop)\s*:/m);
  });
  test(`${name}: startup removes hidden, duplicate and nested stale controls on every entry page`, () => {
    for (const [page, html] of pages) {
      const h = policyHarness(source, html), inside = h.document.querySelector('[data-module-panel="workspace"]');
      const header = h.document.querySelector(".top-actions") || h.document.body;
      const more = new Element("details", { hidden: "" }); header.append(more);
      for (const id of legacyIds) { h.add(id, more, { hidden: "" }); h.add(id, header); if (inside) h.add(id, inside); }
      for (const id of managementIds) h.add(id, more);
      h.add("staleManagement", more, { "data-console-management": "" });
      const existing = inside ? managementIds.map(id => inside.querySelector(`#${id}`)).filter(Boolean) : [];
      h.context.startDesktopConsoleControlPolicy();
      for (const id of legacyIds) assert.equal(h.document.querySelectorAll(`#${id}`).length, 0, `${page}: ${id}`);
      for (const node of more.children) assert.fail(`${page}: outside management ${node.id} survived`);
      for (const node of existing) assert.ok(inside.contains(node), `${page}: preserve Console control ${node.id}`);
    }
  });
  test(`${name}: later DOM mutations and page restoration cannot resurrect header controls`, () => {
    const h = policyHarness(source, pages.get("index.html")); h.context.startDesktopConsoleControlPolicy();
    const observer = h.observers[0], inside = h.document.querySelector('[data-module-panel="workspace"]');
    assert.equal(h.observers.length, 1); assert.equal(observer.target, h.document.body);
    assert.ok(observer.options.childList && observer.options.subtree && observer.options.attributes);
    assert.ok(observer.options.attributeFilter.includes("id") && observer.options.attributeFilter.includes("data-console-management"));
    for (const id of [...legacyIds, ...managementIds]) {
      const node = h.add(id); observer.deliver([{ type: "childList", addedNodes: [node] }]);
      assert.equal(node.parentElement, null, `remove newly inserted ${id}`);
    }
    const fragment = new Element("section"), nested = h.add("consoleUpdateTop", fragment); h.document.body.append(fragment);
    observer.deliver([{ type: "childList", addedNodes: [{ nodeType: 3 }, fragment] }]); assert.equal(nested.parentElement, null);
    const renamed = h.add("ordinaryHeaderControl"); renamed.id = "consoleDeveloperSettingsTop";
    observer.deliver([{ type: "attributes", target: renamed }]); assert.equal(renamed.parentElement, null);
    const marked = h.add("newManagement"); marked.setAttribute("data-console-management", "");
    observer.deliver([{ type: "attributes", target: marked }]); assert.equal(marked.parentElement, null);
    const valid = h.add("validConsoleManagement", inside, { "data-console-management": "" });
    observer.deliver([{ type: "childList", addedNodes: [valid] }]); assert.ok(inside.contains(valid));
    const moved = h.document.getElementById("consoleDeveloperTools"); h.document.body.append(moved);
    observer.deliver([{ type: "childList", addedNodes: [moved] }]); assert.equal(moved.parentElement, null);
    h.fire("pagehide"); assert.equal(observer.connected, false);
    h.add("consoleUpdateTop"); h.fire("pageshow");
    assert.equal(h.document.getElementById("consoleUpdateTop"), null); assert.equal(observer.connected, true);
    assert.ok(inside.contains(valid));
  });
  test(`${name}: edition, language, Store and update states preserve Console controls and a clean header`, () => {
    const h = policyHarness(source, pages.get("index.html")), inside = h.document.querySelector('[data-module-panel="workspace"]');
    const ids = ["consoleUpdateStatus", "consoleUpdateCurrent", "consoleUpdateAuto", "consoleUpdateRefresh", "consoleUpdateInstall", "consoleUninstall", "consoleUpdateRelease", "consoleUpdateError", "updateProductConsole", "updateProductConsoleBadge", "updateProductWorld", "updateProductWorldBadge"];
    h.context.els = Object.fromEntries(ids.map(id => [id, h.document.getElementById(id)]));
    for (const id of ids) assert.ok(h.context.els[id], `Console control fixture ${id}`);
    Object.assign(h.context, { selectedUpdateProduct: "console", productUpdateBusy: false, updateProductIds: ["console", "world"], productUpdateStates: {}, text: (key, ...args) => [key, ...args].join(" "), storageKeys: { updateProduct: "fixture" }, localStorage: { setItem() {} } });
    runInNewContext(["selectedProductUpdateState", "storeProductUnavailable", "renderUpdateProductButton", "renderConsoleUpdate"].map(fn => extractFunction(source, fn)).join("\n"), h.context);
    const retained = managementIds.map(id => h.document.getElementById(id));
    for (const lang of ["zh-CN", "en"]) for (const edition of ["developer", "public", "lite"]) for (const store of [false, true]) for (const available of [false, true]) for (const busy of [false, true]) {
      h.document.documentElement.lang = lang; h.document.documentElement.dataset.edition = edition; inside.hidden = edition === "lite";
      h.context.storeManagedInstall = store; h.context.productUpdateBusy = busy;
      h.context.productUpdateStates = Object.fromEntries(["console", "world"].map(product => [product, { currentVersion: "1.0.89", latestVersion: "1.0.90", available, canInstall: !store, managedByStore: store, canUninstall: !store, autoCheck: true, releaseUrl: store ? "" : `https://fixture.test/${product}` }]));
      for (const product of ["console", "world"]) {
        h.context.selectedUpdateProduct = product; h.context.renderConsoleUpdate(); h.context.enforceDesktopConsoleControls();
        checkHeaderActions(`${name}: rendered ${edition}/${lang}/${store}`, h.document);
        for (const id of legacyIds) assert.equal(h.document.getElementById(id), null);
        for (const node of retained) assert.ok(inside.contains(node), `preserve ${node.id} in ${edition}/${lang}/${store}`);
        if (!store && available) { assert.equal(h.context.els.consoleUpdateInstall.hidden, false); assert.equal(h.context.els.consoleUpdateInstall.disabled, busy); }
      }
    }
  });
}

const desktopPages = readdirSync(projectRoot).filter(name => name.endsWith(".html") && name !== "mobile.html").sort();
for (const name of requiredPages) assert.ok(desktopPages.includes(name), `missing desktop source ${name}`);
const handler = readFileSync(join(projectRoot, "world_console.py"), "utf8");
test("module URL aliases always serve the shared desktop document", () => {
  const moduleMap = handler.match(/CONSOLE_MODULE_HREFS\s*=\s*\{([\s\S]*?)\n\}/)?.[1]; assert.ok(moduleMap);
  const aliases = [...moduleMap.matchAll(/["'][^"']+["']\s*:\s*["']([^"']+\.html)["']/g)].map(match => match[1]);
  assert.ok(aliases.includes("music.html") && aliases.includes("workspace.html") && aliases.includes("index.html"));
  assert.match(handler, /CONSOLE_PAGE_PATHS\s*=\s*\{[^\n]*CONSOLE_MODULE_HREFS\.values\(\)/);
  const route = handler.match(/if parsed\.path in CONSOLE_PAGE_PATHS:([\s\S]*?)\n        super\(\)\.do_GET\(\)/)?.[1]; assert.ok(route);
  assert.match(route, /self\.send_file_response\(APP_DIR\s*\/\s*["']index\.html["'],\s*["']text\/html; charset=utf-8["']\)/);
});

const roots = [["source", projectRoot]], args = process.argv.slice(2);
if (args.length) {
  assert.equal(args.length, 2, "usage: node tools/check-console-header-controls.mjs [--app-dir <bundle-or-_internal>]");
  assert.equal(args[0], "--app-dir");
  const supplied = resolve(args[1]);
  const appDir = existsSync(join(supplied, "index.html")) ? supplied : join(supplied, "_internal");
  assert.ok(existsSync(join(appDir, "index.html")), `missing packaged index.html: ${appDir}`);
  roots.push(["package", appDir]);
}
test("renamed and unannotated settings/update shortcuts are rejected in the shared desktop header", () => {
  const html = readFileSync(join(projectRoot, "index.html"), "utf8");
  for (const [id, caption] of [["futureUpdateVersion", "Update version"], ["futureGearSettings", "⚙"], ["futureConsoleUpdate", "Update Codex Console"]]) {
    const bad = html.replace('<button id="languageToggle"', `<details hidden><summary>${caption}</summary><button id="${id}" hidden>${caption}</button></details><button id="languageToggle"`);
    assert.throws(() => checkMarkup(`bad fixture ${id}`, bad), /unexpected desktop header control/);
  }
  const renamed = html.replace('<button id="languageToggle"', '<button id="renamedUpdate">Update</button><button id="languageToggle"');
  assert.throws(() => checkMarkup("bad fixture renamed Update", renamed), /unexpected desktop header control renamedUpdate/);
});
test("module navigation/archive remain allowed and separate reader/resource controls remain intact", () => {
  const document = parseDocument(readFileSync(join(projectRoot, "index.html"), "utf8"));
  const link = new Element("a", { class: "module-link", "data-module-id": "music", href: "music.html" });
  document.querySelector("[data-module-nav]").append(link);
  const item = new Element("button", { class: "archive-item", "data-module-id": "unity" });
  document.getElementById("moduleArchiveList").append(item);
  checkHeaderActions("module fixture", document);
  for (const name of ["reader.html", "resources.html"]) checkMarkup(name, readFileSync(join(projectRoot, name), "utf8"));
});
for (const [label, root] of roots) {
  const pages = new Map();
  test(`${label}: every desktop entry page excludes header management controls`, () => {
    for (const name of desktopPages) {
      const html = readFileSync(join(root, name), "utf8"); checkMarkup(`${label}/${name}`, html); pages.set(name, html);
    }
  });
  test(`${label}: removed header styles stay absent`, () => {
    assert.doesNotMatch(readFileSync(join(root, "styles.css"), "utf8"), /\.console-update-top\b/);
  });
  checkRuntime(label, readFileSync(join(root, "app.js"), "utf8"), pages);
}
console.log(`Desktop header policy: ${checks} checks passed (${desktopPages.length} desktop entry pages per root).`);
