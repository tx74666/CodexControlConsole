/* The public phone shell keeps drafts in its existing PhoneStore. No App sender. */
(() => {
  "use strict";
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const ID = /^[a-f0-9]{32}$/;
  const profiles = new Set(["fast", "high", "pro"]);
  const error = (message, status = 400, code = "invalid_request") => Object.assign(new Error(message), { status, code });
  const text = (value, limit = 20000) => { if (typeof value !== "string" || Array.from(value).length > limit || value.includes("\0")) throw error("文字内容无效或过长。"); return value; };
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
    return { session, detail: session ? detail(session) : null, eligibleAttachments: [], preferences: { requestedProfile: profile }, execution: execution(profile), revision: String(value.revision), localOnly: true };
  };
  function client(value) { if (!UUID.test(value || "")) throw error("此手机的讨论身份无效。"); return value; }
  function current(value, body) {
    const session = value.mobile.sessions[body.sessionId];
    if (!session || session.clientId !== client(body.clientId) || value.mobile.current[body.clientId] !== session.id) throw error("讨论已切换，原草稿仍保留。", 409, "dialogue_changed");
    if (body.expectedRevision !== session.revision) throw error("讨论已在另一页修改，请刷新后合并。", 409, "revision_conflict");
    return session;
  }
  function newSession(value, clientId, ideaId = null) {
    const idea = ideaId ? value.ideas.find(item => item.id === ideaId) : null;
    const now = stamp(), session = { id: nextId(), clientId, recordId: nextId(), ideaId, ideaRevision: idea?.revision ?? null, eligibleAttachmentIds: idea ? [...(extended(value, idea).attachmentIds || [])] : [], revision: 1, draft: { text: "", attachmentIds: [] }, requestedProfile: value.mobile.profile || "high", createdAt: now, updatedAt: now };
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
    if (response?.session) response.eligibleAttachments = await attachments(response.session.eligibleAttachmentIds);
    return response;
  }
  async function uploadAttachments(files, expected, uploadRequest = { requestId: crypto.randomUUID(), recordId: expected.recordId }) {
    const value = state(await PhoneStore.get("records", "incubator"));
    const session = current(value, { clientId: expected.clientId, sessionId: expected.id, expectedRevision: expected.revision });
    if (session.ideaId && value.ideas.find(idea => idea.id === session.ideaId)?.revision !== session.ideaRevision) throw error("想法已修改，请刷新后重新核对。", 409, "revision_conflict");
    if (!UUID.test(uploadRequest.requestId || "") || uploadRequest.recordId !== session.recordId) throw error("图片上传凭据不属于当前讨论。", 409);
    if (uploadRequest.scope && (uploadRequest.scope.clientId !== session.clientId || uploadRequest.scope.sessionId !== session.id || uploadRequest.scope.expectedRevision !== session.revision)) throw error("图片上传凭据不属于当前讨论版本。", 409);
    if (!Array.isArray(files) || !files.length || files.length + (session.draft.attachmentIds?.length || 0) > 4) throw error("每次最多保留四张图片。");
    let selectedSize = 0;
    for (const id of session.draft.attachmentIds || []) { const item = await PhoneStore.get("media", `dialogue-image:${id}`); if (!item?.blob || item.size !== item.blob.size) throw error("已选图片无法核对，请保留草稿。", 409, "image_source_mismatch"); selectedSize += item.blob.size; }
    if (selectedSize + files.reduce((sum, file) => sum + (file?.size || 0), 0) > 24 * 1024 * 1024) throw error("本次图片合计不能超过 24 MB。", 413);
    const digest = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), byte => byte.toString(16).padStart(2, "0")).join("");
    const items = await Promise.all(files.map(async (file, index) => {
      if (!file || !["image/png", "image/jpeg", "image/gif", "image/webp"].includes(file.type) || !file.size || file.size > 8 * 1024 * 1024) throw error("请选择小于 8 MB 的 PNG、JPEG、GIF 或 WebP 图片。");
      const id = (await digest(new TextEncoder().encode(`${uploadRequest.requestId}:${session.id}:${index}`))).slice(0, 32), sha256 = await digest(await file.arrayBuffer());
      return { id: `dialogue-image:${id}`, kind: "dialogue_image", sessionId: session.id, clientId: session.clientId, name: String(file.name || "图片").slice(0, 180), mimeType: file.type, size: file.size, sha256, blob: file, createdAt: stamp() };
    }));
    const frozenSignature = signature({ clientId: session.clientId, sessionId: session.id, recordId: session.recordId, expectedRevision: session.revision, images: items.map(({ id, name, mimeType, size, sha256 }) => ({ id, name, mimeType, size, sha256 })) });
    const receipt = value.mobile.uploadReceipts?.[uploadRequest.requestId];
    if (receipt) { if (receipt.signature !== frozenSignature) throw error("同一图片请求不能换成其它内容。", 409); return { attachments: await attachments(receipt.attachmentIds), localOnly: true, duplicate: true }; }
    const written = [];
    try { for (const item of items) {
      const old = await PhoneStore.get("media", item.id);
      if (old) throw error("原图片请求尚需核对，请保留草稿；不能把同一编号用于新上传。", 409);
      else { await PhoneStore.add("media", item); written.push(item.id); }
    }
      await PhoneStore.mutateRecord("records", "incubator", source => {
        const next = state(source), active = current(next, { clientId: session.clientId, sessionId: session.id, expectedRevision: session.revision });
        if (active.ideaId && next.ideas.find(idea => idea.id === active.ideaId)?.revision !== active.ideaRevision) throw error("想法已修改，请刷新后重新核对。", 409, "revision_conflict");
        next.mobile.uploadReceipts ||= {}; if (next.mobile.uploadReceipts[uploadRequest.requestId]) throw error("图片请求正在另一页保存，请保留原草稿后重试。", 409);
        next.mobile.uploadReceipts[uploadRequest.requestId] = { signature: frozenSignature, attachmentIds: items.map(item => item.id.slice("dialogue-image:".length)), createdAt: stamp() };
        next.revision++; return next;
      });
    }
    catch (failure) { await Promise.allSettled(written.map(id => PhoneStore.remove("media", id))); throw failure; }
    return { attachments: await attachments(items.map(item => item.id.slice("dialogue-image:".length))), localOnly: true };
  }
  const managementRoutes = new Set(["mobile/idea/split", "mobile/idea/merge"]);
  const digestText = async value => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value))), byte => byte.toString(16).padStart(2, "0")).join("");
  const validRevision = revision => Number.isSafeInteger(revision) && revision > 0;
  async function prepareManagement(route, body) {
    const allowed = new Set(route.endsWith("split") ? ["requestId", "id", "expectedRevision", "start", "end", "title", "attachmentIds"] : ["requestId", "firstId", "firstRevision", "secondId", "secondRevision", "title", "attachmentIds"]);
    if (Object.keys(body).some(key => !allowed.has(key))) throw error("想法管理请求内容无效。");
    const title = text(body.title, 80).trim(); if (!title) throw error("新想法标题不能为空。");
    const selected = body.attachmentIds || [];
    if (!Array.isArray(selected) || selected.length > 4 || selected.some(id => !ID.test(id)) || new Set(selected).size !== selected.length) throw error("图片选择无效。");
    const value = state(await PhoneStore.get("records", "incubator")), receiptKey = route + ":" + body.requestId;
    const previous = value.mobile.receipts[receiptKey];
    if (previous) {
      if (previous.fingerprint !== signature(body)) throw error("同一管理请求不能换成不同内容。", 409);
      return { replay: true, title, selected, copies: [], written: [] };
    }
    const references = route.endsWith("split") ? [{ id: body.id, revision: body.expectedRevision }] : [{ id: body.firstId, revision: body.firstRevision }, { id: body.secondId, revision: body.secondRevision }];
    if (references.some(ref => !ID.test(ref.id || "") || !validRevision(ref.revision)) || new Set(references.map(ref => ref.id)).size !== references.length) throw error("请选择不同的已保存想法及其准确版本。");
    const sources = references.map(ref => { const item = value.ideas.find(idea => idea.id === ref.id); if (!item || item.revision !== ref.revision) throw error("原想法已修改，请刷新后重新核对。", 409, "revision_conflict"); return extended(value, item); });
    let content;
    if (route.endsWith("split")) {
      const characters = Array.from(sources[0].body);
      if (!Number.isSafeInteger(body.start) || !Number.isSafeInteger(body.end) || body.start < 0 || body.end <= body.start || body.end > characters.length) throw error("请选择原想法中的准确文字范围。");
      content = characters.slice(body.start, body.end).join(""); if (!content.trim()) throw error("选中的内容不能为空。");
    } else content = sources.map(item => item.body).filter(Boolean).join("\n\n");
    text(content);
    const executionDraft = route.endsWith("merge") ? text(sources.map(item => item.executionDraft || "").filter(Boolean).join("\n\n")) : "";
    const points = [], seen = new Set();
    if (route.endsWith("merge")) for (const source of sources) for (const point of source.keyPoints || []) {
      const key = JSON.stringify([point.text, point.kind]); if (seen.has(key)) continue; seen.add(key);
      points.push({ id: nextId(), text: text(point.text), kind: point.kind, source: { sourceIdeaId: source.id, sourceIdeaRevision: source.revision, sourcePointId: point.id } });
    }
    if (points.length > 100) throw error("合并后的长期要点超过 100 条，原内容仍保留。", 413);
    const eligible = new Set(sources.flatMap(source => source.attachmentIds || []));
    if (selected.some(id => !eligible.has(id))) throw error("所选图片不属于这些准确版本的原想法。", 409);
    const copies = [], written = [];
    try {
      for (const [index, imageId] of selected.entries()) {
        const image = await PhoneStore.get("media", `dialogue-image:${imageId}`);
        if (!image?.blob || image.kind !== "dialogue_image" || image.size !== image.blob.size || image.mimeType !== image.blob.type || !image.size || image.size > 8 * 1024 * 1024) throw error("原图片无法完整核对，尚未创建新想法。", 409);
        const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await image.blob.arrayBuffer())), byte => byte.toString(16).padStart(2, "0")).join("");
        if (sha256 !== image.sha256) throw error("原图片内容已变化，尚未创建新想法。", 409);
        const id = (await digestText(`${body.requestId}:${imageId}:${index}`)).slice(0, 32), copied = { ...image, id: `dialogue-image:${id}`, sessionId: null, clientId: null, sourceImageId: imageId, sourceIdeaIds: sources.filter(source => source.attachmentIds?.includes(imageId)).map(source => source.id), createdAt: stamp() };
        const old = await PhoneStore.get("media", copied.id);
        if (old) { if (old.sha256 !== sha256 || old.sourceImageId !== imageId || old.name !== image.name) throw error("同一图片副本不能换成其它内容。", 409); }
        else { await PhoneStore.add("media", copied); written.push(copied.id); }
        copies.push(copied);
      }
      if (copies.reduce((sum, image) => sum + image.size, 0) > 24 * 1024 * 1024) throw error("原图合计不能超过 24 MB。", 413);
      const proof = await Promise.all(sources.map(async source => ({ ideaId: source.id, revision: source.revision, sourceRecordId: source.workflowRecordId || null, sourceBodySha256: await digestText(source.body) })));
      return { title, sources, proof, content, executionDraft, points, copies, written };
    } catch (failure) { await Promise.allSettled(written.map(id => PhoneStore.remove("media", id))); throw failure; }
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
    const allowed = new Set(["mobile/dialogue/open", "mobile/dialogue/draft", "mobile/dialogue/clear", "mobile/dialogue/save", "mobile/idea/update", "mobile/idea/archive", ...managementRoutes]);
    if (!allowed.has(route)) throw error("此手机没有这个入口。", 404);
    let mediaProof = [];
    if (body.attachmentIds !== undefined) {
      if (!Array.isArray(body.attachmentIds) || body.attachmentIds.length > 4 || body.attachmentIds.some(id => !ID.test(id)) || new Set(body.attachmentIds).size !== body.attachmentIds.length) throw error("图片选择无效。");
      mediaProof = await Promise.all(body.attachmentIds.map(id => PhoneStore.get("media", `dialogue-image:${id}`)));
      if (mediaProof.some(item => item && (!item.blob || item.size !== item.blob.size || item.size > 8 * 1024 * 1024)) || mediaProof.reduce((sum, item) => sum + (item?.size || 0), 0) > 24 * 1024 * 1024) throw error("所选图片无法核对或总量超过 24 MB。", 413);
    }
    const saveSource = route === "mobile/dialogue/save" ? state(await PhoneStore.get("records", "incubator")) : null;
    const sourceSession = saveSource?.mobile.sessions[body.sessionId], sourceIdea = sourceSession?.ideaId && saveSource.ideas.find(item => item.id === sourceSession.ideaId);
    const retainedImages = sourceIdea ? await Promise.all((extended(saveSource, sourceIdea).attachmentIds || []).map(id => PhoneStore.get("media", `dialogue-image:${id}`))) : [];
    const management = managementRoutes.has(route) ? await prepareManagement(route, body) : null;
    let response;
    try { await PhoneStore.mutateRecord("records", "incubator", source => {
      const value = state(source), receiptKey = route + ":" + body.requestId, fingerprint = signature(body), receipt = value.mobile.receipts[receiptKey];
      if (receipt) {
        if (receipt.fingerprint !== fingerprint) throw error("同一保存请求不能换成不同内容。", 409);
        response = { ...structuredClone(receipt.response), duplicate: true };
        if (managementRoutes.has(route)) { const actual = value.ideas.find(idea => idea.id === response.idea?.id); if (!actual) throw error("原管理结果无法核对，未重复创建。", 409); response.idea = extended(value, actual); response.revision = String(value.revision); }
        if (response.session) response.session.isCurrent = value.mobile.current[response.session.clientId] === response.session.id;
        return value;
      }
      if (Object.keys(value.mobile.receipts).length >= 4096) throw error("此手机保存记录较多，请先备份；现有内容仍保留。", 409);
      if (management) {
        if (management.replay) throw error("原管理结果已变化，保留请求后核对，未重复创建。", 409);
        if (value.ideas.length >= 1000) throw error("此手机保存的想法较多，请先导出备份。", 409);
        for (const original of management.sources) { const actual = value.ideas.find(idea => idea.id === original.id); if (!actual || signature(extended(value, actual)) !== signature(original)) throw error("原想法已修改，请刷新后重新核对。", 409, "revision_conflict"); }
        const now = stamp(), id = body.requestId.replaceAll("-", "");
        if (value.ideas.some(idea => idea.id === id)) throw error("保存标识已被使用，请先核对原结果。", 409);
        const idea = { id, title: management.title, body: management.content, stage: "vague", priority: "normal", parentId: route.endsWith("split") ? management.sources[0].id : null, targetKind: "none", targetThreadId: "", targetName: "", revision: 1, createdAt: now, updatedAt: now };
        const provenance = { id: nextId(), kind: route.endsWith("split") ? "user_split" : "user_merge", sources: management.proof, sourceClaim: true, authorityVerified: false, destinationRevision: 1, createdAt: now, ...(route.endsWith("split") ? { start: body.start, end: body.end } : {}) };
        value.ideas.unshift(idea); value.mobile.metadata[id] = { projectId: null, archived: false, keyPoints: management.points, executionDraft: management.executionDraft, attachmentIds: management.copies.map(image => image.id.slice("dialogue-image:".length)), provenance: [provenance] };
        value.mobile.managementSources ||= {}; value.mobile.managementSources[id] = { sources: structuredClone(management.sources), proof: management.proof, images: management.copies.map(image => ({ sourceImageId: image.sourceImageId, copiedImageId: image.id.slice("dialogue-image:".length), sha256: image.sha256, size: image.size, mimeType: image.mimeType, name: image.name })), requestId: body.requestId, createdAt: now };
        response = { idea: extended(value, idea) };
      } else if (route === "mobile/dialogue/open") {
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
          if (session.ideaId && value.ideas.find(idea => idea.id === session.ideaId)?.revision !== session.ideaRevision) throw error("想法已修改，请刷新后重新核对。", 409, "revision_conflict");
          const content = text(body.text), attachmentIds = body.attachmentIds || [];
          if (mediaProof.some((item, index) => !item?.blob || item.kind !== "dialogue_image" || !(item.sessionId === session.id && item.clientId === session.clientId || session.ideaId && (session.eligibleAttachmentIds || []).includes(attachmentIds[index])))) throw error("图片尚未完整保存在当前讨论，内容仍保留。", 409);
          if (!profiles.has(body.requestedProfile || session.requestedProfile)) throw error("请选择有效档位。");
          session.draft = { text: content, attachmentIds }; session.requestedProfile = body.requestedProfile || session.requestedProfile;
          value.mobile.profile = session.requestedProfile; session.revision++; session.updatedAt = stamp();
          if (route === "mobile/dialogue/save") {
            if (!content.trim() && !attachmentIds.length) throw error("先写下一点想法或选择图片。");
            const now = stamp(), ideaId = body.requestId.replaceAll("-", "");
            const existing = session.ideaId ? value.ideas.find(item => item.id === session.ideaId) : null;
            if (session.ideaId && (!existing || existing.revision !== session.ideaRevision)) throw error("想法已修改，请刷新后合并。", 409, "revision_conflict");
            if (!existing && value.ideas.length >= 1000) throw error("此手机保存的想法较多，请先导出备份。", 409);
            const idea = existing || { id: ideaId, title: Array.from(content.trim().split(/\r?\n/)[0]).slice(0, 80).join("") || mediaProof[0]?.name || "图片想法", body: content, stage: "vague", priority: "normal", parentId: null, targetKind: "none", targetThreadId: "", targetName: "", revision: 1, createdAt: now, updatedAt: now };
            if (existing) { idea.body = text(idea.body + (content && idea.body ? "\n\n" : "") + content); idea.revision++; idea.updatedAt = now; session.ideaRevision = idea.revision; }
            else { value.ideas.unshift(idea); value.mobile.metadata[ideaId] = { projectId: null, archived: false, keyPoints: [], executionDraft: "", provenance: [] }; }
            const metadata = value.mobile.metadata[idea.id] ||= { projectId: null, archived: false, keyPoints: [], executionDraft: "", provenance: [] };
            const combinedIds = [...new Set([...(metadata.attachmentIds || []), ...attachmentIds])], imagePool = [...retainedImages, ...mediaProof];
            if (combinedIds.length > 4) throw error("一条想法最多保存四张图片；原内容与图片草稿保留，可另存一个想法。", 413);
            const savedImages = combinedIds.map(id => imagePool.find(item => item?.id === `dialogue-image:${id}`));
            if (savedImages.some(item => !item?.blob || item.blob.size !== item.size) || savedImages.reduce((sum, item) => sum + (item?.size || 0), 0) > 24 * 1024 * 1024) throw error("此想法图片无法核对或总量超过 24 MB；原内容与草稿保留。", 413);
            metadata.attachmentIds = combinedIds;
            metadata.provenance.push({ source: "phone_local", sessionId: session.id, attachmentIds: [...attachmentIds], createdAt: now });
            session.ideaId = idea.id; session.ideaRevision = idea.revision;
            session.eligibleAttachmentIds = [...metadata.attachmentIds];
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
            const seen = new Set(); metadata.keyPoints = body.keyPoints.map(item => { if (!ID.test(item.id || "") || seen.has(item.id) || !["suggestion", "decision"].includes(item.kind)) throw error("长期要点身份或类型无效。"); seen.add(item.id); return { id: item.id, text: text(item.text), kind: item.kind }; });
          }
        }
        value.mobile.metadata[idea.id] = { projectId: null, archived: metadata.archived, keyPoints: metadata.keyPoints, executionDraft: metadata.executionDraft, attachmentIds: metadata.attachmentIds, provenance: metadata.provenance };
        idea.revision++; idea.updatedAt = stamp(); response = { idea: extended(value, idea), revision: String(value.revision + 1), localOnly: true };
      }
      value.revision++; response.revision = String(value.revision); response.localOnly = true;
      value.mobile.receipts[receiptKey] = { fingerprint, response: structuredClone(response) }; return value;
    }); } catch (failure) { if (management) await Promise.allSettled(management.written.map(id => PhoneStore.remove("media", id))); throw failure; }
    return hydrate(response);
  }
  const exportIdea = idea => ({ title: idea.title, body: idea.body, executionDraft: idea.executionDraft || "", archived: Boolean(idea.archived), keyPoints: (idea.keyPoints || []).map(item => ({ id: item.id, text: item.text, kind: item.kind })) });
  async function sourceStoreId() {
    const saved = await PhoneStore.mutateRecord("settings", "mobileIdeaSource", source => {
      if (source?.sourceStoreId && !UUID.test(source.sourceStoreId)) throw error("手机来源身份无法核对，原资料仍保留。", 409);
      return source ? { ...source, sourceStoreId: source.sourceStoreId.toLowerCase() } : { id: "mobileIdeaSource", sourceStoreId: crypto.randomUUID() };
    });
    return saved.sourceStoreId;
  }
  async function buildExport(ideaId, expectedRevision, portable = false) {
    if (!window.CodexMobileHandoff || !ID.test(ideaId || "") || !Number.isSafeInteger(expectedRevision) || expectedRevision < 1) throw error("请选择已经保存的准确想法版本。");
    const sourceId = await sourceStoreId(), before = state(await PhoneStore.get("records", "incubator")), original = before.ideas.find(item => item.id === ideaId);
    if (!original || original.revision !== expectedRevision) throw error("想法已修改，请刷新保存后再带到电脑。", 409, "revision_conflict");
    const idea = extended(before, original), imageIds = idea.attachmentIds || [], files = [], images = [];
    for (const id of imageIds) {
      const item = await PhoneStore.get("media", `dialogue-image:${id}`);
      if (!ID.test(id || "") || !item?.blob || item.kind !== "dialogue_image" || item.size !== item.blob.size || item.mimeType !== item.blob.type || await window.CodexMobileHandoff.digest(item.blob) !== item.sha256) throw error("已保存图片的实际文件或校验值缺失，未交给电脑。", 409);
      files.push(item.blob); images.push({ id, name: item.name, mimeType: item.mimeType, size: item.size, sha256: item.sha256 });
    }
    const manifest = { format: "codex-console-idea", version: 1, source: { clientId: sourceId, ideaId, revision: expectedRevision }, idea: exportIdea(idea), images }, manifestText = JSON.stringify(manifest);
    await window.CodexMobileHandoff.verify(manifestText, files);
    let frozen;
    await PhoneStore.mutateRecord("records", "incubator", source => {
      const value = state(source), actual = value.ideas.find(item => item.id === ideaId);
      if (!actual || actual.revision !== expectedRevision || JSON.stringify(exportIdea(extended(value, actual))) !== JSON.stringify(manifest.idea) || JSON.stringify(extended(value, actual).attachmentIds || []) !== JSON.stringify(imageIds)) throw error("准备交接时想法已修改，请刷新后再试。", 409, "revision_conflict");
      value.mobile.handoffs ||= {};
      const entries = value.mobile.handoffs[ideaId] ||= {}, previous = Object.values(entries).find(item => item.status === "pending" && item.source.revision !== expectedRevision);
      if (previous) throw error("此想法上一版本的导入结果还待核对，请在更多里点「核对上次交接」。", 409);
      const existing = entries[expectedRevision];
      if (existing && (existing.text !== manifestText || existing.source.clientId !== sourceId)) throw error("同一想法版本的交接内容不一致，原交接凭据仍保留。", 409);
      if (portable && existing?.attemptedAt) throw error("这个版本已尝试交接，请先核对原回执，不能生成另一份重送包。", 409);
      frozen = existing || { requestId: crypto.randomUUID(), text: manifestText, source: manifest.source, imageIds: [...imageIds], status: portable ? "exported" : "prepared", createdAt: stamp() };
      entries[expectedRevision] = frozen; return value;
    });
    return { requestId: frozen.requestId, text: frozen.text, files, source: frozen.source, destinationOrigin: frozen.destinationOrigin || null, attemptedAt: frozen.attemptedAt || null, status: frozen.status };
  }
  async function saveReceipt(exported, receipt) {
    window.CodexMobileHandoff.verifyReceipt(receipt, exported);
    const source = window.CodexMobileHandoff.decode(exported.text).source;
    await PhoneStore.mutateRecord("records", "incubator", input => {
      const value = state(input), frozen = value.mobile.handoffs?.[source.ideaId]?.[source.revision];
      if (!frozen || frozen.requestId !== exported.requestId || frozen.text !== exported.text || frozen.destinationOrigin && frozen.destinationOrigin !== exported.destinationOrigin || frozen.receipt && frozen.receipt.imported.ideaId !== receipt.imported.ideaId) throw error("导入回执不能替换另一条想法或电脑入口的交接凭据。", 409);
      frozen.status = "completed"; frozen.receipt = structuredClone(receipt); frozen.receivedAt = stamp(); return value;
    });
    return { receipt, localRetained: true };
  }
  async function markAttempted(exported, destinationOrigin) {
    if (window.CodexMobileHandoff.targetAddress(destinationOrigin + "/").origin !== destinationOrigin) throw error("电脑入口无法准确核对，尚未传送。");
    const source = window.CodexMobileHandoff.decode(exported.text).source;
    await PhoneStore.mutateRecord("records", "incubator", input => { const value = state(input), frozen = value.mobile.handoffs?.[source.ideaId]?.[source.revision]; if (!frozen || frozen.requestId !== exported.requestId || frozen.text !== exported.text) throw error("交接凭据未完整保存在手机，尚未传送。", 409); if (frozen.destinationOrigin && frozen.destinationOrigin !== destinationOrigin) throw error("原交接已绑定另一台电脑入口，未传送到当前电脑。", 409); frozen.destinationOrigin = destinationOrigin; frozen.attemptedAt ||= stamp(); if (frozen.status !== "completed") frozen.status = "pending"; return value; });
    exported.destinationOrigin = destinationOrigin;
    exported.attemptedAt ||= stamp(); if (exported.status !== "completed") exported.status = "pending";
  }
  async function buildPendingExport(ideaId) {
    if (!ID.test(ideaId || "")) throw error("请选择需要核对的准确想法。");
    const value = state(await PhoneStore.get("records", "incubator")), pending = Object.values(value.mobile.handoffs?.[ideaId] || {}).filter(item => item.status === "pending");
    if (pending.length !== 1) throw error(pending.length ? "这条想法有多个交接凭据，需先核对来源。" : "这条想法没有待核对的交接。", 409);
    const frozen = pending[0], manifest = window.CodexMobileHandoff.decode(frozen.text), files = [];
    if (manifest.source.ideaId !== ideaId || !UUID.test(frozen.requestId) || JSON.stringify(manifest.source) !== JSON.stringify(frozen.source) || JSON.stringify(manifest.images.map(item => item.id)) !== JSON.stringify(frozen.imageIds)) throw error("原交接凭据与想法来源不一致。", 409);
    for (const image of manifest.images) { const item = await PhoneStore.get("media", `dialogue-image:${image.id}`); if (!item?.blob || item.kind !== "dialogue_image" || item.name !== image.name || item.mimeType !== image.mimeType || item.size !== image.size || item.sha256 !== image.sha256) throw error("上次交接的原图片暂时无法核对，原凭据仍保留。", 409); files.push(item.blob); }
    await window.CodexMobileHandoff.verify(frozen.text, files);
    return { requestId: frozen.requestId, text: frozen.text, files, source: manifest.source, destinationOrigin: frozen.destinationOrigin || null, attemptedAt: frozen.attemptedAt || null, status: frozen.status };
  }
  async function saveRejected(exported, rejection) {
    if (!([400, 413, 415, 429].includes(rejection.status) || rejection.status === 409 && ["import_source_conflict", "import_revision_conflict", "import_conflict"].includes(rejection.code))) throw error("不能把未知交接结果标为未导入。", 409);
    const source = window.CodexMobileHandoff.decode(exported.text).source;
    await PhoneStore.mutateRecord("records", "incubator", input => { const value = state(input), frozen = value.mobile.handoffs?.[source.ideaId]?.[source.revision]; if (!frozen || frozen.requestId !== exported.requestId || frozen.text !== exported.text || frozen.status === "completed") throw error("拒绝凭据不属于这次待核对交接。", 409); frozen.status = "rejected"; frozen.rejection = { status: rejection.status, code: rejection.code || "rejected", message: String(rejection.message || "电脑明确拒绝导入"), rejectedAt: stamp() }; return value; });
  }
  window.CodexPhoneDialogueLocal = { endpoint, uploadAttachments, buildExport, buildPendingExport, markAttempted, saveReceipt, saveRejected };
})();
