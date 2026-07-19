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
const allowEmptyMedia = process.env.CONSOLE_UI_ALLOW_EMPTY_MEDIA === "true";
const allowAvailableUpdates = process.env.CONSOLE_UI_ALLOW_AVAILABLE_UPDATES === "true";
const allowCloudProjects = process.env.CONSOLE_UI_ALLOW_CLOUD_PROJECTS === "true";
let expectedAppVersion = "";

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
  const coopCatalog = JSON.parse(readFileSync(join(projectRoot, "github-coop.json"), "utf8"));
  assert(
    coopCatalog.repositories?.length === 1
      && coopCatalog.repositories[0]?.name === "Blender Projects"
      && coopCatalog.repositories[0]?.repositoryUrl === "https://github.com/tx74666/Blender-projects.git",
    "GitHub Coop catalog must contain only the unified Blender Projects repository"
  );
  assert(existsSync(join(projectRoot, "console_update.py")), "console updater backend is missing");
  assert(existsSync(join(projectRoot, "world_update.py")), "Codex World updater backend is missing");
  assert(existsSync(join(projectRoot, "app_uninstall.py")), "clean uninstall backend is missing");
  assert(existsSync(join(projectRoot, "tools", "apply_update.py")), "portable update helper is missing");
  assert(existsSync(join(projectRoot, "desktop_layout.py")), "desktop layout backend is missing");
  assert(existsSync(join(projectRoot, "feedback_service.py")), "feedback backend is missing");
  assert(existsSync(join(projectRoot, "services", "feedback-relay", "src", "index.js")), "feedback relay is missing");
  assert(existsSync(join(projectRoot, "tools", "DesktopLayout.ps1")), "generic desktop layout helper is missing");
  const manifest = JSON.parse(readFileSync(join(projectRoot, "app-manifest.json"), "utf8"));
  assert(manifest.version === "0.5.1", `unexpected app version: ${manifest.version}`);
  expectedAppVersion = manifest.version;
  assert(manifest.repository === "tx74666/CodexControlConsole", "update repository is not configured");
  const consoleHtml = readFileSync(join(projectRoot, "index.html"), "utf8");
  assert(
    /id="updateProductConsole"[^>]+href="https:\/\/github\.com\/tx74666\/CodexControlConsole\/releases\/latest"/.test(consoleHtml),
    "Codex Console download card is not linked to GitHub Releases"
  );
  assert(
    /id="updateProductWorld"[^>]+href="https:\/\/github\.com\/tx74666\/CodexWorldConsole\/releases\/latest"/.test(consoleHtml),
    "Codex World download card is not linked to GitHub Releases"
  );
  assert(/id="consoleUninstall"/.test(consoleHtml), "product uninstall control is missing");
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
    if (link) {
      link.click();
      return true;
    }
    if (typeof activateModule === 'function' && document.querySelector('[data-module-panel="${id}"]')) {
      activateModule('${id}', true, { allowArchived: true });
      return true;
    }
    return false;
  })()`);
  assert(clicked, `module link not found: ${id}`);
  await waitForValue(
    () => evaluate(client, "document.querySelector('.module-link.active')?.dataset.moduleId || (typeof activeModuleId === 'string' ? activeModuleId : '')"),
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
  const languageToggleState = await evaluate(client, `(() => {
    const button = document.querySelector('#languageToggle');
    const originalLanguage = language;
    language = 'en';
    applyLanguage();
    const english = button?.textContent?.trim() || '';
    language = 'zh';
    applyLanguage();
    const chinese = button?.textContent?.trim() || '';
    language = originalLanguage;
    applyLanguage();
    return { english, chinese };
  })()`);
  assert(
    languageToggleState.english === "EN" && languageToggleState.chinese === "CN",
    `language indicator is reversed: ${JSON.stringify(languageToggleState)}`
  );
  await clickModule(client, "blender");

  await waitForValue(
    () => evaluate(client, "document.querySelectorAll('#randomRealmBlenderProject option').length"),
    value => value > 0,
    "Blender projects did not load",
    20000,
    120
  );

  await waitForValue(
    () => evaluate(client, "document.querySelector('#consoleUpdateCurrent')?.textContent?.trim() || ''"),
    value => value === `v${expectedAppVersion}`,
    "update status did not load the current version",
    25000,
    120
  );
  await waitForValue(
    () => evaluate(client, "!productUpdateBusy && Boolean(productUpdateStates.console) && Boolean(productUpdateStates.world)"),
    Boolean,
    "product update checks did not settle",
    60000,
    150
  );
  const updateState = await evaluate(client, `({
    current: document.querySelector('#consoleUpdateCurrent')?.textContent?.trim() || '',
    auto: document.querySelector('#consoleUpdateAuto')?.checked,
    controls: Boolean(document.querySelector('#consoleUpdateRefresh') && document.querySelector('#consoleUpdateInstall') && document.querySelector('#consoleUninstall')),
    products: document.querySelectorAll('[data-update-product]').length,
    badges: Array.from(document.querySelectorAll('.update-product-badge')).map(item => item.textContent?.trim() || ''),
    topVisible: document.querySelector('#consoleUpdateTop')?.getBoundingClientRect().width > 0,
    consoleDownload: document.querySelector('#updateProductConsole')?.href || '',
    worldDownload: document.querySelector('#updateProductWorld')?.href || ''
  })`);
  assert(
    updateState.current === `v${expectedAppVersion}`
      && typeof updateState.auto === "boolean"
      && updateState.controls
      && updateState.products === 2
      && updateState.badges.every(Boolean)
      && updateState.consoleDownload.includes('/tx74666/CodexControlConsole/releases/')
      && updateState.worldDownload.includes('/tx74666/CodexWorldConsole/releases/'),
    `update controls are incomplete: ${JSON.stringify(updateState)}`
  );
  if (!allowAvailableUpdates) {
    assert(!updateState.topVisible, `inactive update control still occupies the top bar: ${JSON.stringify(updateState)}`);
  }

  const updateBannerState = await evaluate(client, `(() => {
    const originalStates = productUpdateStates;
    const originalProduct = selectedUpdateProduct;
    productUpdateStates = {
      console: {
        currentVersion: '0.3.4', latestVersion: '0.3.5', available: true,
        autoCheck: true, canInstall: true,
        releaseUrl: 'https://github.com/tx74666/CodexControlConsole/releases/tag/v0.3.5'
      },
      world: {
        currentVersion: '0.1.6', latestVersion: '0.1.7', available: true,
        installed: true, autoCheck: true, canInstall: true,
        releaseUrl: 'https://github.com/tx74666/CodexWorldConsole/releases/tag/v0.1.7'
      }
    };
    selectUpdateProduct('console', { persist: false });
    renderConsoleUpdate();
    const button = document.querySelector('#consoleUpdateTop');
    const bothAvailable = {
      visible: !button?.hidden && button?.getBoundingClientRect().width > 0,
      text: button?.textContent?.trim() || '',
      width: button?.getBoundingClientRect().width || 0,
      availableBadges: document.querySelectorAll('.update-product-badge.available').length
    };
    productUpdateStates.world = { ...productUpdateStates.world, latestVersion: '0.1.6', available: false };
    renderConsoleUpdate();
    const oneAvailable = { text: button?.textContent?.trim() || '', product: button?.dataset.product || '' };
    productUpdateStates.console = { ...productUpdateStates.console, latestVersion: '0.3.4', available: false };
    renderConsoleUpdate();
    const hiddenWhenCurrent = Boolean(button?.hidden);
    productUpdateStates = originalStates;
    selectedUpdateProduct = originalProduct;
    renderConsoleUpdate();
    return { bothAvailable, oneAvailable, hiddenWhenCurrent };
  })()`);
  assert(
    updateBannerState.bothAvailable.visible
      && updateBannerState.bothAvailable.text.startsWith('2 ')
      && updateBannerState.bothAvailable.width >= 120
      && updateBannerState.bothAvailable.availableBadges === 2
      && updateBannerState.oneAvailable.text.endsWith('Codex Console v0.3.5')
      && updateBannerState.oneAvailable.product === 'console'
      && updateBannerState.hiddenWhenCurrent,
    `top update area does not reflect version availability: ${JSON.stringify(updateBannerState)}`
  );

  const oneClickUpdate = await evaluate(client, `(async () => {
    const originalStates = productUpdateStates;
    const originalProduct = selectedUpdateProduct;
    const originalFetch = window.fetch;
    const originalConfirm = window.confirm;
    let request = null;
    productUpdateStates = {
      console: { currentVersion: '0.3.5', latestVersion: '0.3.5', available: false, autoCheck: true },
      world: {
        currentVersion: '', latestVersion: '0.1.7', available: true, installed: false,
        autoCheck: true, canInstall: true,
        releaseUrl: 'https://github.com/tx74666/CodexWorldConsole/releases/tag/v0.1.7'
      }
    };
    window.confirm = () => true;
    window.fetch = async (input, init = {}) => {
      const url = String(input || '');
      if (url.endsWith('/api/world/update/install')) {
        request = { url, method: init.method || 'GET' };
        return new Response(JSON.stringify({
          currentVersion: '0.1.7', latestVersion: '0.1.7', available: false,
          installed: true, autoCheck: true, canInstall: false, canOpen: true
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return originalFetch(input, init);
    };
    try {
      selectUpdateProduct('console', { persist: false });
      renderConsoleUpdate();
      document.querySelector('#consoleUpdateTop')?.click();
      for (let attempt = 0; attempt < 20 && !request; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      return request;
    } finally {
      window.fetch = originalFetch;
      window.confirm = originalConfirm;
      productUpdateStates = originalStates;
      selectedUpdateProduct = originalProduct;
      productUpdateBusy = false;
      renderConsoleUpdate();
    }
  })()`, true);
  assert(
    oneClickUpdate?.url.endsWith('/api/world/update/install') && oneClickUpdate.method === 'POST',
    `top update action targeted the wrong product: ${JSON.stringify(oneClickUpdate)}`
  );

  const cleanUninstallAction = await evaluate(client, `(async () => {
    const originalStates = productUpdateStates;
    const originalProduct = selectedUpdateProduct;
    const originalFetch = window.fetch;
    const originalConfirm = window.confirm;
    let request = null;
    productUpdateStates = {
      console: { currentVersion: '0.5.1', latestVersion: '0.5.1', available: false, canUninstall: true },
      world: { currentVersion: '0.3.0', latestVersion: '0.3.0', available: false, installed: true, canUninstall: true }
    };
    window.confirm = () => true;
    window.fetch = async (input, init = {}) => {
      const url = String(input || '');
      if (url.endsWith('/api/world/uninstall')) {
        request = { url, method: init.method || 'GET' };
        return new Response(JSON.stringify({ ok: true, cleanLocalData: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      return originalFetch(input, init);
    };
    try {
      selectUpdateProduct('world', { persist: false });
      renderConsoleUpdate();
      const button = document.querySelector('#consoleUninstall');
      const visible = !button?.hidden;
      button?.click();
      for (let attempt = 0; attempt < 20 && !request; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      return { visible, request };
    } finally {
      window.fetch = originalFetch;
      window.confirm = originalConfirm;
      productUpdateStates = originalStates;
      selectedUpdateProduct = originalProduct;
      productUpdateBusy = false;
      renderConsoleUpdate();
    }
  })()`, true);
  assert(
    cleanUninstallAction.visible
      && cleanUninstallAction.request?.url.endsWith('/api/world/uninstall')
      && cleanUninstallAction.request?.method === 'POST',
    `clean uninstall action is not connected: ${JSON.stringify(cleanUninstallAction)}`
  );

  await clickModule(client, "workspace");
  await waitForValue(
    () => evaluate(client, `({
      plans: document.querySelectorAll('#desktopLayoutPlan option').length,
      busy: document.querySelector('#desktopLayoutImport')?.disabled || false
    })`),
    value => value.plans > 0 && !value.busy,
    "device-local desktop layout plan did not load",
    10000,
    100
  );
  const desktopLayoutUi = await evaluate(client, `(async () => {
    const response = await fetch('/api/console/desktop-layout', { cache: 'no-store' });
    const api = await response.json();
    const panel = document.querySelector('.desktop-layout-panel');
    return {
      visible: Boolean(panel && !panel.closest('[data-module-panel]')?.hidden && panel.getBoundingClientRect().height > 0),
      localOnly: api.localOnly,
      plans: api.plans?.length || 0,
      selected: document.querySelector('#desktopLayoutPlan')?.value || '',
      saveDisabled: document.querySelector('#desktopLayoutSave')?.disabled,
      importDisabled: document.querySelector('#desktopLayoutImport')?.disabled,
      controls: ['desktopLayoutRestore', 'desktopLayoutSave', 'desktopLayoutImport'].every(id => Boolean(document.getElementById(id))),
      localLabel: document.querySelector('#desktopLayoutLocalOnly')?.textContent?.trim() || '',
      dataDirectory: api.dataDirectory || ''
    };
  })()`, true);
  assert(
    desktopLayoutUi.visible
      && desktopLayoutUi.localOnly
      && desktopLayoutUi.plans >= 1
      && desktopLayoutUi.selected
      && !desktopLayoutUi.saveDisabled
      && !desktopLayoutUi.importDisabled
      && desktopLayoutUi.controls
      && desktopLayoutUi.localLabel
      && /CodexControlConsole[\\/]desktop-layout/i.test(desktopLayoutUi.dataDirectory),
    `desktop layout UI is incomplete or not device-local: ${JSON.stringify(desktopLayoutUi)}`
  );
  await clickModule(client, "blender");

  await waitForValue(
    () => evaluate(client, `({
      count: Array.from(document.querySelectorAll('#blenderGithubProject option')).filter(option => option.value).length,
      busy: document.querySelector('#blenderGithubSharePanel')?.classList.contains('busy') || false
    })`),
    value => value.count > 0 && !value.busy,
    "Pinned Blender projects did not load",
    30000,
    120
  );

  const selectedPinned = await evaluate(client, `(() => {
    const select = document.querySelector('#blenderGithubProject');
    if (!select) return { found: false, values: [] };
    const options = Array.from(select.options);
    const target = options.find(option => option.value);
    if (!target) return { found: false, values: options.map(option => option.value) };
    select.value = target.value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return { found: true, value: target.value };
  })()`);
  assert(selectedPinned.found, `No pinned Blender project was listed: ${JSON.stringify(selectedPinned.values)}`);
  await waitForValue(
    () => evaluate(client, `({
      project: document.querySelector('#blenderGithubProject')?.value || '',
      state: document.querySelector('#blenderGithubState')?.dataset.state || '',
      busy: document.querySelector('#blenderGithubSharePanel')?.classList.contains('busy') || false
    })`),
    value => value.project === selectedPinned.value
      && ["cloud", "uninitialized", "initialized", "dirty", "committed", "pendingPush", "behind", "synced", "gitUnavailable"].includes(value.state)
      && !value.busy,
    "Blender GitHub Coop did not load the pinned project",
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
    currentFileTitle: document.querySelector('#blenderGithubBlendCards .blender-github-blend-card[aria-selected="true"] strong')?.title || '',
    repositoryMarks: Array.from(document.querySelectorAll('#blenderGithubBlendCards .blender-github-file-mark')).map(mark => mark.textContent?.trim() || ''),
    version: document.querySelector('#blenderGithubBlendCards .blender-github-blend-card[aria-selected="true"] .blender-github-version')?.textContent?.trim() || '',
    optionCount: document.querySelectorAll('#blenderGithubProject option[value]').length,
    collectionCount: blenderGithubShareState?.collection?.projects?.length || 0,
    generatedOptions: Array.from(document.querySelectorAll('#blenderGithubProject option')).filter(option => /[\\/](?:assets|records|blend_backups|roundtrip|unityexports)[\\/]/i.test(option.value)).map(option => option.value),
    addVisible: document.querySelector('#blenderGithubAdd')?.getBoundingClientRect().width > 0,
    allDraggable: Array.from(document.querySelectorAll('#blenderGithubBlendCards .blender-github-blend-card')).every(card => card.draggable),
    doubleClickHint: document.querySelector('#blenderGithubBlendCards .blender-github-blend-card')?.title || '',
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
  assert(shareState.currentFile && /^https:\/\/github\.com\//i.test(shareState.currentFileTitle), `repository card does not point to GitHub: ${JSON.stringify(shareState)}`);
  assert(shareState.repositoryMarks.length === shareState.cards && shareState.repositoryMarks.every(mark => mark === "GH"), `repository cards have the wrong marker: ${JSON.stringify(shareState)}`);
  assert(shareState.optionCount === shareState.collectionCount, `project picker contains projects outside the saved collection: ${JSON.stringify(shareState)}`);
  assert(shareState.generatedOptions.length === 0, `generated Blender folders entered the project picker: ${JSON.stringify(shareState.generatedOptions)}`);
  assert(shareState.addVisible && shareState.allDraggable && /double-click|双击/i.test(shareState.doubleClickHint), `GitHub Coop project shelf interactions are incomplete: ${JSON.stringify(shareState)}`);
  assert(/^V(?:\d|--)/.test(shareState.version), `compact version is invalid: ${JSON.stringify(shareState)}`);
  assert(shareState.refreshText && shareState.refreshFontSize >= 16, `refresh control is not visible: ${JSON.stringify(shareState)}`);
  const cloudOnlyProject = allowCloudProjects && shareState.state === "cloud";
  assert(
    !shareState.desktopDisabled
      && !shareState.openDisabled
      && (cloudOnlyProject ? shareState.folderDisabled : !shareState.folderDisabled),
    `project links are unavailable: ${JSON.stringify(shareState)}`
  );
  assert(shareState.noticeHidden, `passive Ready text is still visible: ${JSON.stringify(shareState)}`);
  assert(shareState.removedControls === 0, `verbose Git controls are still mounted: ${JSON.stringify(shareState)}`);

  const doubleClickOpen = await evaluate(client, `(async () => {
    const card = document.querySelector('#blenderGithubBlendCards .blender-github-blend-card');
    if (!card) return { found: false };
    const originalFetch = window.fetch;
    let request = null;
    window.fetch = async (input, init = {}) => {
      const url = String(input || '');
      if (url.includes('/api/randomrealm/blender/github-share/desktop')) {
        request = { url, body: JSON.parse(init.body || '{}') };
        return new Response(JSON.stringify({ ok: true, url: card.dataset.repositoryUrl }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        });
      }
      return originalFetch(input, init);
    };
    try {
      card.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
      await new Promise(resolve => setTimeout(resolve, 80));
      return {
        found: true,
        request,
        path: card.dataset.projectPath || '',
        repositoryUrl: card.dataset.repositoryUrl || ''
      };
    } finally {
      window.fetch = originalFetch;
    }
  })()`, true);
  if (!cloudOnlyProject) {
    assert(
      doubleClickOpen.found
        && doubleClickOpen.request?.url.endsWith('/api/randomrealm/blender/github-share/desktop')
        && doubleClickOpen.request?.body?.project === doubleClickOpen.path
        && doubleClickOpen.request?.body?.repositoryUrl === doubleClickOpen.repositoryUrl
        && /^https:\/\/github\.com\//i.test(doubleClickOpen.repositoryUrl),
      `repository card double-click is not wired to GitHub Desktop: ${JSON.stringify(doubleClickOpen)}`
    );
  }

  const cloudCardState = await evaluate(client, `(async () => {
    const originalState = blenderGithubShareState;
    const originalRepository = originalState?.collection?.projects?.[0];
    if (!originalRepository?.repositoryUrl) return { found: false };
    const cloudRepository = {
      ...originalRepository,
      path: '',
      directory: '',
      downloaded: false,
      state: 'cloud'
    };
    const cloudState = {
      ...originalState,
      collection: { projects: [cloudRepository] },
      project: {
        ...originalState.project,
        name: cloudRepository.name,
        path: '',
        directory: '',
        repositoryUrl: cloudRepository.repositoryUrl,
        downloaded: false
      },
      git: {
        ...originalState.git,
        state: 'cloud',
        repositoryWebUrl: cloudRepository.repositoryUrl,
        remoteUrl: cloudRepository.remoteUrl || cloudRepository.repositoryUrl
      }
    };
    const originalFetch = window.fetch;
    let request = null;
    try {
      renderBlenderGithubShare(cloudState);
      const card = document.querySelector('#blenderGithubBlendCards .blender-github-blend-card');
      window.fetch = async (input, init = {}) => {
        const url = String(input || '');
        if (url.includes('/api/randomrealm/blender/github-share/desktop')) {
          request = { url, body: JSON.parse(init.body || '{}') };
          return new Response(JSON.stringify({ ok: true, action: 'clone' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          });
        }
        return originalFetch(input, init);
      };
      card?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
      await new Promise(resolve => setTimeout(resolve, 80));
      return {
        found: Boolean(card),
        cloud: card?.dataset.downloaded === 'false' && card?.classList.contains('cloud'),
        cloudLabel: card?.querySelector('small')?.textContent?.trim() || '',
        folderDisabled: document.querySelector('#blenderGithubFolder')?.disabled,
        request,
        repositoryUrl: cloudRepository.repositoryUrl,
        guideMounted: Boolean(document.querySelector('.blender-github-guide.tutorial-only'))
      };
    } finally {
      window.fetch = originalFetch;
      renderBlenderGithubShare(originalState);
    }
  })()`, true);
  assert(
    cloudCardState.found
      && cloudCardState.cloud
      && cloudCardState.cloudLabel
      && cloudCardState.folderDisabled
      && cloudCardState.guideMounted
      && cloudCardState.request?.url.endsWith('/api/randomrealm/blender/github-share/desktop')
      && cloudCardState.request?.body?.project === cloudCardState.repositoryUrl,
    `cloud repository card is not clone-ready: ${JSON.stringify(cloudCardState)}`
  );

  const collapseState = await evaluate(client, `(() => {
    const toggle = document.querySelector('#blenderGithubToggle');
    const body = document.querySelector('#blenderGithubBody');
    toggle?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    const collapsed = Boolean(body?.hidden) && toggle?.getAttribute('aria-expanded') === 'false';
    toggle?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    return { collapsed, expanded: !body?.hidden && toggle?.getAttribute('aria-expanded') === 'true' };
  })()`);
  assert(collapseState.collapsed && collapseState.expanded, `GitHub Coop collapse behavior is broken: ${JSON.stringify(collapseState)}`);

  if (process.env.CONSOLE_UI_SCREENSHOT) {
    if (["light", "dark"].includes(process.env.CONSOLE_UI_THEME || "")) {
      await evaluate(client, `setTheme(${JSON.stringify(process.env.CONSOLE_UI_THEME)}, { record: false })`);
    }
    const screenshotModule = process.env.CONSOLE_UI_SCREENSHOT_MODULE || "blender";
    if (screenshotModule !== "blender") await clickModule(client, screenshotModule);
    if (process.env.CONSOLE_UI_THEME) {
      await evaluate(client, `(() => {
        const target = ${JSON.stringify(process.env.CONSOLE_UI_THEME)};
        if (document.documentElement.dataset.theme !== target) document.querySelector('#themeToggle')?.click();
      })()`);
      await delay(120);
    }
    if (process.env.CONSOLE_UI_TUTORIAL === "true") {
      await evaluate(client, `(() => {
        if (!document.documentElement.classList.contains('tutorial-mode')) {
          document.querySelector('#tutorialModeToggle')?.click();
        }
      })()`);
    }
    if (process.env.CONSOLE_UI_SCREENSHOT_CLOUD === "true") {
      await evaluate(client, `(() => {
        const repository = blenderGithubShareState?.collection?.projects?.[0];
        if (!repository) return;
        const cloudRepository = { ...repository, path: '', directory: '', downloaded: false, state: 'cloud' };
        renderBlenderGithubShare({
          ...blenderGithubShareState,
          collection: { projects: [cloudRepository] },
          project: {
            ...blenderGithubShareState.project,
            name: cloudRepository.name,
            path: '',
            directory: '',
            repositoryUrl: cloudRepository.repositoryUrl,
            downloaded: false
          },
          git: {
            ...blenderGithubShareState.git,
            state: 'cloud',
            repositoryWebUrl: cloudRepository.repositoryUrl,
            remoteUrl: cloudRepository.remoteUrl || cloudRepository.repositoryUrl
          }
        });
      })()`);
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
    () => evaluate(client, `({
      cards: document.querySelectorAll('.music-dock .track-card').length,
      empty: document.querySelectorAll('.music-dock .music-tier-empty').length
    })`),
    value => value.cards > 0 || (allowEmptyMedia && value.empty > 0),
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
    value => ["cloud", "uninitialized", "initialized", "dirty", "committed", "pendingPush", "behind", "synced", "gitUnavailable"].includes(value),
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

  await evaluate(client, "localStorage.clear()");
  await client.send("Page.navigate", { url: new URL("workspace.html?edition=public", baseUrl).href });
  await waitForDocument(client);
  await waitForValue(
    () => evaluate(client, "document.body?.dataset.consoleEdition || ''"),
    value => value === "public",
    "public edition did not initialize"
  );
  const publicState = await evaluate(client, `({
    active: document.querySelector('.module-link.active')?.dataset.moduleId || '',
    visible: Array.from(document.querySelectorAll('.module-link')).map(item => item.dataset.moduleId),
    archived: JSON.parse(localStorage.getItem('codexControl.moduleArchive.v1') || '[]'),
    deepArchived: JSON.parse(localStorage.getItem('codexControl.moduleDeepArchive.v1') || '[]'),
    feedbackPanel: Boolean(document.querySelector('#feedbackPanel')),
    feedbackStatus: document.querySelector('#feedbackStatus')?.textContent?.trim() || '',
    viewportWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth
  })`);
  assert(publicState.active === "workspace", `public edition did not start in Console: ${JSON.stringify(publicState)}`);
  assert(
    JSON.stringify(publicState.visible) === JSON.stringify(["workspace", "music", "wallpaper"]),
    `public edition exposed the wrong first-level tabs: ${JSON.stringify(publicState)}`
  );
  assert(
    JSON.stringify(publicState.archived) === JSON.stringify(["blender"]),
    `public edition Archive defaults are wrong: ${JSON.stringify(publicState)}`
  );
  assert(
    JSON.stringify(publicState.deepArchived) === JSON.stringify(["manager", "unity", "steamwork", "randomrealm"]),
    `public edition deep Archive defaults are wrong: ${JSON.stringify(publicState)}`
  );
  assert(publicState.feedbackPanel && publicState.feedbackStatus, "feedback panel did not initialize");
  assert(publicState.scrollWidth <= publicState.viewportWidth, `public workspace overflows: ${JSON.stringify(publicState)}`);

  for (const viewport of [
    { width: 390, height: 844 },
    { width: 1024, height: 768 },
    { width: 1366, height: 768 },
    { width: 1920, height: 1080 },
    { width: 2560, height: 1440 }
  ]) {
    await client.send("Emulation.setDeviceMetricsOverride", {
      ...viewport,
      deviceScaleFactor: 1,
      mobile: false
    });
    await delay(100);
    const responsiveState = await evaluate(client, `({
      viewportWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      shellWidth: Math.ceil(document.querySelector('.app-shell')?.getBoundingClientRect().width || 0),
      downloadsWidth: Math.ceil(document.querySelector('.github-download-panel')?.getBoundingClientRect().width || 0),
      clippedControls: Array.from(document.querySelectorAll('.github-download-link, .console-update-controls button')).filter(item => item.scrollWidth > item.clientWidth + 1).map(item => item.id || item.textContent?.trim() || item.tagName)
    })`);
    assert(
      responsiveState.scrollWidth <= responsiveState.viewportWidth
        && responsiveState.shellWidth <= responsiveState.viewportWidth
        && responsiveState.downloadsWidth <= responsiveState.viewportWidth
        && responsiveState.clippedControls.length === 0,
      `workspace layout is not responsive at ${viewport.width}x${viewport.height}: ${JSON.stringify(responsiveState)}`
    );
  }
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
