#!/usr/bin/env node
// Device overview regressions use isolated DTOs: no sampler, driver query or user data.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8").replace(/\r\n?/g, "\n");
const GiB = 1024 ** 3;
const freshAt = "2026-10-03T12:00:00+08:00";
const savedAt = "2026-09-27T12:00:00+08:00";
const hardwareAt = "2026-10-01T12:00:00+08:00";
function extract(name) {
  const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
  assert.ok(start >= 0, `Missing ${name}`);
  const end = source.slice(start + 1).search(/\n(?:async )?function /);
  return source.slice(start, end < 0 ? undefined : start + 1 + end);
}
function fixture() {
  return {
    root: "D:/fixture-library", sampledAt: savedAt, hardwareSampledAt: hardwareAt, status: "completed", model: "Fixture laptop", cpuModel: "Fixture CPU",
    cpus: [{ name: "Fixture CPU", cores: 6, logicalProcessors: 12 }],
    physicalTotalBytes: 16 * GiB, installedMemoryBytes: 16 * GiB,
    availableBytes: 2 * GiB, commitBytes: 18 * GiB,
    memoryModules: [{ capacityBytes: 8 * GiB, speedMHz: 3200, configuredSpeedMHz: 3200 }, { capacityBytes: 8 * GiB, speedMHz: 3200, configuredSpeedMHz: 3200 }],
    gpuModels: ["Fixture NVIDIA"], gpus: [{ name: "Fixture NVIDIA", dedicatedCapacityBytes: 6 * GiB, driverVersion: "fixture-driver", capacityReason: "saved driver capacity" }],
    currentMemory: { status: "available", readAt: freshAt, totalBytes: 16 * GiB, usedBytes: 11 * GiB, availableBytes: 5 * GiB, usedPercent: 68.75, source: "Windows fixture" },
    currentGpuRead: { status: "available", readAt: freshAt, source: "driver fixture", reason: "" },
    currentGpu: [{ adapterId: "GPU-fixture-a", name: "Fixture NVIDIA", status: "available", readAt: freshAt, totalBytes: 6 * GiB, usedBytes: 1.5 * GiB, freeBytes: 4.5 * GiB, utilizationPercent: 25, temperatureC: 51, source: "driver fixture", reason: "" }],
    currentStorage: { status: "available", readAt: freshAt, totalBytes: 2_000_000_000_000, usedBytes: 1_250_000_000_000, freeBytes: 750_000_000_000, source: "anonymous fixed-disk totals", reason: "" },
    deviceDetails: { status: "available", model: "Fixture laptop", purchase: { amount: 6500, currency: "CNY", approximate: true, source: "user recollection", year: 2021, yearApproximate: true }, color: "Carbon black", reason: "" },
    applications: [], volumes: [{ letter: "C:", sizeBytes: 512 * GiB }, { letter: "D:", sizeBytes: 1024 * GiB }],
    physicalDisks: [{ model: "PRIVATE DISK MODEL", sizeBytes: 1024 * GiB }]
  };
}
function harness(data, language = "en") {
  class Element {
    constructor(tag = "div") { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.attributes = {}; this.listeners = new Map(); this._text = ""; this.className = ""; this.style = { setProperty(name, value) { this[name] = value; } }; }
    append(...children) { children.forEach(child => this.appendChild(child)); }
    appendChild(child) { child.parentElement = this; child.parentNode = this; this.children.push(child); return child; }
    replaceChildren(...children) { this.children = []; this._text = ""; this.append(...children); }
    set textContent(value) { this.replaceChildren(); this._text = String(value); }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
    set innerHTML(_) { throw new Error("Device data must remain text, never raw HTML."); }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
  }
  const nodes = new Map(), opened = [];
  const runtime = {
    language, documentOverviewResult: data, document: { createElement: tag => new Element(tag), createTextNode: text => { const node = new Element("#text"); node.textContent = text; return node; } },
    documentNode(name) { if (!nodes.has(name)) nodes.set(name, new Element()); return nodes.get(name); },
    documentDisplayTime: value => `[time:${value}]`, openDocumentInboxEntry: async entry => { opened.push(entry); }
  };
  const render = runInNewContext(`${extract("documentText")}\n${extract("renderDocumentOverview")}\nrenderDocumentOverview`, runtime);
  render();
  const all = (root = runtime.documentNode("Overview")) => { const result = []; const visit = node => { result.push(node); node.children.forEach(visit); }; visit(root); return result; };
  return { runtime, render, nodes, opened, all, main: runtime.documentNode("Overview"), details: runtime.documentNode("OverviewDetails") };
}
let count = 0;
async function test(name, action) { await action(); console.log(`PASS ${name}`); count++; }

