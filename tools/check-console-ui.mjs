#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDir, "..");
const baseUrl = new URL(process.argv[2] || "http://127.0.0.1:8898/");
const delay = milliseconds => new Promise(resolveDelay => setTimeout(resolveDelay, milliseconds));

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function staticChecks() {
  const htmlFiles = ["index.html", "music.html", "workspace.html"];
  const versions = new Set();
  for (const name of htmlFiles) {
    const source = readFileSync(join(projectRoot, name), "utf8");
    const cssVersion = source.match(/styles\.css\?v=([^"']+)/)?.[1];
    const appVersion = source.match(/app\.js\?v=([^"']+)/)?.[1];
    assert(cssVersion, `${name} is missing the stylesheet cache version`);
    assert(appVersion, `${name} is missing the app cache version`);
    assert(cssVersion === appVersion, `${name} uses different CSS and JS cache versions`);
    versions.add(cssVersion);
  }
  assert(versions.size === 1, "HTML entry points do not share one cache version");

  const appSource = readFileSync(join(projectRoot, "app.js"), "utf8");
  new Function(appSource);
  assert(existsSync(join(projectRoot, "blender_github_share.py")), "Blender GitHub Share backend is missing");
  assert(existsSync(join(projectRoot, "console_update.py")), "console updater backend is missing");
  assert(existsSync(join(projectRoot, "tools", "apply_update.py")), "portable update helper is missing");
  const manifest = JSON.parse(readFileSync(join(projectRoot, "app-manifest.json"), "utf8"));
  assert(manifest.version === "0.3.0", `unexpected app version: ${manifest.version}`);
  assert(manifest.repository === "tx74666/CodexControlConsole", "update repository is not configured");
  return Array.from(versions)[0];
}

function edgeExecutable() {
  const candidates = [
    process.env.EDGE_PATH,
    join(process.env["ProgramFiles(x86)"] || "", "Microsoft", "Edge", "Application", "msedge.exe"),
    join(process.env.ProgramFiles || "", "Microsoft", "Edge", "Application", "msedge.exe"),
    join(process.env.LOCALAPPDATA || "", "Microsoft", "Edge", "Application", "msedge.exe")
  ].filter(Boolean);
  return candidates.find(existsSync) || "";
}

async function waitForValue(read, predicate, message, timeoutMs = 12000, intervalMs = 80) {
  const deadline = Date.now() + timeoutMs;
  let lastValue;
  while (Date.now() < deadline) {
    lastValue = await read();
    if (predicate(lastValue)) return lastValue;
    await delay(intervalMs);
  }
  throw new Error(`${message}; last value: ${JSON.stringify(lastValue)}`);
}

class CdpClient {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
  }

  async open() {
    await new Promise((resolveOpen, rejectOpen) => {
      this.socket.addEventListener("open", resolveOpen, { once: true });
      this.socket.addEventListener("error", rejectOpen, { once: true });
    });
    this.socket.addEventListener("message", event => {
      const message = JSON.parse(event.data);
      if (!message.id || !this.pending.has(message.id)) return;
      const { resolve: resolveCall, reject: rejectCall } = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) rejectCall(new Error(message.error.message || "CDP command failed"));
      else resolveCall(message.result || {});
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolveCall, rejectCall) => {
      this.pending.set(id, { resolve: resolveCall, reject: rejectCall });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket.close();
  }
}

async function createPageClient(port, url) {
  const target = await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: "PUT" })
    .then(response => response.json());
  const client = new CdpClient(target.webSocketDebuggerUrl);
  await client.open();
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  return client;
}

async function evaluate(client, expression, awaitPromise = false) {
  const result = await client.send("Runtime.evaluate", {
    expression,
    awaitPromise,
    returnByValue: true
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text || "Page evaluation failed");
  }
  return result.result?.value;
}

async function waitForDocument(client) {
  await waitForValue(
    () => evaluate(client, "document.readyState"),
    value => value === "interactive" || value === "complete",
    "page did not finish loading"
  );
}

async function clickModule(client, id) {
  const clicked = await evaluate(client, `(() => {
    const link = document.querySelector('.module-link[data-module-id="${id}"]');
    if (!link) return false;
    link.click();
    return true;
  })()`);
  assert(clicked, `module link not found: ${id}`);
  await waitForValue(
    () => evaluate(client, "document.querySelector('.module-link.active')?.dataset.moduleId || ''"),
    value => value === id,
    `module did not activate: ${id}`,
    3000,
    30
  );
}

const transitionSampleExpression = `(() => {
  const stage = document.querySelector('.blender-view-stage');
  const leaving = document.querySelector('.blender-subview.leaving');
  const active = document.querySelector('.blender-subtab.active')?.dataset.blenderViewTarget || '';
  if (!stage) return { switching: false, active, visibleOldWidth: 0, residualCount: 0 };
  const switching = stage.classList.contains('switching');
  if (!leaving) return { switching, active, visibleOldWidth: 0, residualCount: 0 };
  const stageRect = stage.getBoundingClientRect();
  const leavingRect = leaving.getBoundingClientRect();
  let residualCount = 0;
  for (const element of leaving.querySelectorAll('*')) {
    const style = getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    const overlapWidth = Math.max(0, Math.min(stageRect.right, rect.right) - Math.max(stageRect.left, rect.left));
    const overlapHeight = Math.max(0, Math.min(stageRect.bottom, rect.bottom) - Math.max(stageRect.top, rect.top));
    if (overlapWidth > 0 && overlapHeight > 0) residualCount += 1;
  }
  return {
    switching,
    active,
    visibleOldWidth: Math.max(0, Math.min(stageRect.right, leavingRect.right) - Math.max(stageRect.left, leavingRect.left)),
    residualCount
  };
})()`;

async function checkBlenderTransition(client, target) {
  const clicked = await evaluate(client, `(() => {
    const button = document.querySelector('[data-blender-view-target="${target}"]');
    if (!button) return false;
    button.click();
    return true;
  })()`);
  assert(clicked, `Blender view button not found: ${target}`);

  const samples = [];
  let sawSwitching = false;
  const deadline = Date.now() + 1800;
  while (Date.now() < deadline) {
    const sample = await evaluate(client, transitionSampleExpression);
    samples.push(sample);
    if (sample.switching) sawSwitching = true;
    if (sawSwitching && !sample.switching) break;
    await delay(10);
  }

  assert(sawSwitching, `Blender transition did not start: ${target}`);
  const switchingSamples = samples.filter(sample => sample.switching);
  const finalPaint = switchingSamples[switchingSamples.length - 1];
  const finalState = samples[samples.length - 1];
  assert(finalPaint?.visibleOldWidth === 0, `${target} transition hid the old view before it fully exited`);
  assert(finalPaint?.residualCount === 0, `${target} transition left ${finalPaint?.residualCount} child elements visible`);
  assert(finalState.active === target && !finalState.switching, `${target} transition did not settle cleanly`);
}

async function runBrowserChecks(client) {
  await waitForDocument(client);
  await waitForValue(
    () => evaluate(client, "document.querySelector('.module-link.active')?.dataset.moduleId || ''"),
    value => value === "blender",
    "Blender module did not initialize"
  );

  await waitForValue(
    () => evaluate(client, "document.querySelectorAll('#randomRealmBlenderProject option').length"),
    value => value > 0,
    "Blender projects did not load",
    20000,
    120
  );

  await waitForValue(
    () => evaluate(client, "document.querySelector('#consoleUpdateCurrent')?.textContent?.trim() || ''"),
    value => value === "v0.3.0",
    "update status did not load the current version",
    25000,
    120
  );
  const updateState = await evaluate(client, `({
    current: document.querySelector('#consoleUpdateCurrent')?.textContent?.trim() || '',
    auto: document.querySelector('#consoleUpdateAuto')?.checked,
    controls: Boolean(document.querySelector('#consoleUpdateRefresh') && document.querySelector('#consoleUpdateInstall')),
    topVisible: document.querySelector('#consoleUpdateTop')?.getBoundingClientRect().width > 0
  })`);
  assert(updateState.current === "v0.3.0" && typeof updateState.auto === "boolean" && updateState.controls, `update controls are incomplete: ${JSON.stringify(updateState)}`);
  assert(!updateState.topVisible, `inactive update control still occupies the top bar: ${JSON.stringify(updateState)}`);

  const selectedX = await evaluate(client, `(() => {
    const select = document.querySelector('#blenderGithubProject');
    if (!select) return { found: false, values: [] };
    const options = Array.from(select.options);
    const target = options.find(option => option.value.replace(/\\\\/g, '/').toLowerCase().endsWith('/character/x/x.blend'));
    if (!target) return { found: false, values: options.map(option => option.value) };
    select.value = target.value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return { found: true, value: target.value };
  })()`);
  assert(selectedX.found, `X Blender project was not listed: ${JSON.stringify(selectedX.values)}`);
  await waitForValue(
    () => evaluate(client, `({
      project: document.querySelector('#blenderGithubProject')?.value || '',
      state: document.querySelector('#blenderGithubState')?.dataset.state || '',
      busy: document.querySelector('#blenderGithubSharePanel')?.classList.contains('busy') || false
    })`),
    value => value.project.replace(/\\/g, "/").toLowerCase().endsWith("/character/x/x.blend")
      && ["initialized", "dirty", "committed", "pendingPush", "behind", "synced"].includes(value.state)
      && !value.busy,
    "Blender GitHub Share did not load X",
    20000,
    120
  );
  const shareState = await evaluate(client, `({
    visible: !document.querySelector('#blenderGithubSharePanel')?.hidden,
    title: document.querySelector('#blenderGithubSharePanel h2')?.textContent?.trim() || '',
    state: document.querySelector('#blenderGithubState')?.dataset.state || '',
    cards: document.querySelectorAll('#blenderGithubBlendCards .blender-github-blend-card').length,
    selectedCards: document.querySelectorAll('#blenderGithubBlendCards .blender-github-blend-card[aria-selected="true"]').length,
    currentFile: document.querySelector('#blenderGithubBlendCards .blender-github-blend-card[aria-selected="true"] strong')?.textContent?.trim() || '',
    version: document.querySelector('#blenderGithubBlendCards .blender-github-blend-card[aria-selected="true"] .blender-github-version')?.textContent?.trim() || '',
    refreshText: document.querySelector('#blenderGithubRefresh')?.textContent?.trim() || '',
    refreshFontSize: parseFloat(getComputedStyle(document.querySelector('#blenderGithubRefresh')).fontSize) || 0,
    desktopDisabled: document.querySelector('#blenderGithubDesktop')?.disabled,
    folderDisabled: document.querySelector('#blenderGithubFolder')?.disabled,
    openDisabled: document.querySelector('#blenderGithubOpen')?.disabled,
    noticeHidden: document.querySelector('#blenderGithubStatus')?.hidden,
    removedControls: ['blenderGithubBranch', 'blenderGithubRemote', 'blenderGithubRepository', 'blenderGithubInitialize', 'blenderGithubCommit', 'blenderGithubPush', 'blenderGithubChanges'].filter(id => document.getElementById(id)).length
  })`);
  assert(shareState.visible, "Blender GitHub Share panel is hidden");
  assert(shareState.title === "GitHub Coop", `GitHub Coop title is missing: ${JSON.stringify(shareState)}`);
  assert(shareState.cards >= 1 && shareState.selectedCards === 1, `blend cards are not ready: ${JSON.stringify(shareState)}`);
  assert(shareState.currentFile === "X.blend", `X blend card was not selected: ${JSON.stringify(shareState)}`);
  assert(/^V(?:\d|--)/.test(shareState.version), `compact version is invalid: ${JSON.stringify(shareState)}`);
  assert(shareState.refreshText && shareState.refreshFontSize >= 16, `refresh control is not visible: ${JSON.stringify(shareState)}`);
  assert(!shareState.desktopDisabled && !shareState.folderDisabled && !shareState.openDisabled, `project links are unavailable: ${JSON.stringify(shareState)}`);
  assert(shareState.noticeHidden, `passive Ready text is still visible: ${JSON.stringify(shareState)}`);
  assert(shareState.removedControls === 0, `verbose Git controls are still mounted: ${JSON.stringify(shareState)}`);

  if (process.env.CONSOLE_UI_SCREENSHOT) {
    const screenshotModule = process.env.CONSOLE_UI_SCREENSHOT_MODULE || "blender";
    if (screenshotModule !== "blender") await clickModule(client, screenshotModule);
    if (process.env.CONSOLE_UI_THEME) {
      await evaluate(client, `(() => {
        const target = ${JSON.stringify(process.env.CONSOLE_UI_THEME)};
        if (document.documentElement.dataset.theme !== target) document.querySelector('#themeToggle')?.click();
      })()`);
      await delay(120);
    }
    const screenshotSelector = process.env.CONSOLE_UI_SCREENSHOT_SELECTOR || "#blenderGithubSharePanel";
    await evaluate(client, `document.querySelector(${JSON.stringify(screenshotSelector)})?.scrollIntoView({ block: 'start' })`);
    await delay(180);
    const screenshot = await client.send("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: false
    });
    writeFileSync(process.env.CONSOLE_UI_SCREENSHOT, Buffer.from(screenshot.data, "base64"));
    if (screenshotModule !== "blender") await clickModule(client, "blender");
  }

  const lazyState = await evaluate(client, `({
    musicCards: document.querySelectorAll('.music-dock .track-card').length,
    wallpaperCards: document.querySelectorAll('.wallpaper-card').length,
    steamRoot: document.querySelector('#steamworkAssetRoot')?.textContent?.trim() || ''
  })`);
  assert(lazyState.musicCards === 0, "music data loaded before the Music module was opened");
  assert(lazyState.wallpaperCards === 0, "wallpaper data loaded before the Wallpaper module was opened");
  assert(lazyState.steamRoot === "", "Steamwork data loaded before the Steamwork module was opened");

  const helperBackground = await evaluate(client, `(() => {
    const style = getComputedStyle(document.body, '::before');
    return [style.position, style.width, style.height, style.backgroundImage, style.backgroundSize];
  })()`);

  await checkBlenderTransition(client, "builder");
  const builderBackground = await evaluate(client, `(() => {
    const style = getComputedStyle(document.body, '::before');
    return [style.position, style.width, style.height, style.backgroundImage, style.backgroundSize];
  })()`);
  assert(JSON.stringify(helperBackground) === JSON.stringify(builderBackground), "Blender views use different page backgrounds");
  await checkBlenderTransition(client, "helper");

  await clickModule(client, "music");
  await waitForValue(
    () => evaluate(client, "document.querySelectorAll('.music-dock .track-card').length"),
    value => value > 0,
    "Music did not load on first open",
    10000
  );

  await clickModule(client, "wallpaper");
  await waitForValue(
    () => evaluate(client, "document.querySelectorAll('.wallpaper-card').length"),
    value => value > 0,
    "wallpapers did not load on first open",
    10000
  );

  await clickModule(client, "steamwork");
  await waitForValue(
    () => evaluate(client, "document.querySelector('#steamworkAssetRoot')?.textContent?.trim() || ''"),
    value => Boolean(value),
    "Steamwork assets did not load on first open",
    10000
  );

  const layoutState = await evaluate(client, `({
    viewportWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    errors: window.__consoleCheckErrors || []
  })`);
  assert(layoutState.scrollWidth <= layoutState.viewportWidth, "page has horizontal overflow");
  assert(layoutState.errors.length === 0, `page reported errors: ${layoutState.errors.join("; ")}`);

  await clickModule(client, "blender");
  await waitForValue(
    () => evaluate(client, "document.querySelector('#blenderGithubState')?.dataset.state || ''"),
    value => ["initialized", "dirty", "committed", "pendingPush", "behind", "synced"].includes(value),
    "Blender GitHub Share did not restore after returning to Blender",
    10000
  );

  await client.send("Emulation.setDeviceMetricsOverride", {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: false
  });
  await delay(120);
  const narrowLayout = await evaluate(client, `({
    viewportWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    shellWidth: document.querySelector('.app-shell')?.getBoundingClientRect().width || 0,
    subnavWidth: document.querySelector('.blender-subnav')?.getBoundingClientRect().width || 0,
    overflowers: Array.from(document.querySelectorAll('body *')).map(element => {
      const rect = element.getBoundingClientRect();
      return {
        tag: element.tagName,
        id: element.id || '',
        className: String(element.className || '').slice(0, 120),
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
        scrollWidth: element.scrollWidth
      };
    }).filter(item => item.left < -1 || item.right > document.documentElement.clientWidth + 1).slice(0, 20)
  })`);
  assert(narrowLayout.scrollWidth <= narrowLayout.viewportWidth, `narrow layout has horizontal overflow: ${JSON.stringify(narrowLayout)}`);
  assert(narrowLayout.shellWidth <= narrowLayout.viewportWidth, `app shell exceeds the narrow viewport: ${JSON.stringify(narrowLayout)}`);
}

async function main() {
  const cacheVersion = staticChecks();
  assert(typeof WebSocket === "function", "Node.js 22 or newer is required for the browser check");
  await fetch(baseUrl, { cache: "no-store" }).then(response => {
    assert(response.ok, `console server returned HTTP ${response.status}`);
  }).catch(error => {
    throw new Error(`cannot reach ${baseUrl.href}; start Control Console first (${error.message})`);
  });

  const edge = edgeExecutable();
  assert(edge, "Microsoft Edge was not found; set EDGE_PATH to msedge.exe");
  const profileDir = await mkdtemp(join(tmpdir(), "codex-console-check-"));
  const port = 9300 + Math.floor(Math.random() * 500);
  const browser = spawn(edge, [
    "--headless=new",
    "--disable-background-networking",
    "--disable-extensions",
    "--no-first-run",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    "about:blank"
  ], { stdio: "ignore", windowsHide: true });

  let client;
  try {
    await waitForValue(
      async () => fetch(`http://127.0.0.1:${port}/json/version`).then(response => response.ok).catch(() => false),
      Boolean,
      "Edge debugging endpoint did not start",
      10000,
      100
    );
    client = await createPageClient(port, new URL("blender.html", baseUrl).href);
    await client.send("Emulation.setDeviceMetricsOverride", {
      width: 1280,
      height: 800,
      deviceScaleFactor: 1,
      mobile: false
    });
    await client.send("Page.reload", { ignoreCache: true });
    await client.send("Runtime.evaluate", {
      expression: `window.addEventListener('error', event => {
        window.__consoleCheckErrors = window.__consoleCheckErrors || [];
        window.__consoleCheckErrors.push(event.message || 'unknown error');
      })`
    });
    await runBrowserChecks(client);
    console.log(`PASS Control Console UI (${cacheVersion})`);
  } finally {
    client?.close();
    const browserExit = browser.exitCode === null
      ? new Promise(resolveExit => browser.once("exit", resolveExit))
      : Promise.resolve();
    browser.kill();
    await Promise.race([browserExit, delay(3000)]);
    try {
      rmSync(profileDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 120 });
    } catch (error) {
      console.warn(`WARN temporary browser profile cleanup was deferred: ${error.message}`);
    }
  }
}

main().catch(error => {
  console.error(`FAIL ${error.message}`);
  process.exitCode = 1;
});
