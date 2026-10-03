#!/usr/bin/env node
// Real Fetch/Origin behavior against a disposable gateway, never the user's live inbox.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import http from "node:http";

const repo = fileURLToPath(new URL("../", import.meta.url));
let playwright;
try { playwright = await import("playwright"); }
catch {
  const packages = process.env.CODEX_NODE_MODULES || join(dirname(process.execPath), "..", "node_modules");
  playwright = createRequire(join(packages, "package.json"))("playwright");
}
const candidates = [process.env.CODEX_BROWSER_EXECUTABLE, playwright.chromium.executablePath(),
  join(process.env.ProgramFiles || "", "Google", "Chrome", "Application", "chrome.exe"),
  join(process.env["ProgramFiles(x86)"] || "", "Microsoft", "Edge", "Application", "msedge.exe")];
const executablePath = candidates.find(value => value && existsSync(value));
assert.ok(executablePath, "No installed Chromium browser; set CODEX_BROWSER_EXECUTABLE. No downloads are performed.");
const python = process.env.CODEX_PYTHON || process.env.PYTHON || "python";
const fixture = spawn(python, [join(repo, "tools", "phone-origin-browser-fixture.py")], {
  cwd: repo, windowsHide: true, stdio: ["pipe", "pipe", "pipe"]
});
const replies = [], pending = [];
let diagnostic = "";
fixture.stderr.on("data", value => { diagnostic += value.toString(); });
createInterface({ input: fixture.stdout }).on("line", line => {
  const value = JSON.parse(line);
  if (pending.length) pending.shift().resolve(value);
  else replies.push(value);
});
fixture.on("exit", code => {
  for (const item of pending.splice(0)) item.reject(new Error(`Fixture exited (${code}): ${diagnostic}`));
});
function nextReply() {
  if (replies.length) return Promise.resolve(replies.shift());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Fixture response timed out: ${diagnostic}`)), 10000);
    pending.push({ resolve(value) { clearTimeout(timer); resolve(value); }, reject(error) { clearTimeout(timer); reject(error); } });
  });
}
function command(command, options = {}) {
  const result = nextReply();
  fixture.stdin.write(JSON.stringify({ command, ...options }) + "\n");
  return result;
}
async function rawPost(origin, suppliedOrigin, body) {
  return new Promise((resolve, reject) => {
    const encoded = Buffer.from(JSON.stringify(body));
    const request = http.request(new URL("/api/phone/pair", origin), {
      method: "POST", headers: { Origin: suppliedOrigin, "Content-Type": "application/json",
        "Content-Length": encoded.length, "X-Codex-Phone": "1", "Sec-Fetch-Site": "same-origin" }
    }, response => {
      let data = "";
      response.on("data", chunk => { data += chunk; });
      response.on("end", () => resolve({ status: response.statusCode, body: JSON.parse(data) }));
    });
    request.on("error", reject);
    request.end(encoded);
  });
}
async function postFromPage(page, code, referrerPolicy) {
  return page.evaluate(async ({ code, referrerPolicy }) => {
    const response = await fetch("/api/phone/pair", {
      method: "POST", mode: "same-origin", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Codex-Phone": "1" },
      body: JSON.stringify({ code, remember: false }), ...(referrerPolicy ? { referrerPolicy } : {})
    });
    return { status: response.status, body: await response.json() };
  }, { code, referrerPolicy });
}
let browser, tests = 0;
async function test(name, run) {
  await run();
  console.log(`PASS ${name}`);
  tests++;
}
try {
  const { origin, png } = await nextReply();
  browser = await playwright.chromium.launch({ executablePath, headless: true,
    args: ["--no-proxy-server", "--disable-background-networking"] });
  await test("legacy no-referrer behavior is recorded and explicit request policies preserve the real origin", async () => {
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      const { code } = await command("renew");
      await command("observed");
      await page.goto(origin + "/__origin_browser/no-referrer");
      const result = await postFromPage(page, code);
      const capture = await command("observed");
      const observedOrigin = capture.requests.find(item => item.path === "/api/phone/pair").origin;
      // Chromium releases can preserve Origin here; WebKit can serialize it as null.
      // Record the actual engine result instead of claiming a reproduction it did not produce.
      if (observedOrigin === "null") {
        assert.equal(result.status, 403);
        assert.match(result.body.error, /请求来源不匹配/);
        console.log("INFO Installed Chromium reproduced the legacy Origin:null failure.");
      } else {
        assert.equal(observedOrigin, origin);
        assert.equal(result.status, 200);
        console.log("INFO Installed Chromium preserves legacy Origin; iPhone WebKit reproduction remains a device check.");
      }
      for (const policy of ["same-origin", "strict-origin"]) {
        const invitation = await command("renew");
        await command("observed");
        const fixed = await postFromPage(page, invitation.code, policy);
        assert.equal(fixed.status, 200, fixed.body.error);
        assert.equal((await command("observed")).requests.find(item => item.path === "/api/phone/pair").origin, origin);
      }
    } finally { await context.close(); }
  });
  await test("same-origin response policy fixes POST without a per-request override", async () => {
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      const { code } = await command("renew");
      await page.goto(origin + "/__origin_browser/same-origin");
      await command("observed");
      assert.equal((await postFromPage(page, code)).status, 200);
      assert.equal((await command("observed")).requests.find(item => item.path === "/api/phone/pair").origin, origin);
    } finally { await context.close(); }
  });
  await test("current QR UI pairs, remembers, and uploads a visible original image with legacy page headers", async () => {
    await command("legacy-headers", { enabled: true });
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    try {
      const page = await context.newPage();
      const { qrToken } = await command("renew");
      await command("observed");
      const response = await page.goto(origin + "/?tab=transfer#qrToken=" + qrToken);
      assert.equal(response.headers()["referrer-policy"], "no-referrer");
      await page.locator("#connectionLabel[data-connected='true']").waitFor();
      assert.equal(new URL(page.url()).hash, "", "one-use invitation is removed from visible history");
      const cookies = await context.cookies(origin);
      assert.ok(cookies.some(item => item.name === "codex_phone_device" && item.httpOnly));
      await page.locator("#phoneTransferPanel textarea").fill("Browser Origin fixture image");
      await page.locator("#phoneTransferPanel input[type=file]").first().setInputFiles({
        name: "来源回归.png", mimeType: "image/png", buffer: Buffer.from(png, "base64")
      });
      await page.getByRole("button", { name: "上传并发送", exact: true }).click();
      await page.locator(".transfer-message").filter({ hasText: "Browser Origin fixture image" }).waitFor();
      const image = page.locator(".transfer-message img").first();
      await image.waitFor();
      await image.evaluate(element => element.complete && element.naturalWidth > 0
        ? Promise.resolve() : new Promise((resolve, reject) => { element.onload = resolve; element.onerror = reject; }));
      const stored = await page.evaluate(async () => (await fetch("/api/phone/transfer/messages", { mode: "same-origin" })).json());
      assert.equal(stored.messages[0].attachments[0].name, "来源回归.png");
      const original = await page.evaluate(async url => {
        const response = await fetch(url, { mode: "same-origin" });
        return { status: response.status, bytes: Array.from(new Uint8Array(await response.arrayBuffer())) };
      }, stored.messages[0].attachments[0].url);
      assert.equal(original.status, 200);
      assert.deepEqual(Buffer.from(original.bytes), Buffer.from(png, "base64"));
      const capture = await command("observed");
      for (const request of capture.requests.filter(item => item.method === "POST")) assert.equal(request.origin, origin);
    } finally { await context.close(); await command("legacy-headers", { enabled: false }); }
  });
  await test("current manual PIN UI pairs with same-origin response headers", async () => {
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      const { code } = await command("renew");
      const response = await page.goto(origin + "/?tab=transfer");
      assert.equal(response.headers()["referrer-policy"], "same-origin");
      await page.locator("#pairSubmit:not([disabled])").waitFor();
      await page.locator("#pairCode").fill(code);
      await command("observed");
      await page.locator("#pairSubmit").click();
      try { await page.locator("#connectionLabel[data-connected='true']").waitFor({ timeout: 10000 }); }
      catch (error) {
        const notice = await page.locator("#pairNotice").innerText();
        const requests = (await command("observed")).requests;
        throw new Error(`Manual PIN UI did not connect: ${notice}; requests=${JSON.stringify(requests)}`, { cause: error });
      }
      assert.equal((await command("observed")).requests.find(item => item.path === "/api/phone/pair").origin, origin);
    } finally { await context.close(); }
  });
  await test("null and attacker origins remain rejected even with a same-origin Fetch metadata claim", async () => {
    const { code } = await command("renew");
    for (const invalid of ["null", "https://evil.test"]) {
      const result = await rawPost(origin, invalid, { code, remember: false });
      assert.equal(result.status, 403);
      assert.match(result.body.error, /请求来源不匹配/);
    }
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      await page.goto(origin + "/__origin_browser/same-origin");
      assert.equal((await postFromPage(page, code)).status, 200, "rejected requests must not consume the invitation");
    } finally { await context.close(); }
  });
  console.log(`Phone Origin real-browser checks passed (${tests} checks).`);
} finally {
  if (browser) await browser.close();
  if (fixture.exitCode === null) {
    try { await command("stop"); } finally { fixture.stdin.end(); }
    await new Promise(resolve => fixture.exitCode === null ? fixture.once("exit", resolve) : resolve());
  }
}
