(function (scope) {
  "use strict";
  let databasePromise;
  function database() {
    if (!databasePromise) databasePromise = new Promise((resolve, reject) => {
      const request = indexedDB.open("codex-console-phone-v1", 1);
      request.onupgradeneeded = () => { for (const name of ["records", "media", "music", "settings"]) if (!request.result.objectStoreNames.contains(name)) request.result.createObjectStore(name, { keyPath: "id" }); };
      request.onsuccess = () => { request.result.onversionchange = () => { request.result.close(); databasePromise = null; }; resolve(request.result); };
      request.onerror = () => { databasePromise = null; reject(request.error || new Error("无法打开手机资料库。")); };
      request.onblocked = () => { databasePromise = null; reject(new Error("请关闭另一个 Console 页面，再重试。")); };
    });
    return databasePromise;
  }
  async function operation(name, mode, action) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(name, mode); let value;
      transaction.oncomplete = () => resolve(value);
      transaction.onerror = () => reject(transaction.error || new Error("手机资料暂时无法保存。"));
      transaction.onabort = () => reject(transaction.error || new Error("手机资料保存已中断。"));
      const request = action(transaction.objectStore(name));
      request.onsuccess = () => { value = request.result; };
    });
  }
  async function replaceLibrary(library) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction("records", "readwrite"), store = transaction.objectStore("records"), previous = store.get("library");
      previous.onsuccess = () => { if (previous.result) store.put({ ...previous.result, id: "previousImport" }); store.put({ ...library, id: "library" }); };
      transaction.oncomplete = () => resolve(); transaction.onerror = () => reject(transaction.error); transaction.onabort = () => reject(transaction.error || new Error("导入已中断，原资料保留。"));
    });
  }
  async function putTrack(metadata, media) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(["music", "media"], "readwrite");
      transaction.oncomplete = () => resolve(); transaction.onerror = () => reject(transaction.error); transaction.onabort = () => reject(transaction.error || new Error("音乐保存已中断，原文件保留。"));
      transaction.objectStore("music").put(metadata); transaction.objectStore("media").put(media);
    });
  }
  async function mutateRecord(name, id, change) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(name, "readwrite"), store = transaction.objectStore(name); let value, failure;
      transaction.oncomplete = () => resolve(value);
      transaction.onerror = () => reject(failure || transaction.error || new Error("手机资料暂时无法保存。"));
      transaction.onabort = () => reject(failure || transaction.error || new Error("保存已中断，原内容保留。"));
      const request = store.get(id);
      request.onsuccess = () => {
        try {
          value = change(request.result);
          if (!value || value.id !== id || typeof value.then === "function") throw new Error("本机保存内容无效。");
          store.put(value);
        } catch (error) { failure = error; transaction.abort(); }
      };
    });
  }
  scope.PhoneStore = {
    database, replaceLibrary, putTrack, mutateRecord,
    get: (name, id) => operation(name, "readonly", store => store.get(id)),
    put: (name, value) => operation(name, "readwrite", store => store.put(value)),
    add: (name, value) => operation(name, "readwrite", store => store.add(value)),
    remove: (name, id) => operation(name, "readwrite", store => store.delete(id)),
    all: name => operation(name, "readonly", store => store.getAll()),
    keys: name => operation(name, "readonly", store => store.getAllKeys())
  };
})(typeof self === "undefined" ? globalThis : self);