await test("fresh RAM GPU and aggregate disk usage remain distinct from saved hardware and sample readings", () => {
  for (const language of ["en", "zh"]) {
    const h = harness(fixture(), language), text = h.main.textContent;
    assert.match(text, /Fixture laptop/); assert.match(text, /Fixture CPU/); assert.match(text, /Fixture NVIDIA/);
    for (const value of [11, 16, 5, 1.5, 6, 4.5]) assert.match(text, new RegExp(`${value.toFixed(2)} GiB`));
    for (const value of [1.25, 2]) assert.match(text, new RegExp(`${value.toFixed(2)} TB`));
    assert.match(text, /750\.0 GB/);
    assert.match(text, /25(?:\.0)?%/); assert.match(text, /3200/); assert.match(text, /(?:2\s*[×x]\s*8|8(?:\.00)? GiB.*8(?:\.00)? GiB)/);
    assert.ok(text.includes(`[time:${freshAt}]`)); assert.ok(text.includes(`[time:${hardwareAt}]`));
    assert.ok(!text.includes(`[time:${savedAt}]`)); assert.ok(h.details.textContent.includes(`[time:${savedAt}]`));
    assert.ok(!h.details.textContent.includes(`[time:${hardwareAt}]`));
    assert.doesNotMatch(text, /18\.00 GiB|2\.00 GiB/); assert.match(h.details.textContent, /2\.00 GiB/);
    assert.doesNotMatch(text, /PRIVATE DISK MODEL|C:|D:|Compare|比较/);
  }
});

await test("unknown RAM GPU and disk metrics never become measured zero or use stale sample values", () => {
  for (const value of [null, undefined, "", false, -1, NaN, Infinity]) {
    const data = fixture(); data.currentMemory = { status: "available", readAt: freshAt, usedBytes: value, totalBytes: value, availableBytes: value, usedPercent: value };
    data.currentGpu = [{ adapterId: "GPU-fixture-a", name: "Fixture NVIDIA", status: "available", readAt: freshAt, totalBytes: value, usedBytes: value, freeBytes: value, utilizationPercent: value }];
    data.currentStorage = { status: "available", readAt: freshAt, totalBytes: value, usedBytes: value, freeBytes: value };
    const h = harness(data); assert.match(h.main.textContent, /Unknown|unavailable/i); assert.doesNotMatch(h.main.textContent, /\b0(?:\.0+)?(?: GiB| TB| GB|%)|11\.00 GiB|5\.00 GiB|1\.50 GiB|4\.50 GiB/);
  }
  const data = fixture(); data.currentMemory.status = "unavailable"; data.currentGpuRead.status = "unavailable"; data.currentGpu = []; data.currentStorage.status = "unavailable";
  Object.assign(data.gpus[0], { usedBytes: 1.5 * GiB, freeBytes: 4.5 * GiB, utilizationPercent: 25 });
  const h = harness(data); assert.doesNotMatch(h.main.textContent, /11\.00 GiB|5\.00 GiB|1\.50 GiB|4\.50 GiB|25(?:\.0)?%|1\.25 TB|750\.0 GB/);
  assert.match(h.main.textContent, /Unknown|unavailable/i);
});

await test("an actual zero usage reading stays visible rather than becoming unknown", () => {
  for (const fullyUsed of [false, true]) {
    const data = fixture(); data.currentMemory.usedBytes = fullyUsed ? data.currentMemory.totalBytes : 0; data.currentMemory.availableBytes = fullyUsed ? 0 : data.currentMemory.totalBytes; data.currentMemory.usedPercent = fullyUsed ? 100 : 0;
    data.currentGpu[0].usedBytes = fullyUsed ? data.currentGpu[0].totalBytes : 0; data.currentGpu[0].freeBytes = fullyUsed ? 0 : data.currentGpu[0].totalBytes; data.currentGpu[0].utilizationPercent = 0;
    data.currentStorage.usedBytes = fullyUsed ? data.currentStorage.totalBytes : 0; data.currentStorage.freeBytes = fullyUsed ? 0 : data.currentStorage.totalBytes;
    const h = harness(data); assert.match(h.main.textContent, /0\.00 GiB/); assert.match(h.main.textContent, /0\.0 GB/); assert.match(h.main.textContent, /0(?:\.0)?%/);
  }
});

await test("partial aggregate storage explicitly identifies its limited scope without showing drive letters", () => {
  for (const language of ["en", "zh"]) {
    const data = fixture(); data.currentStorage.status = "partial"; data.currentStorage.reason = "Only readable volumes are counted.";
    const h = harness(data, language); assert.match(h.main.textContent, /2\.00 TB/); assert.match(h.main.textContent, /部分|partial|only readable/i);
    assert.doesNotMatch(h.main.textContent, /C:|D:|PRIVATE DISK MODEL/);
  }
});

await test("inconsistent storage free space never creates negative used space or a fake zero reading", () => {
  for (const used of [undefined, -1_000_000_000_000]) {
    const data = fixture(); data.currentStorage.usedBytes = used; data.currentStorage.freeBytes = 3_000_000_000_000;
    const h = harness(data), storage = h.all().find(node => node.className.split(" ").includes("document-device-storage"));
    assert.ok(storage); assert.match(storage.textContent, /2\.00 TB/); assert.match(storage.textContent, /Unknown|unavailable/i);
    assert.doesNotMatch(storage.textContent, /-\d|0\.0+ GB|3\.00 TB/);
  }
});

