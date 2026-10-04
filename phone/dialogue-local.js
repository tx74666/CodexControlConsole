/* The public phone shell keeps drafts in its existing PhoneStore. No App sender. */
(() => {
  "use strict";
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const ID = /^[a-f0-9]{32}$/;
  const profiles = new Set(["fast", "high", "pro"]);
  const error = (message, status = 400, code = "invalid_request") => Object.assign(new Error(message), { status, code });
  const text = (value, limit = 20000) => { if (typeof value !== "string" || value.length > limit || value.includes("\0")) throw error("文字内容无效或过长。"); return value; };
  const stamp = () => new Date().toISOString();
  const nextId = () => crypto.randomUUID().replaceAll("-", "");
  const signature = value => JSON.stringify(Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]])));
  const state = source => {
    const value = structuredClone(source || { id: "incubator", ideas: [], receipts: {}, revision: 0 });
    value.mobile ||= { current: {}, sessions: {}, metadata: {}, receipts: {} };
    return value;
  };
  const extended = (value, idea) => ({ ...idea, projectId: null, archived: false, keyPoints: [], executionDraft: "", attachmentIds: [], provenance: [], ...(value.mobile.metadata[idea.id] || {}) });
  const execution = profile => ({ requestedProfile: profile, actualReceipt: { verified: false, actualProfile: null, status: "unavailable", source: null }, supportedProfiles: [], capability: "unavailable", relayStatus: "not_connected", message: "草稿保存在此手机；连接电脑后继续对话。" });
  const detail = session => ({ record: { id: session.recordId, title: "当前讨论" }, messages: [], attachments: [], jobs: [], sourceTask: null, revision: String(session.revision) });
  const sessionResult = (value, clientId) => {
    const raw = value.mobile.sessions[value.mobile.current[clientId]] || null;
    const session = raw ? { ...structuredClone(raw), isCurrent: true } : null;
    const profile = session?.requestedProfile || value.mobile.profile || "high";
    return { session, detail: session ? detail(session) : null, preferences: { requestedProfile: profile }, execution: execution(profile), revision: String(value.revision), localOnly: true };
  };
  function client(value) { if (!UUID.test(value || "")) throw error("此手机的讨论身份无效。"); return value; }
  function current(value, body) {
    const session = value.mobile.sessions[body.sessionId];
    if (!session || session.clientId !== client(body.clientId) || value.mobile.current[body.clientId] !== session.id) throw error("讨论已切换，原草稿仍保留。", 409, "dialogue_changed");
    if (body.expectedRevision !== session.revision) throw error("讨论已在另一页修改，请刷新后合并。", 409, "revision_conflict");
    return session;
  }
  function newSession(value, clientId, ideaId = null) {
    const now = stamp(), session = { id: nextId(), clientId, recordId: nextId(), ideaId, ideaRevision: ideaId ? value.ideas.find(item => item.id === ideaId)?.revision : null, revision: 1, draft: { text: "", attachmentIds: [] }, requestedProfile: value.mobile.profile || "high", createdAt: now, updatedAt: now };
    value.mobile.sessions[session.id] = session; value.mobile.current[clientId] = session.id;
    return session;
  }
  const previews = new Map();
  async function attachments(ids) {
    const items = [];
    for (const id of ids || []) {
      const item = await PhoneStore.get("media", `dialogue-image:${id}`);
      if (!item?.blob || item.kind !== "dialogue_image") continue;
      if (!previews.has(id)) previews.set(id, URL.createObjectURL(item.blob));
      items.push({ id, name: item.name, mimeType: item.mimeType, size: item.size, url: previews.get(id) });
    }
    return items;
  }
  async function hydrate(response) {
    if (response?.session && response.detail) response.detail.attachments = await attachments(response.session.draft?.attachmentIds);
    return response;
  }
  async function uploadAttachments(files, expected, uploadRequest = { requestId: crypto.randomUUID(), recordId: expected.recordId }) {
    const value = state(await PhoneStore.get("records", "incubator"));
    const session = current(value, { clientId: expected.clientId, sessionId: expected.id, expectedRevision: expected.revision });
    if (!UUID.test(uploadRequest.requestId || "") || uploadRequest.recordId !== session.recordId) throw error("图片上传凭据不属于当前讨论。", 409);
    if (!Array.isArray(files) || !files.length || files.length + (session.draft.attachmentIds?.length || 0) > 4) throw error("每次最多保留四张图片。");
    const digest = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), byte => byte.toString(16).padStart(2, "0")).join("");
    const items = await Promise.all(files.map(async (file, index) => {
      if (!file || !["image/png", "image/jpeg", "image/gif", "image/webp"].includes(file.type) || !file.size || file.size > 8 * 1024 * 1024) throw error("请选择小于 8 MB 的 PNG、JPEG、GIF 或 WebP 图片。");
      const id = (await digest(new TextEncoder().encode(`${uploadRequest.requestId}:${session.id}:${index}`))).slice(0, 32), sha256 = await digest(await file.arrayBuffer());
      return { id: `dialogue-image:${id}`, kind: "dialogue_image", sessionId: session.id, clientId: session.clientId, name: String(file.name || "图片").slice(0, 180), mimeType: file.type, size: file.size, sha256, blob: file, createdAt: stamp() };
    }));
    const written = [];
    try { for (const item of items) {
      const old = await PhoneStore.get("media", item.id);
      if (old) { if (old.sessionId !== item.sessionId || old.clientId !== item.clientId || old.sha256 !== item.sha256 || old.name !== item.name || old.mimeType !== item.mimeType) throw error("同一图片请求不能换成其它内容。", 409); }
      else { await PhoneStore.put("media", item); written.push(item.id); }
    } }
    catch (failure) { await Promise.allSettled(written.map(id => PhoneStore.remove("media", id))); throw failure; }
    return { attachments: await attachments(items.map(item => item.id.slice("dialogue-image:".length))), localOnly: true };
  }
  async function endpoint(action, body) {
    const [route, rawQuery = ""] = action.split("?"), query = new URLSearchParams(rawQuery);
    if (body === undefined) {
      const value = state(await PhoneStore.get("records", "incubator"));
      if (route === "mobile/dialogue") return hydrate(sessionResult(value, client(query.get("clientId"))));
      if (route === "mobile/ideas") {
        const search = (query.get("search") || "").toLocaleLowerCase(), archived = query.get("archived") === "1", projectId = query.get("projectId") || "";
        return { ideas: value.ideas.map(item => extended(value, item)).filter(item => item.archived === archived && (!projectId || projectId === "unclassified" && !item.projectId || item.projectId === projectId) && `${item.title}\n${item.body}`.toLocaleLowerCase().includes(search)).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)), projects: [], revision: String(value.revision), localOnly: true };
      }
      if (route === "mobile/idea") {
        const idea = value.ideas.find(item => item.id === query.get("id"));
        if (!idea) throw error("找不到此手机里的想法。", 404);
        const saved = extended(value, idea), media = await attachments(saved.attachmentIds);
        return { idea: saved, detail: { record: { id: idea.id, title: idea.title }, messages: [], jobs: [], attachments: media }, provenance: saved.provenance, revision: String(value.revision), localOnly: true };
      }
      throw error("此手机没有这个入口。", 404);
    }
    if (!body || !UUID.test(body.requestId || "")) throw error("保存请求无效。");
    if (route === "mobile/dialogue/send") throw error("电脑转发器尚未连接；草稿仍保存在此手机。", 503);
    if (route === "mobile/dialogue/remember") throw error("此手机尚未取得电脑的实际回答，不能补造或保存未知回答。", 409);
    const allowed = new Set(["mobile/dialogue/open", "mobile/dialogue/draft", "mobile/dialogue/clear", "mobile/dialogue/save", "mobile/idea/update", "mobile/idea/archive"]);
    if (!allowed.has(route)) throw error("此手机没有这个入口。", 404);
    let mediaProof = [];
    if (body.attachmentIds !== undefined) {
      if (!Array.isArray(body.attachmentIds) || body.attachmentIds.length > 4 || body.attachmentIds.some(id => !ID.test(id)) || new Set(body.attachmentIds).size !== body.attachmentIds.length) throw error("图片选择无效。");
      mediaProof = await Promise.all(body.attachmentIds.map(id => PhoneStore.get("media", `dialogue-image:${id}`)));
    }
    let response;
    await PhoneStore.mutateRecord("records", "incubator", source => {
      const value = state(source), receiptKey = route + ":" + body.requestId, fingerprint = signature(body), receipt = value.mobile.receipts[receiptKey];
      if (receipt) {
        if (receipt.fingerprint !== fingerprint) throw error("同一保存请求不能换成不同内容。", 409);
        response = { ...structuredClone(receipt.response), duplicate: true };
        if (response.session) response.session.isCurrent = value.mobile.current[response.session.clientId] === response.session.id;
        return value;
      }
      if (Object.keys(value.mobile.receipts).length >= 4096) throw error("此手机保存记录较多，请先备份；现有内容仍保留。", 409);
      if (route === "mobile/dialogue/open") {
        const clientId = client(body.clientId);
        if (body.ideaId) {
          const idea = value.ideas.find(item => item.id === body.ideaId);
          if (!idea || body.expectedIdeaRevision !== idea.revision) throw error("想法已修改，请刷新后继续。", 409, "revision_conflict");
          newSession(value, clientId, idea.id);
        } else if (!value.mobile.current[clientId]) newSession(value, clientId);
        response = sessionResult(value, clientId);
      } else if (route.startsWith("mobile/dialogue/")) {
        const session = current(value, body);
        if (route === "mobile/dialogue/clear") {
          newSession(value, body.clientId);
        } else {
          const content = text(body.text), attachmentIds = body.attachmentIds || [];
          if (mediaProof.some(item => !item?.blob || item.kind !== "dialogue_image" || item.sessionId !== session.id || item.clientId !== session.clientId)) throw error("图片尚未完整保存在当前讨论，内容仍保留。", 409);
          if (!profiles.has(body.requestedProfile || session.requestedProfile)) throw error("请选择有效档位。");
          session.draft = { text: content, attachmentIds }; session.requestedProfile = body.requestedProfile || session.requestedProfile;
          value.mobile.profile = session.requestedProfile; session.revision++; session.updatedAt = stamp();
          if (route === "mobile/dialogue/save") {
            if (!content.trim() && !attachmentIds.length) throw error("先写下一点想法或选择图片。");
            const now = stamp(), ideaId = body.requestId.replaceAll("-", "");
            const existing = session.ideaId ? value.ideas.find(item => item.id === session.ideaId) : null;
            if (session.ideaId && (!existing || existing.revision !== session.ideaRevision)) throw error("想法已修改，请刷新后合并。", 409, "revision_conflict");
            if (!existing && value.ideas.length >= 1000) throw error("此手机保存的想法较多，请先导出备份。", 409);
            const idea = existing || { id: ideaId, title: content.trim().split(/\r?\n/)[0].slice(0, 80) || mediaProof[0]?.name || "图片想法", body: content, stage: "vague", priority: "normal", parentId: null, targetKind: "none", targetThreadId: "", targetName: "", revision: 1, createdAt: now, updatedAt: now };
            if (existing) { idea.body = text(idea.body + (content && idea.body ? "\n\n" : "") + content); idea.revision++; idea.updatedAt = now; session.ideaRevision = idea.revision; }
            else { value.ideas.unshift(idea); value.mobile.metadata[ideaId] = { projectId: null, archived: false, keyPoints: [], executionDraft: "", provenance: [] }; }
            const metadata = value.mobile.metadata[idea.id] ||= { projectId: null, archived: false, keyPoints: [], executionDraft: "", provenance: [] };
            metadata.attachmentIds = [...new Set([...(metadata.attachmentIds || []), ...attachmentIds])];
            metadata.provenance.push({ source: "phone_local", sessionId: session.id, attachmentIds: [...attachmentIds], createdAt: now });
            session.ideaId = idea.id; session.ideaRevision = idea.revision;
            session.draft = { text: "", attachmentIds: [] }; response = { ...sessionResult(value, body.clientId), idea: extended(value, idea) };
          }
        }
        response ||= sessionResult(value, body.clientId);
      } else {
        if (!ID.test(body.id || "")) throw error("想法标识无效。");
        const idea = value.ideas.find(item => item.id === body.id);
        if (!idea || body.expectedRevision !== idea.revision) throw error("想法已修改，请刷新后合并。", 409, "revision_conflict");
        const metadata = extended(value, idea);
        if (route === "mobile/idea/archive") {
          if (typeof body.archived !== "boolean") throw error("归档设置无效。");
          metadata.archived = body.archived;
        } else {
          if (body.title !== undefined) { const title = text(body.title, 80).trim(); if (!title) throw error("标题不能为空。"); idea.title = title; }
          if (body.body !== undefined) idea.body = text(body.body);
          if (body.projectId != null && body.projectId !== "unclassified") throw error("本机想法尚未归入电脑项目。", 409);
          if (body.executionDraft !== undefined) metadata.executionDraft = text(body.executionDraft);
          if (body.keyPoints !== undefined) {
            if (!Array.isArray(body.keyPoints) || body.keyPoints.length > 100) throw error("长期要点无效。");
            const seen = new Set(); metadata.keyPoints = body.keyPoints.map(item => { if (!ID.test(item.id || "") || seen.has(item.id) || !["suggestion", "decision"].includes(item.kind)) throw error("长期要点身份或类型无效。"); seen.add(item.id); return { id: item.id, text: text(item.text, 2000), kind: item.kind }; });
          }
        }
        value.mobile.metadata[idea.id] = { projectId: null, archived: metadata.archived, keyPoints: metadata.keyPoints, executionDraft: metadata.executionDraft, attachmentIds: metadata.attachmentIds, provenance: metadata.provenance };
        idea.revision++; idea.updatedAt = stamp(); response = { idea: extended(value, idea), revision: String(value.revision + 1), localOnly: true };
      }
      value.revision++; response.revision = String(value.revision); response.localOnly = true;
      value.mobile.receipts[receiptKey] = { fingerprint, response: structuredClone(response) }; return value;
    });
    return hydrate(response);
  }
  window.CodexPhoneDialogueLocal = { endpoint, uploadAttachments };
})();
