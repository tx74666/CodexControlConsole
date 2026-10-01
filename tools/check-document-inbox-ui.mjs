#!/usr/bin/env node
// Isolated DOM/API regressions; never opens a browser or writes a real inbox.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = readFileSync(join(root, "app.js"), "utf8");
const html = readFileSync(join(root, "index.html"), "utf8");
const inboxSource = source.slice(source.indexOf("function documentInboxEntryStatus("), source.indexOf("function showDocumentSampleStatus("));
const controlsSource = source.slice(source.indexOf("function updateDocumentControls("), source.indexOf("async function documentRequest("));
const clone = value => structuredClone(value);
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const settle = async () => { for (let n = 0; n < 12; n += 1) await new Promise(setImmediate); };
let passed = 0;

function createInbox() {
  const elements = new Map(), calls = [], notices = [], channels = [], opened = [], windowEvents = {};
  const all = element => element.children.flatMap(child => [child, ...all(child)]);
  const matches = (element, selector) => {
    if (selector.startsWith(".")) return element.className.split(/\s+/).includes(selector.slice(1));
    const match = selector.match(/^\[([^=\]]+)(?:=['"]?([^'"\]]+)['"]?)?\]$/);
    return match ? element.getAttribute(match[1]) !== undefined && (match[2] === undefined || element.getAttribute(match[1]) === match[2]) : element.tagName.toLowerCase() === selector;
  };
  class Element {
    constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {}; this.dataset = {}; this.attributes = {}; this.style = {}; this.className = ""; this._text = ""; }
    appendChild(child) { child.parentElement = this; this.children.push(child); return child; }
    append(...children) { children.forEach(child => this.appendChild(child)); }
    replaceChildren(...children) { if (this.contains(document.activeElement)) document.activeElement = document.body; this.children.forEach(child => { child.parentElement = null; }); this.children = []; this._text = ""; this.append(...children); }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    getAttribute(key) { if (key.startsWith("data-")) return this.dataset[key.slice(5).replace(/-([a-z])/g, (_, value) => value.toUpperCase())]; return this.attributes[key]; }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    contains(element) { return element === this || all(this).includes(element); }
    closest(selector) { return matches(this, selector) ? this : this.parentElement?.closest(selector); }
    querySelector(selector) { return all(this).find(element => matches(element, selector)) || null; }
    focus() { if (!this.disabled) document.activeElement = this; }
    scrollIntoView() { this.scrolled = true; }
  }
  const body = new Element("body");
  const document = {
    body, activeElement: body,
    createElement: tag => new Element(tag), createElementNS: (_namespace, tag) => new Element(tag),
    querySelectorAll(selector) {
      if (selector.startsWith("#documentInboxTabs ")) return all(elements.get("InboxTabs")).filter(element => matches(element, selector.split(" ").at(-1)));
      if (selector === ".document-inbox-entry button, .document-inbox-entry input") return all(elements.get("InboxEntries")).filter(element => ["BUTTON", "INPUT"].includes(element.tagName));
      if (selector === ".document-guide-card button") return [];
      throw new Error(`Unsupported test selector: ${selector}`);
    },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  };
  for (const suffix of ["Inbox", "UnreadBadge", "InboxTabs", "InboxTabPill", "InboxEntries", "InboxClearAll", "InboxUndoBar", "InboxUndoMessage", "InboxUndo", "InboxTabInbox", "InboxTabLater", "InboxTabArchive", "InboxCountInbox", "InboxCountLater", "InboxCountArchive"]) {
    const element = new Element(suffix.startsWith("InboxTab") && suffix !== "InboxTabs" && suffix !== "InboxTabPill" ? "button" : "div"); element.id = `document${suffix}`; elements.set(suffix, element); body.appendChild(element);
  }
  for (const [index, name] of ["Inbox", "Later", "Archive"].entries()) {
    const tab = elements.get(`InboxTab${name}`); tab.dataset.inboxStatus = name.toLowerCase(); tab.offsetWidth = 100; tab.offsetLeft = index * 100; elements.get("InboxTabs").appendChild(tab);
  }
  const entries = [
    { id: "one", title: "<script>literal title</script>", path: "one.md", summary: "<img src=x onerror=alert(1)>", source: "Fixture", createdAt: "2026-09-28", status: "inbox", read: false },
    { id: "two", title: "Second", path: "two.md", status: "inbox", read: false },
    { id: "later", title: "Later", path: "later.md", status: "later", read: false },
    { id: "old", title: "Archive", path: "old.md", status: "archive", read: true }
  ];
  const files = entries.map(entry => entry.path), undo = new Map();
  let nextGate = null, nextReply = null, token = 0;
  const library = { root: "D:/library", exists: true, busy: false, sample: { status: "idle" } };
  const state = { entries: [], busy: false, loading: false, root: "", view: "inbox", undo: null, sequence: 0, refreshPending: false };
  const snapshot = () => ({ root: library.root, entries: clone(entries.filter(entry => entry.status !== "cleared")), unreadCount: entries.filter(entry => ["inbox", "later"].includes(entry.status)).length });
  const runtime = {
    document, documentLibrary: library, documentInbox: state, documentInboxChannel: null, documentReadingWindow: null, documentResources: { pendingLoad: false },
    documentNode: suffix => elements.get(suffix) || null, documentText: (_zh, en) => en, documentNotice: (...message) => notices.push(message), documentSampleRunning: () => false,
    flushDocumentResourcesPending() {},
    withDocumentAction: async () => { throw new Error("Reader popup unexpectedly failed"); }, URL, URLSearchParams,
    BroadcastChannel: class { constructor(name) { this.name = name; this.messages = []; channels.push(this); } postMessage(message) { this.messages.push(clone(message)); } receive(message) { this.onmessage?.({ data: message }); } },
    window: { location: { href: "http://127.0.0.1:55319/workspace.html" }, requestAnimationFrame: action => action(), addEventListener: (event, action) => { windowEvents[event] = action; }, open(url, name) { const reader = { location: { href: url }, closed: false, focus() {} }; opened.push({ url, name }); return reader; } },
    async documentRequest(endpoint, payload) {
      calls.push({ endpoint, payload: clone(payload) });
      assert.equal(payload?.expectedRoot || new URLSearchParams(endpoint.split("?")[1]).get("expectedRoot"), library.root, "expectedRoot guard missing");
      let result;
      if (payload) {
        if (endpoint === "inbox/read" || endpoint === "inbox/move") {
          const entry = entries.find(item => item.id === payload.id); assert.ok(entry && entry.status !== "cleared");
          entry.status = endpoint === "inbox/read" ? (payload.read ? "archive" : "inbox") : payload.status; entry.read = entry.status === "archive"; result = snapshot();
        } else if (endpoint === "inbox/archive/clear") {
          const ids = entries.filter(entry => entry.status === "archive").map(entry => entry.id); ids.forEach(id => { entries.find(entry => entry.id === id).status = "cleared"; });
          const undoToken = `undo-${++token}`; undo.set(undoToken, ids); result = { ...snapshot(), clearedCount: ids.length, undoToken };
        } else if (endpoint === "inbox/archive/restore") {
          for (const id of undo.get(payload.undoToken) || []) { const entry = entries.find(entry => entry.id === id); if (entry.status === "cleared") entry.status = "archive"; }
          result = snapshot();
        } else throw new Error(`Unexpected mutation ${endpoint}`);
      } else result = snapshot();
      const gate = nextGate; nextGate = null;
      if (nextReply) { result = nextReply(result); nextReply = null; }
      if (gate) await gate.promise;
      return result;
    }
  };
  const api = runInNewContext(`${controlsSource}\n${inboxSource}\n({bindDocumentInbox,loadDocumentInbox,renderDocumentInbox,setDocumentInboxView,setDocumentInboxRead,moveDocumentInboxEntry,clearDocumentInboxArchive,restoreDocumentInboxArchive,requestDocumentInboxRefresh,openDocumentInboxEntry,sameDocumentInboxRoot,documentInboxEntryStatus})`, runtime);
  api.bindDocumentInbox();
  return { api, state, library, entries, files, document, elements, channels, calls, notices, opened, snapshot, gateNext() { nextGate = deferred(); return nextGate; }, replyNext(transform) { nextReply = transform; }, rows: () => elements.get("InboxEntries").children.filter(item => item.dataset.reportId), control(id, action) { return this.rows().find(row => row.dataset.reportId === id)?.querySelector(`[data-inbox-action="${action}"]`); } };
}

