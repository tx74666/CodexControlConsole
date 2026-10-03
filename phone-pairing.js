(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const dialog = byId('phoneCompanionDialog');
  if (!dialog) return;
  const open = byId('phoneCompanionOpen');
  const select = byId('phoneCompanionInterface');
  const status = byId('phoneCompanionStatus');
  const start = byId('phoneCompanionStart');
  const renew = byId('phoneCompanionRenew');
  const stop = byId('phoneCompanionStop');
  const qr = byId('phoneCompanionQr');
  qr?.addEventListener('error', () => { qr.hidden = true; });
  let current = null;
  let busy = false;
  let timer = 0;
  let sequence = 0;
  function render(value) {
    if (!Array.isArray(value.availableInterfaces) && Array.isArray(current?.availableInterfaces)) {
      value = {...value, availableInterfaces: current.availableInterfaces};
    }
    current = value;
    const addresses = Array.isArray(value.availableInterfaces) ? value.availableInterfaces : [];
    const wanted = select.value || value.host;
    select.replaceChildren();
    for (const item of addresses) {
      const option = document.createElement('option');
      option.value = item.address;
      option.textContent = `${item.name} · ${item.address}`;
      select.append(option);
    }
    if (addresses.some(item => item.address === wanted)) select.value = wanted;
    select.disabled = busy || value.enabled;
    start.hidden = Boolean(value.enabled);
    renew.hidden = !value.enabled;
    stop.hidden = !value.enabled;
    start.disabled = busy || !addresses.length;
    renew.disabled = busy;
    stop.disabled = busy;
    byId('phoneCompanionDetails').hidden = !value.enabled;
    status.textContent = value.enabled ? '手机入口已开启，可以配对后使用互传和任务同步。' : addresses.length ? '手机入口已关闭，需要使用时再开启。' : '没有找到已连接的 Wi‑Fi 或网线，请先连接网络。';
    const link = byId('phoneCompanionUrl');
    if (value.enabled) {
      const transferUrl = new URL(value.url);
      transferUrl.searchParams.set('tab', 'transfer');
      link.href = transferUrl.href;
      link.textContent = transferUrl.href;
      if (qr && qr.dataset.url !== value.url) {
        qr.dataset.url = value.url;
        qr.hidden = false;
        qr.src = `/api/phone-companion/qr.png?version=${encodeURIComponent(value.url)}`;
      }
      const expiry = Date.parse(value.pairingExpiresAt);
      const active = Boolean(value.pairingCode) && Number.isFinite(expiry) && expiry > Date.now();
      byId('phoneCompanionCode').textContent = active ? value.pairingCode : '点击“新配对码”';
      byId('phoneCompanionExpiry').textContent = active ? `有效至 ${new Date(expiry).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}，仅可使用一次。` : '旧配对码已使用或过期；手机需要重新连接时，生成一个新码。';
      byId('phoneCompanionPeers').textContent = `已配对 ${Number(value.pairedCount) || 0} 个连接。`;
    } else {
      link.removeAttribute('href');
      link.textContent = '';
      if (qr) { qr.hidden = true; qr.removeAttribute('src'); delete qr.dataset.url; }
      byId('phoneCompanionCode').textContent = '';
    }
  }
  async function request(action, payload = {}) {
    const response = await fetch(`/api/phone-companion/${action}`, {
      method: action === 'state' ? 'GET' : 'POST',
      headers: action === 'state' ? {} : {'Content-Type':'application/json'},
      ...(action === 'state' ? {} : {body:JSON.stringify(payload)}),
      cache:'no-store'
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '连接设置未完成，请重试。');
    return result;
  }
  async function refresh() {
    if (busy || !dialog.open) return;
    const ticket = ++sequence;
    try {
      const value = await request('state');
      if (ticket === sequence && dialog.open) render(value);
    } catch (error) {
      if (ticket === sequence) status.textContent = error.message;
    }
  }
  async function act(action, payload) {
    if (busy) return;
    busy = true;
    ++sequence;
    if (current) render(current);
    status.textContent = action === 'start' ? '正在开启手机入口…' : '正在更新连接…';
    try {
      const next = await request(action, payload);
      busy = false;
      render(next);
    } catch (error) {
      busy = false;
      if (current) render(current);
      status.textContent = error.message;
    }
  }
  open?.addEventListener('click', () => {
    if (!dialog.open) dialog.showModal();
    refresh();
    window.clearInterval(timer);
    timer = window.setInterval(refresh, 15000);
  });
  byId('phoneCompanionClose').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {++sequence; window.clearInterval(timer); timer=0;});
  start.addEventListener('click', () => act('start', {host:select.value}));
  renew.addEventListener('click', () => act('pair-code', {}));
  stop.addEventListener('click', () => act('stop', {}));
})();
