#!/usr/bin/env node
// Small isolated regressions: no browser, service, sampler, or real inbox writes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
function extract(name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  assert.ok(start >= 0, `Missing ${name}`);
  const end = source.slice(start + 1).search(/\n(?:async )?function /);
  return source.slice(start, end < 0 ? undefined : start + 1 + end);
}
const settle = async () => { for (let index = 0; index < 10; index++) await new Promise(setImmediate); };
const defer = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

function harness() {
  const nodes = new Map(), calls = [], opens = [];
  let wait = null, replyRoot = null;
  class Element {
    constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {}; this.dataset = {}; this.attributes = {}; this._text = ""; this.isConnected = true; this.open = false; this.value = ""; }
    appendChild(child) { this.children.push(child); return child; }
    append(...children) { children.forEach(child => this.appendChild(child)); }
    replaceChildren(...children) { this.children = children; this._text = ""; }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    addEventListener(name, action) { this.listeners[name] = action; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    querySelectorAll() { return this.children.filter(child => child.tagName === "BUTTON"); }
    focus() { document.activeElement = this; }
    scrollIntoView() {}
    showModal() { this.open = true; }
    close() { this.open = false; this.listeners.close?.(); }
  }
  const document = { activeElement: new Element("button"), createElement: tag => new Element(tag) };
  const library = { root: "", exists: false, loaded: false, busy: false, path: "", file: "", sample: { status: "idle" }, pendingSampleReport: null };
  const resources = { view: "guide", guideLoaded: false, guideItems: [], aiLoaded: false, sequence: 0, fileSequence: 0, browseSequence: 0, pendingLoad: false };
  const runtime = {
    document, documentLibrary: library, documentResources: resources, documentInbox: { entries: [], busy: false, refreshPending: false }, documentOverviewResult: null,
    documentNode(id) { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); }, documentText: (_zh, en) => en, text: key => key,
    documentNotice() {}, updateDocumentControls() {}, saveDocumentPosition() {}, renderDocumentInbox() {},
    renderDocumentMarkdown: (value, container) => { container.textContent = value; },
    loadDocumentOverview: async () => { calls.push("overview"); }, loadDocumentInbox: async () => { calls.push("inbox"); }, loadDocumentSnapshots: async () => { calls.push("snapshots"); },
    showDocumentSampleStatus() {}, scheduleDocumentSamplePoll() {}, requestDocumentInboxRefresh() {},
    runtimeActivityReady: true, activeConsoleView: "document", isModuleForeground: () => true,
    openDocumentReadingWindow(path) { opens.push(path); return true; },
    async documentRequest(endpoint) {
      calls.push(endpoint);
      const root = replyRoot || "D:/library"; replyRoot = null;
      let result;
      if (endpoint === "state") result = { root, exists: true };
      else if (endpoint.startsWith("guide?")) result = { root, items: [{ path: "report.md", title: "A useful conclusion", summary: "For the reader", highlights: ["<script>literal highlight</script>", "Next action"] }] };
      else if (endpoint.startsWith("list?")) result = { root, path: "", entries: [{ path: "README.md", name: "README.md", isDirectory: false }, { path: "report.md", name: "report.md", isDirectory: false }] };
      else if (endpoint.startsWith("read?")) result = { root, path: "report.md", name: "Report", content: "Saved report body", format: "markdown" };
      else if (endpoint === "sample-status") result = { status: "idle" };
      else throw new Error(`Unexpected endpoint ${endpoint}`);
      const gate = wait; wait = null; if (gate) await gate.promise;
      return result;
    }
  };
  const names = ["sameDocumentInboxRoot", "withDocumentAction", "resetDocumentResources", "setDocumentResourcesView", "showDocumentResources", "renderDocumentGuide", "flushDocumentResourcesPending", "loadDocumentGuide", "loadDocumentAIRecords", "bindDocumentResources", "clearDocumentReader", "readDocumentFile", "browseDocumentFolder", "loadDocumentLibrary", "finishDocumentSampleReport", "openDocumentInboxEntry"];
  const api = runInNewContext(`${names.map(extract).join("\n")}\n({${names.join(",")}})`, runtime);
  api.bindDocumentResources();
  return { api, runtime, library, resources, nodes, calls, opens, document, node: runtime.documentNode, gateNext() { wait = defer(); return wait; }, rootNext(value) { replyRoot = value; } };
}

let count = 0;
async function test(name, action) { await action(); console.log(`PASS ${name}`); count += 1; }

await test("homepage has a closed dialog and performs no directory or body reads", async () => {
  assert.match(html, /<dialog id="documentResourcesDialog"[^>]*>/);
  assert.doesNotMatch(html, /<dialog id="documentResourcesDialog"[^>]*\bopen\b/);
  assert.ok(html.indexOf('id="documentResourcesDialog"') < html.indexOf('class="document-layout"'));
  assert.ok(html.indexOf('id="documentResourcesDialog"') < html.indexOf('id="documentFolderSettings"'));
  assert.match(html, /id="documentAIPanel"[^>]*hidden/);
  const h = harness(); await h.api.loadDocumentLibrary();
  assert.deepEqual(h.calls, ["state", "overview", "inbox", "sample-status"]);
  assert.equal(h.node("ResourcesDialog").open, false); assert.equal(h.library.file, "");
  await h.api.loadDocumentLibrary({ force: true });
  assert.ok(!h.calls.some(call => /^(?:read|list|guide)\?/.test(call)));
});