async function test(name, action) { await action(); passed += 1; console.log(`PASS ${name}`); }

await test("persistent tabs, one list, legacy statuses and safe text", async () => {
  for (const id of ["documentInboxTabInbox", "documentInboxTabLater", "documentInboxTabArchive", "documentInboxEntries", "documentInboxClearAll", "documentInboxUndo"]) assert.equal((html.match(new RegExp(`id="${id}"`, "g")) || []).length, 1);
  assert.ok(!html.includes('id="documentInboxHistory"'));
  const h = createInbox(); await h.api.loadDocumentInbox();
  assert.equal(h.rows().length, 2); assert.equal(h.elements.get("UnreadBadge").textContent, "2");
  assert.equal(h.elements.get("InboxCountLater").textContent, "1"); assert.equal(h.elements.get("InboxCountArchive").textContent, "1");
  assert.equal(h.control("one", "open").textContent, "<script>literal title</script>"); assert.equal(h.control("one", "open").children.length, 0);
  assert.equal(h.api.documentInboxEntryStatus({ read: true }), "archive"); assert.equal(h.api.documentInboxEntryStatus({ read: false }), "inbox");
  h.entries.splice(0); await h.api.loadDocumentInbox();
  assert.equal(h.elements.get("Inbox").hidden, false); assert.equal(h.elements.get("UnreadBadge").hidden, true);
  assert.equal(h.elements.get("InboxCountInbox").textContent, "0"); assert.equal(h.rows().length, 0);
});

