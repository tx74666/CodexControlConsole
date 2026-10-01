(() => {
  'use strict';
  const button = document.getElementById('phoneOfflineExport');
  const status = document.getElementById('phoneOfflineExportStatus');
  if (!button || !status) return;
  button.addEventListener('click', async () => {
    if (button.disabled) return;
    button.disabled = true;
    status.textContent = '正在整理计划、阅读资料与带时间的设备摘要…';
    try {
      const response = await fetch('/api/phone-offline/export', {
        method: 'POST', credentials: 'same-origin', mode: 'same-origin', cache: 'no-store', redirect: 'error',
        headers: {'Content-Type':'application/json'}, body: '{}'
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || '资料暂时无法导出。');
      if (payload.format !== 'codex-console-phone-data' || payload.schemaVersion !== 1) throw new Error('资料格式无效，请更新 Console 后重试。');
      const objectUrl = URL.createObjectURL(new Blob([JSON.stringify(payload)], {type:'application/json'}));
      const link = document.createElement('a');
      link.href = objectUrl; link.download = `Console-手机资料-${new Date().toISOString().slice(0,10)}.json`;
      document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
      status.textContent = '已导出。把这个文件送到 iPhone，在离线手机版的设置中导入即可。音乐在手机中另行保存或导入。';
    } catch (error) {
      status.textContent = error.message || '导出未完成，请重试。';
    } finally {
      button.disabled = false;
    }
  });
})();
