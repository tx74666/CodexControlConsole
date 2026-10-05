#!/usr/bin/env node
// Actual desktop UI behavior against in-memory replies: no browser, credentials or network.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const html = readFileSync(new URL("../subscription.html", import.meta.url), "utf8");
const source = readFileSync(new URL("../subscription.js", import.meta.url), "utf8");
const flush = async () => { for (let i = 0; i < 6; i++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const status = (changes = {}) => ({ connected: false, connectionId: null, catalogRevision: null, models: [], status: "disconnected", busy: false, error: null, ...changes });
const connected = (changes = {}) => status({ connected: true, connectionId: "own-connection", catalogRevision: "own-catalog", models: [{ slug: "actual-model", displayName: "目录实际模型" }], status: "connected", ...changes });
const authorizationUrl = "https://auth.openai.com/api/accounts/authorize?client_id=fixture&state=frozen-state&code_challenge=fixture&code_challenge_method=S256";

function tagAttributes(tag) {
  const attributes = new Map();
  for (const match of tag.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) attributes.set(match[1], match[2] ?? "");
  return attributes;
}
class Element {
  constructor(tag = "div", attributes = new Map()) {
    this.tagName = tag.toUpperCase(); this.attributes = attributes; this.listeners = new Map(); this.children = [];
    this.dataset = {}; this._text = ""; this.disabled = false; this.hidden = attributes.has("hidden"); this.href = attributes.get("href") || "";
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_) { throw new Error("Status, model and error input must never become HTML"); }
  replaceChildren(...values) { this._text = ""; this.children = values; }
  addEventListener(name, callback) { this.listeners.set(name, callback); }
  removeAttribute(name) { this.attributes.delete(name); if (name === "href") this.href = ""; }
  click() { if (!this.disabled) this.listeners.get("click")?.(); }
}
function harness(initial = status()) {
  const nodes = new Map(), calls = [], navigations = [], replies = new Map();
  for (const match of html.matchAll(/<([a-z]+)\b[^>]*\bid="([^"]+)"[^>]*>/gi)) nodes.set(match[2], new Element(match[1], tagAttributes(match[0])));
  replies.set("GET status", initial);
  const respond = (key, value) => replies.set(key, value);
  const runtime = {
    URL, console,
    document: { getElementById(id) { assert.ok(nodes.has(id), `Missing actual HTML control: ${id}`); return nodes.get(id); }, createElement(tag) { return new Element(tag); } },
    window: { open(...args) { navigations.push(args); throw new Error("Authorization must be opened only by the human following a link"); }, location: { assign(...args) { navigations.push(args); throw new Error("No automatic navigation"); }, replace(...args) { navigations.push(args); throw new Error("No automatic navigation"); } } },
    location: { assign() { throw new Error("No automatic navigation"); }, replace() { throw new Error("No automatic navigation"); } },
    async fetch(url, options) {
      const parsed = new URL(url, "http://127.0.0.1:43123/subscription.html");
      assert.equal(parsed.origin, "http://127.0.0.1:43123");
      assert.match(parsed.pathname, /^\/api\/workflow\/subscription\/(?:status|signin|models|disconnect)$/);
      assert.equal(parsed.search, "");
      assert.equal(options.credentials, "same-origin"); assert.equal(options.mode, "same-origin"); assert.equal(options.redirect, "error"); assert.equal(options.cache, "no-store");
      const method = options.method, action = parsed.pathname.split("/").at(-1);
      calls.push({ action, method, options: structuredClone(options) });
      if (method === "POST") { assert.equal(options.headers["Content-Type"], "application/json"); assert.deepEqual(JSON.parse(options.body), {}); }
      else { assert.equal(method, "GET"); assert.equal(options.body, undefined); }
      const key = `${method} ${action}`; assert.ok(replies.has(key), `Unconfirmed operation: ${key}`);
      const configured = replies.get(key), reply = await (typeof configured === "function" ? configured() : configured);
      if (reply instanceof Error) throw reply;
      return { ok: reply?.httpError !== true, async json() { return structuredClone(reply); } };
    }
  };
  runInNewContext(source, runtime);
  return { nodes, calls, navigations, respond, control: id => nodes.get(id) };
}

let count = 0;
async function test(name, body) { await body(); count++; console.log(`PASS ${name}`); }

await test("opening the actual page reads cached status once without OAuth POST or navigation", async () => {
  const h = harness(); await flush();
  assert.deepEqual(h.calls.map(item => [item.method, item.action]), [["GET", "status"]]);
  assert.equal(h.navigations.length, 0); assert.equal(h.control("authorizationLink").hidden, true);
  assert.match(h.control("connectionStatus").textContent, /尚未连接/);
  assert.equal(h.control("models").disabled, true); assert.equal(h.control("disconnect").disabled, true);
  const back = html.match(/<a\b[^>]*class="back"[^>]*href="([^"]+)"[^>]*>([^<]+)<\/a>/);
  assert.ok(back, "Actual page must offer a visible return to Console");
  const target = new URL(back[1], "http://127.0.0.1:43123/subscription.html");
  assert.equal(target.origin, "http://127.0.0.1:43123"); assert.equal(target.pathname, "/index.html"); assert.match(back[2], /返回 Console/);
});

await test("only the signin click posts once and reveals an official human-operated link", async () => {
  const h = harness(); await flush(); h.respond("POST signin", { authorizationUrl });
  h.control("signin").click(); h.control("signin").click(); await flush();
  assert.deepEqual(h.calls.map(item => [item.method, item.action]), [["GET", "status"], ["POST", "signin"]]);
  const link = h.control("authorizationLink"); assert.equal(link.hidden, false); assert.equal(link.href, authorizationUrl);
  assert.equal(link.attributes.get("target"), "_blank"); assert.match(link.attributes.get("rel"), /noopener/); assert.match(link.attributes.get("rel"), /noreferrer/);
  assert.match(h.control("operationStatus").textContent, /点击下面的官方授权链接/); assert.equal(h.navigations.length, 0);
  h.respond("GET status", connected()); h.control("status").click(); await flush();
  assert.equal(h.control("authorizationLink").hidden, true); assert.equal(h.control("authorizationLink").href, "");
  assert.match(h.control("connectionStatus").textContent, /订阅已连接/); assert.equal(h.calls.filter(item => item.method === "POST").length, 1);
});

await test("foreign script credential fragment and wrong-path authorization URLs stay inaccessible", async () => {
  for (const candidate of ["javascript:alert(1)", "https://other.invalid/api/accounts/authorize", "http://auth.openai.com/api/accounts/authorize", "https://auth.openai.com:444/api/accounts/authorize", "https://auth.openai.com/api/accounts/authorize/extra", "https://user:password@auth.openai.com/api/accounts/authorize", "https://auth.openai.com/api/accounts/authorize#private-fragment"]) {
    const h = harness(); await flush(); h.respond("POST signin", { authorizationUrl: candidate }); h.control("signin").click(); await flush();
    assert.equal(h.control("authorizationLink").hidden, true, candidate); assert.equal(h.control("authorizationLink").href, "", candidate);
    assert.equal(h.control("operationStatus").dataset.error, "true"); assert.match(h.control("operationStatus").textContent, /授权地址无法核对/);
    assert.equal(h.navigations.length, 0);
  }
});

await test("another signin retires the old link even when the next response fails", async () => {
  const h = harness(); await flush(); h.respond("POST signin", { authorizationUrl }); h.control("signin").click(); await flush();
  assert.equal(h.control("authorizationLink").hidden, false);
  const pending = deferred(); h.respond("POST signin", pending.promise); h.control("signin").click();
  assert.equal(h.control("authorizationLink").hidden, true); assert.equal(h.control("authorizationLink").href, "");
  pending.resolve({ httpError: true, error: "本次登录未完成" }); await flush();
  assert.equal(h.control("authorizationLink").hidden, true); assert.equal(h.control("authorizationLink").href, "");
  assert.equal(h.control("operationStatus").textContent, "本次登录未完成"); assert.equal(h.navigations.length, 0);
});

await test("catalog restoration uses an explicit one-shot model refresh and preserves official order", async () => {
  const h = harness(status({ connectionId: "saved-grant", status: "catalog_required" })); await flush();
  assert.equal(h.control("models").disabled, false); assert.match(h.control("connectionStatus").textContent, /重新读取模型/);
  const pending = deferred(); h.respond("POST models", pending.promise); h.control("models").click(); h.control("models").click();
  assert.equal(h.calls.filter(item => item.action === "models").length, 1); assert.equal(h.control("signin").disabled, true);
  pending.resolve(connected({ models: [{ slug: "second-name-first", displayName: "官方第一项" }, { slug: "first-name-second", displayName: "官方第二项" }] })); await flush();
  assert.deepEqual(h.control("modelList").children.map(item => item.textContent), ["官方第一项 · second-name-first", "官方第二项 · first-name-second"]);
  assert.equal(h.control("signin").disabled, false); assert.equal(h.navigations.length, 0);
  assert.deepEqual(h.calls.map(item => [item.method, item.action]), [["GET", "status"], ["POST", "models"]]);
});

await test("explicit disconnect displays local stop without claiming unconfirmed remote revocation", async () => {
  const h = harness(connected()); await flush();
  h.respond("POST disconnect", status({ error: "subscription_remote_revocation_unconfirmed" })); h.control("disconnect").click(); await flush();
  assert.deepEqual(h.calls.map(item => [item.method, item.action]), [["GET", "status"], ["POST", "disconnect"]]);
  assert.match(h.control("connectionStatus").textContent, /本机连接已停止.*官方撤销尚未核实/);
  assert.match(h.control("operationStatus").textContent, /原记录与草稿保留/);
  assert.equal(h.control("authorizationLink").hidden, true); assert.equal(h.control("authorizationLink").href, "");
  assert.equal(h.control("models").disabled, true); assert.equal(h.control("disconnect").disabled, true); assert.equal(h.navigations.length, 0);
});

await test("untrusted status model and error strings remain plain text and cannot become links or HTML", async () => {
  const malicious = "<img src=x onerror=alert(1)>", h = harness(connected({ status: malicious, models: [{ slug: "<script>alert(1)</script>", displayName: malicious }] })); await flush();
  assert.equal(h.control("connectionStatus").textContent, malicious); assert.equal(h.control("modelList").children[0].textContent, `${malicious} · <script>alert(1)</script>`);
  assert.equal(h.control("modelList").children[0].tagName, "LI"); assert.equal(h.control("authorizationLink").hidden, true);
  h.respond("POST models", { httpError: true, error: malicious }); h.control("models").click(); await flush();
  assert.equal(h.control("operationStatus").textContent, malicious); assert.equal(h.control("operationStatus").dataset.error, "true"); assert.equal(h.navigations.length, 0);
});

console.log(`${count} desktop subscription UI checks passed.`);