await test("opening a reader never marks read", async () => {
  const h = createInbox(); await h.api.loadDocumentInbox(); await h.api.openDocumentInboxEntry(h.state.entries[0]);
  assert.equal(h.opened.length, 1); const url = new URL(h.opened[0].url); assert.equal(url.pathname, "/reader.html"); assert.equal(url.searchParams.get("root"), h.library.root); assert.equal(url.searchParams.get("id"), "one");
  assert.equal(h.calls.filter(call => call.payload).length, 0);
});

await test("read, un-read and bookmarks move only the selected report", async () => {
  const h = createInbox(); await h.api.loadDocumentInbox();
  await h.api.moveDocumentInboxEntry("one", "later"); assert.equal(h.rows().length, 1); assert.equal(h.elements.get("UnreadBadge").textContent, "1");
  h.api.setDocumentInboxView("later"); assert.equal(h.control("one", "bookmark").getAttribute("aria-pressed"), "true");
  await h.api.moveDocumentInboxEntry("one", "inbox"); assert.equal(h.rows().length, 1);
  h.api.setDocumentInboxView("inbox"); await h.api.setDocumentInboxRead("one", true); assert.equal(h.control("one", "read"), undefined);
  h.api.setDocumentInboxView("archive"); assert.equal(h.control("one", "read").checked, true); await h.api.setDocumentInboxRead("one", false); assert.equal(h.control("one", "read"), undefined);
  await h.api.moveDocumentInboxEntry("old", "later"); assert.equal(h.rows().length, 0); assert.ok(h.channels[0].messages.every(message => message.type === "read-changed" && message.root === h.library.root));
});

await test("archive clear and root-bound Undo preserve files and other tabs", async () => {
  const h = createInbox(); await h.api.loadDocumentInbox(); assert.equal(h.elements.get("InboxClearAll").hidden, true);
  h.api.setDocumentInboxView("archive"); assert.equal(h.elements.get("InboxClearAll").hidden, false); await h.api.clearDocumentInboxArchive();
  assert.equal(h.rows().length, 0); assert.equal(h.state.undo.count, 1); assert.equal(h.elements.get("InboxUndoBar").hidden, false); assert.equal(h.files.length, 4);
  assert.equal(h.state.entries.length, 3); await h.api.restoreDocumentInboxArchive(); assert.equal(h.rows().length, 1); assert.equal(h.state.undo, null);
  await h.api.clearDocumentInboxArchive(); h.library.root = "D:/other"; h.api.renderDocumentInbox(); assert.equal(h.state.undo, null); assert.equal(h.state.view, "inbox");
  const count = h.calls.length; assert.equal(await h.api.restoreDocumentInboxArchive(), false); assert.equal(h.calls.length, count);
});