await test("explicit library entry loads only curated highlights and safely opens their report", async () => {
  const h = harness(); await h.api.loadDocumentLibrary(); h.node("ResourcesOpen").focus(); h.node("ResourcesOpen").listeners.click(); await settle();
  assert.equal(h.node("ResourcesDialog").open, true); assert.equal(h.resources.view, "guide");
  assert.ok(h.calls.some(call => call === "guide?expectedRoot=D%3A%2Flibrary")); assert.ok(!h.calls.some(call => /^(?:read|list)\?/.test(call)));
  const card = h.node("GuideEntries").children[0]; assert.equal(card.children[2].children[0].textContent, "<script>literal highlight</script>"); assert.equal(card.children[2].children[0].children.length, 0);
  card.children[0].listeners.click(); await settle(); assert.deepEqual(h.opens, ["report.md"]); assert.ok(!h.calls.some(call => call.includes("inbox/read")));
  h.node("ResourcesClose").listeners.click(); assert.equal(h.document.activeElement, h.node("ResourcesOpen"));
  h.resources.view = "ai"; h.node("ResourcesOpen").listeners.click(); await settle(); assert.equal(h.resources.view, "guide");
});

await test("AI records lazily list files once and never auto-open README", async () => {
  const h = harness(); await h.api.loadDocumentLibrary(); h.api.showDocumentResources("ai"); await settle();
  assert.equal(h.calls.filter(call => call.startsWith("list?")).length, 1); assert.ok(!h.calls.some(call => call.startsWith("read?"))); assert.equal(h.library.file, "");
  h.api.showDocumentResources("guide"); await settle(); h.api.showDocumentResources("ai"); await settle(); assert.equal(h.calls.filter(call => call.startsWith("list?")).length, 1);
  let prevented = false; h.node("AITab").listeners.keydown({ key: "Home", preventDefault() { prevented = true; } }); await settle(); assert.equal(h.resources.view, "guide"); assert.equal(prevented, true);
});

await test("popup fallback and actively generated reports expose the inline reader", async () => {
  const h = harness(); await h.api.loadDocumentLibrary(); h.runtime.openDocumentReadingWindow = () => false;
  await h.api.openDocumentInboxEntry({ path: "report.md" }); assert.equal(h.node("ResourcesDialog").open, true); assert.equal(h.node("AIPanel").hidden, false); assert.equal(h.node("Content").textContent, "Saved report body");
  h.node("ResourcesDialog").close(); h.library.pendingSampleReport = { root: h.library.root, report: "report.md" }; await h.api.finishDocumentSampleReport();
  assert.equal(h.node("ResourcesDialog").open, true); assert.equal(h.resources.view, "ai");
  const compare = extract("bindDocumentLibrary").split('documentNode("Compare").addEventListener')[1]; assert.ok(compare.includes('showDocumentResources("ai", { load: false })'));
});

await test("root changes clear guide and reject stale guide, body and folder responses", async () => {
  const h = harness(); await h.api.loadDocumentLibrary(); const gate = h.gateNext(); const pending = h.api.loadDocumentGuide();
  h.library.root = "D:/other"; h.api.resetDocumentResources(); gate.resolve(); await pending; assert.equal(h.resources.guideLoaded, false); assert.equal(h.node("GuideEntries").children.length, 0);
  h.library.root = "D:/library"; h.rootNext("D:/other"); await assert.rejects(h.api.readDocumentFile("report.md"), /library changed/); assert.equal(h.node("Content").textContent, "");
  h.rootNext("D:/other"); await assert.rejects(h.api.browseDocumentFolder(), /library changed/); assert.equal(h.node("Entries").children.length, 0);
  h.rootNext("D:/other"); await assert.rejects(h.api.loadDocumentGuide(), /library changed/);
});

await test("switching tabs during a guide request eventually loads the requested AI pane", async () => {
  const h = harness(); await h.api.loadDocumentLibrary(); const gate = h.gateNext(); h.api.showDocumentResources("guide"); h.api.showDocumentResources("ai");
  assert.equal(h.resources.pendingLoad, true); gate.resolve(); await settle(); assert.equal(h.resources.view, "ai"); assert.equal(h.resources.aiLoaded, true); assert.equal(h.node("AIPanel").hidden, false);
});

await test("tools opened during a busy guide request receive their deferred snapshot list", async () => {
  const h = harness(); await h.api.loadDocumentLibrary(); const gate = h.gateNext(); h.api.showDocumentResources("guide");
  h.node("FolderSettings").open = true; h.node("FolderSettings").listeners.toggle(); assert.equal(h.resources.pendingSnapshots, true); assert.equal(h.calls.includes("snapshots"), false);
  gate.resolve(); await settle(); assert.equal(h.calls.filter(call => call === "snapshots").length, 1); assert.equal(h.resources.pendingSnapshots, false);
});

await test("inbox mutations cannot discard a completed sample report", async () => {
  const h = harness(); await h.api.loadDocumentLibrary(); h.runtime.documentInbox.busy = true; h.library.pendingSampleReport = { root: h.library.root, report: "report.md" };
  await h.api.finishDocumentSampleReport(); assert.ok(h.library.pendingSampleReport); assert.equal(h.node("ResourcesDialog").open, false);
  h.runtime.documentInbox.busy = false; await h.api.finishDocumentSampleReport(); assert.equal(h.library.pendingSampleReport, null); assert.equal(h.node("Content").textContent, "Saved report body");
  assert.ok(extract("mutateDocumentInbox").includes("void finishDocumentSampleReport()"), "inbox completion must drain pending reports");
  assert.ok(extract("updateDocumentControls").includes('.document-guide-card button'), "guide actions must be disabled while busy");
});

console.log(`Document library entry: ${count} isolated checks passed.`);