await test("mixed RAM modules never advertise two identical eight-GiB modules", () => {
  for (const second of [{ capacityBytes: 16 * GiB, configuredSpeedMHz: 2666 }, { capacityBytes: 8 * GiB, configuredSpeedMHz: 2666 }, { capacityBytes: null, configuredSpeedMHz: null }]) {
    const data = fixture(); data.memoryModules[1] = second; const h = harness(data);
    assert.doesNotMatch(h.main.textContent, /2\s*[×x]\s*8(?:\.00)?(?:\s*GiB)?/);
    assert.match(h.main.textContent, /8(?:\.00)? GiB/);
    if (second.capacityBytes) { assert.match(h.main.textContent, /3200/); assert.match(h.main.textContent, /2666/); }
    else assert.match(h.main.textContent, /Unknown|unavailable/i);
  }
});

await test("multiple GPU readings stay attached to their own adapter rather than a summed total", () => {
  const data = fixture(); data.gpuModels = ["Adapter Alpha", "Adapter Beta"];
  data.gpus = [{ name: "Adapter Alpha", dedicatedCapacityBytes: 6 * GiB }, { name: "Adapter Beta", dedicatedCapacityBytes: 12 * GiB }];
  data.currentGpu = [{ adapterId: "GPU-alpha", name: "Adapter Alpha", status: "available", readAt: freshAt, totalBytes: 4 * GiB, usedBytes: 1 * GiB, freeBytes: 3 * GiB, utilizationPercent: 20 }, { adapterId: "GPU-beta", name: "Adapter Beta", status: "available", readAt: freshAt, totalBytes: 12 * GiB, usedBytes: 7 * GiB, freeBytes: 5 * GiB, utilizationPercent: 80 }];
  const h = harness(data);
  const adapterRegion = name => { let node = h.all().find(item => !item.children.length && item.textContent === name); while (node && !node.textContent.includes("GiB")) node = node.parentElement; assert.ok(node, `No capacity metrics for ${name}`); return node; };
  const alpha = adapterRegion("Adapter Alpha").textContent, beta = adapterRegion("Adapter Beta").textContent;
  assert.match(alpha, /1\.00 GiB/); assert.match(alpha, /4\.00 GiB/); assert.match(alpha, /3\.00 GiB/); assert.match(alpha, /20(?:\.0)?%/); assert.doesNotMatch(alpha, /Adapter Beta|7\.00 GiB|80(?:\.0)?%/);
  assert.match(beta, /7\.00 GiB/); assert.match(beta, /12\.00 GiB/); assert.match(beta, /5\.00 GiB/); assert.match(beta, /80(?:\.0)?%/); assert.doesNotMatch(beta, /Adapter Alpha|3\.00 GiB|20(?:\.0)?%/);
});

await test("purchase details are approximate historical notes and invalid detail states reveal no price", () => {
  for (const language of ["en", "zh"]) {
    const h = harness(fixture(), language), text = h.main.textContent;
    assert.match(text, /6[,\s]?500/); assert.match(text, /2021/); assert.match(text, /Carbon black/);
    assert.match(text, /(?:购入|购买|Purchase)/i);
    assert.match(text, /(?:约|about|approx(?:imately)?\.?|around|≈|~)\D{0,24}6[,\s]?500|6[,\s]?500\D{0,16}(?:约|左右|approx|about)/i);
    assert.match(text, /(?:约|about|approx(?:imately)?\.?|around|circa|≈|~)\D{0,16}2021|2021\D{0,12}(?:约|左右|approx|around)/i);
    assert.doesNotMatch(text, /(?:当前售价|现价|市场价|current price|market price)/i);
  }
  for (const status of ["model-mismatch", "unavailable", "invalid", "available"]) {
    const data = fixture(); data.deviceDetails.status = status; data.deviceDetails.model = "Different device";
    const h = harness(data); assert.doesNotMatch(h.main.textContent, /6[,\s]?500|2021|Carbon black/);
  }
});

await test("untrusted hardware names remain text and rendering never initiates a report read", () => {
  const data = fixture(); data.cpuModel = "<script>CPU</script>"; data.cpus[0].name = data.cpuModel; data.currentGpu[0].name = "<img src=x onerror=alert(1)>"; data.gpus[0].name = data.currentGpu[0].name; data.gpuModels = [data.currentGpu[0].name]; data.report = "reports/fixture.md";
  const h = harness(data); assert.match(h.main.textContent, /<script>CPU<\/script>/); assert.match(h.main.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(h.all().filter(node => ["SCRIPT", "IMG"].includes(node.tagName)).length, 0); assert.deepEqual(h.opened, []);
});

console.log(`Device overview UI ${count} checks passed.`);