await test("an empty concurrent clear cannot replace a working Undo token", async () => {
  const h = createInbox(); await h.api.loadDocumentInbox(); h.api.setDocumentInboxView("archive"); await h.api.clearDocumentInboxArchive(); const token = h.state.undo.token;
  // A stale local list can still show an archive another window already cleared.
  h.state.entries.push({ id: "stale", status: "archive" }); await h.api.clearDocumentInboxArchive(); assert.equal(h.state.undo.token, token);
});

await test("response root mismatch and folder switches discard old results", async () => {
  const h = createInbox(); await h.api.loadDocumentInbox(); h.replyNext(result => ({ ...result, root: "D:/wrong", entries: [] })); await assert.rejects(h.api.loadDocumentInbox(), /library has changed/); assert.equal(h.state.entries.length, 4);
  const gate = h.gateNext(); const request = h.api.loadDocumentInbox(); h.library.root = "D:/other"; h.api.renderDocumentInbox(); gate.resolve(); assert.equal(await request, false); assert.equal(h.state.entries.length, 0);
  assert.equal(h.api.sameDocumentInboxRoot("D:\\Library\\", "d:/library"), true); assert.equal(h.api.sameDocumentInboxRoot("/library/A", "/library/a"), false);
});

await test("an earlier GET cannot overwrite a later mutation", async () => {
  const h = createInbox(); await h.api.loadDocumentInbox(); const gate = h.gateNext(); const request = h.api.loadDocumentInbox(); await h.api.setDocumentInboxRead("one", true); gate.resolve(); assert.equal(await request, false); assert.equal(h.state.entries.find(entry => entry.id === "one").status, "archive");
});

await test("busy mutation queues reader broadcast then reconciles after its older reply", async () => {
  const h = createInbox(); await h.api.loadDocumentInbox(); h.api.setDocumentInboxView("later"); const gate = h.gateNext(); const request = h.api.moveDocumentInboxEntry("one", "later");
  assert.equal(h.control("later", "read").disabled, true);
  h.entries.find(entry => entry.id === "two").status = "archive"; h.channels[0].receive({ type: "read-changed", root: h.library.root }); assert.equal(h.state.refreshPending, true);
  gate.resolve(); await request; await settle(); assert.equal(h.state.entries.find(entry => entry.id === "two").status, "archive"); assert.equal(h.state.view, "later"); assert.equal(h.state.refreshPending, false); assert.equal(h.control("later", "read").disabled, false);
  const count = h.calls.length; h.channels[0].receive({ type: "read-changed", root: "D:/other" }); await settle(); assert.equal(h.calls.length, count);
});

await test("keyboard tabs wrap and expose the selected single panel", async () => {
  const h = createInbox(); await h.api.loadDocumentInbox(); let prevented = 0;
  const key = (name, value) => h.elements.get(`InboxTab${name}`).listeners.keydown({ key: value, preventDefault() { prevented += 1; } });
  key("Inbox", "ArrowLeft"); assert.equal(h.state.view, "archive"); assert.equal(h.document.activeElement, h.elements.get("InboxTabArchive"));
  key("Archive", "ArrowRight"); assert.equal(h.state.view, "inbox"); key("Inbox", "End"); assert.equal(h.state.view, "archive"); key("Archive", "Home"); assert.equal(h.state.view, "inbox");
  assert.equal(prevented, 4); assert.equal(h.elements.get("InboxEntries").getAttribute("aria-labelledby"), "documentInboxTabInbox"); assert.equal(h.elements.get("InboxTabLater").tabIndex, -1);
});

await test("refresh preserves row focus and removed rows return focus to the selected tab", async () => {
  const h = createInbox(); await h.api.loadDocumentInbox(); h.control("one", "read").focus(); await h.api.loadDocumentInbox(); assert.equal(h.document.activeElement, h.control("one", "read"));
  await h.api.setDocumentInboxRead("one", true); assert.equal(h.document.activeElement, h.elements.get("InboxTabInbox"));
  h.control("two", "bookmark").focus(); const gate = h.gateNext(); const request = h.api.moveDocumentInboxEntry("two", "later"); h.elements.get("InboxTabLater").focus(); gate.resolve(); await request;
  assert.equal(h.document.activeElement, h.elements.get("InboxTabLater"), "background completion stole new focus");
});

console.log(`Document inbox UI: ${passed} isolated checks passed.`);
