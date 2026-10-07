import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "app.js"), "utf8");
const start = source.indexOf("const i18n = {");
const end = source.indexOf("\n};", start);
assert.ok(start >= 0 && end > start, "Use the application's actual display dictionary");
const context = vm.createContext({});
vm.runInContext(source.slice(start, end + 3) + "\nthis.copy = i18n;", context);
const { zh, en } = context.copy;
let count = 0;
function check(name, run) { run(); count++; console.log(`PASS ${name}`); }

check("display strings and callbacks contain no legacy UTF-8 mojibake", () => {
  for (const [key, value] of Object.entries(zh)) {
    assert.doesNotMatch(String(value), /[\u0080-\u009f]|[åæ]|ï¼|ã€/u, key);
  }
});
check("feedback limits use readable Chinese and retain dynamic values", () => {
  assert.equal(zh.feedbackDescriptionShort, "请至少写 10 个字。");
  assert.equal(zh.feedbackImageTooLarge, "截图不能超过 5 MB。");
  assert.equal(zh.feedbackImagesTotalTooLarge(20), "截图合计不能超过 20 MB。");
  assert.equal(zh.feedbackSent(7), "已发送 · 今天还可发送 7 条");
  assert.equal(zh.feedbackFailed("稍后重试"), "发送失败：稍后重试");
});
check("lyrics labels keep the fallback and both range branches", () => {
  assert.equal(zh.lyricsTimingTarget("", 3), "正在调：这一格 · 第 3 行");
  assert.equal(zh.lyricsTimingRangeTitle("A", "A"), "精调：A");
  assert.equal(zh.lyricsTimingRangeTitle("A", "B"), "精调：A 到 B");
});
check("update and material labels retain both existing conditional branches", () => {
  assert.equal(zh.worldUpdateConfirm("1.2.3", true), "将自动更新 Codex World v1.2.3。现在继续？");
  assert.equal(zh.worldUpdateConfirm("1.2.3", false), "将自动安装 Codex World v1.2.3。现在继续？");
  assert.equal(zh.materialCandidateMeta("package", "5 MB"), "压缩包 · 5 MB");
  assert.equal(zh.materialCandidateMeta("image", "2 MB"), "贴图 · 2 MB");
});
check("English feedback and conditional labels still work", () => {
  assert.equal(en.feedbackDescriptionShort, "Please enter at least 10 characters.");
  assert.equal(en.feedbackImagesTotalTooLarge(20), "Screenshots must total 20 MB or less.");
  assert.equal(en.materialCandidateMeta("package", "5 MB"), "Package · 5 MB");
  assert.equal(en.materialCandidateMeta("image", "2 MB"), "Texture · 2 MB");
});
console.log(`PASS ${count} readable display-copy checks`);
