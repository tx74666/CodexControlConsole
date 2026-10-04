// Local persistence checks run in an isolated store; no phone or production writes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { randomUUID, webcrypto } from "node:crypto";
import { runInNewContext } from "node:vm";

const records = new Map(), media = new Map();
const clone = value => value === undefined ? undefined : structuredClone(value);
const store = name => name === "records" ? records : media;
let writes = 0;
const context = {
  window: {}, crypto: { randomUUID, subtle: webcrypto.subtle }, structuredClone, URL, URLSearchParams, Blob, TextEncoder,
  PhoneStore: {
    get: async (name, id) => clone(store(name).get(id)),
    put: async (name, value) => { writes++; store(name).set(value.id, clone(value)); },
    remove: async (name, id) => store(name).delete(id),
    mutateRecord: async (name, id, change) => {
      const next = change(clone(store(name).get(id))); writes++; store(name).set(id, clone(next)); return clone(next);
    }
  }
};
runInNewContext(readFileSync(new URL("../phone/dialogue-local.js", import.meta.url), "utf8"), context);
const api = context.window.CodexPhoneDialogueLocal, clientId = randomUUID();
const post = (route, body) => api.endpoint(route, { requestId: randomUUID(), ...body });
const scope = session => ({ clientId, sessionId: session.id, expectedRevision: session.revision });
const legacyId = "a".repeat(32);
records.set("incubator", { id: "incubator", ideas: [{ id: legacyId, title: "已有想法", body: "原底稿", revision: 1, updatedAt: "2026-10-01T00:00:00Z" }], receipts: { old: { signature: "preserved" } }, revision: 1 });

const fresh = await api.endpoint(`mobile/dialogue?clientId=${clientId}`);
assert.equal(fresh.session, null); assert.equal(fresh.preferences.requestedProfile, "high"); assert.equal(fresh.execution.actualReceipt.verified, false);
const a = await post("mobile/dialogue/open", { clientId });
const draft = await post("mobile/dialogue/draft", { ...scope(a.session), text: "裙子保留双模式", attachmentIds: [], requestedProfile: "pro" });
assert.equal(draft.session.draft.text, "裙子保留双模式");
assert.equal((await api.endpoint(`mobile/dialogue?clientId=${clientId}`)).session.draft.text, "裙子保留双模式");
const request = { requestId: randomUUID(), ...scope(draft.session), text: "裙子保留双模式", attachmentIds: [], requestedProfile: "pro" };
const saved = await api.endpoint("mobile/dialogue/save", request), repeat = await api.endpoint("mobile/dialogue/save", request);
assert.equal(saved.idea.id, repeat.idea.id); assert.equal(repeat.duplicate, true); assert.equal(saved.session.draft.text, "");
assert.equal(saved.session.ideaId, saved.idea.id); assert.equal(saved.session.ideaRevision, saved.idea.revision);
assert.equal((await api.endpoint(`mobile/dialogue?clientId=${clientId}`)).session.draft.text, "");
await assert.rejects(() => api.endpoint("mobile/dialogue/save", { ...request, text: "不能换正文" }), /不同内容/);
const ordinaryAppend = await post("mobile/dialogue/save", { ...scope(saved.session), text: "首保存后同一主题追加", attachmentIds: [], requestedProfile: "pro" });
assert.equal(ordinaryAppend.idea.id, saved.idea.id); assert.equal((await api.endpoint("mobile/ideas?archived=0")).ideas.length, 2);
const clear = await post("mobile/dialogue/clear", scope(ordinaryAppend.session));
assert.notEqual(clear.session.id, saved.session.id); assert.equal(clear.session.requestedProfile, "pro");
assert.equal(clear.session.ideaId, null); assert.equal(clear.session.ideaRevision, null);
const oldReceipt = await api.endpoint("mobile/dialogue/save", request);
assert.equal(oldReceipt.session.isCurrent, false); assert.equal((await api.endpoint(`mobile/dialogue?clientId=${clientId}`)).session.id, clear.session.id);
await assert.rejects(() => post("mobile/dialogue/draft", { ...scope(saved.session), text: "旧讨论迟到", attachmentIds: [] }), value => value.status === 409 && value.code === "dialogue_changed");
assert.equal((await api.endpoint("mobile/ideas?archived=0")).ideas.length, 2);
const newIdea = await post("mobile/dialogue/save", { ...scope(clear.session), text: "清空后另一件事", attachmentIds: [], requestedProfile: "pro" });
assert.notEqual(newIdea.idea.id, saved.idea.id); assert.equal((await api.endpoint("mobile/ideas?archived=0")).ideas.length, 3);
assert.equal((await api.endpoint(`mobile/idea?id=${saved.idea.id}`)).idea.body, ordinaryAppend.idea.body);
const discussion = await post("mobile/dialogue/open", { clientId, ideaId: saved.idea.id, expectedIdeaRevision: ordinaryAppend.idea.revision });
const conflictWrites = writes;
await assert.rejects(() => post("mobile/dialogue/save", { ...scope(discussion.session), expectedRevision: discussion.session.revision - 1, text: "版本冲突不能保存", attachmentIds: [], requestedProfile: "high" }), value => value.status === 409 && value.code === "revision_conflict");
assert.equal(writes, conflictWrites); assert.equal((await api.endpoint(`mobile/dialogue?clientId=${clientId}`)).session.revision, discussion.session.revision);
const append = await post("mobile/dialogue/save", { ...scope(discussion.session), text: "以后再想切换方式", attachmentIds: [], requestedProfile: "high" });
assert.equal(append.idea.id, saved.idea.id); assert.equal((await api.endpoint("mobile/ideas?archived=0")).ideas.length, 3);
assert.match(append.idea.body, /双模式\n\n首保存后同一主题追加\n\n以后/); assert.equal(append.idea.provenance.length, 3);
const edited = await post("mobile/idea/update", { id: append.idea.id, expectedRevision: append.idea.revision, executionDraft: "实现切换", keyPoints: [{ id: "b".repeat(32), text: "尚未确认方案", kind: "suggestion" }] });
assert.equal(edited.idea.keyPoints[0].kind, "suggestion"); assert.equal(edited.idea.executionDraft, "实现切换");
const archived = await post("mobile/idea/archive", { id: edited.idea.id, expectedRevision: edited.idea.revision, archived: true });
assert.equal(archived.idea.provenance.length, 3); assert.equal((await api.endpoint("mobile/ideas?archived=1&search=双模式&projectId=unclassified")).ideas.length, 1);
assert.equal((await api.endpoint("mobile/ideas?projectId=unknown-project")).ideas.length, 0);
assert.equal(records.get("incubator").receipts.old.signature, "preserved"); assert.equal(records.get("incubator").ideas.find(item => item.id === legacyId).body, "原底稿");
const before = writes;
await assert.rejects(() => post("mobile/dialogue/send", { ...scope(clear.session), text: "你好" }), /转发器尚未连接/);
assert.equal(writes, before);
const imageSession = await post("mobile/dialogue/open", { clientId: randomUUID() });
const image = new Blob([Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10])], { type: "image/png" }); image.name = "底稿.png";
const imageRequest = { requestId: randomUUID(), recordId: imageSession.session.recordId };
const uploaded = await api.uploadAttachments([image], imageSession.session, imageRequest);
const imageWriteCount = writes;
const duplicateUpload = await api.uploadAttachments([image], imageSession.session, imageRequest);
assert.equal(duplicateUpload.attachments[0].id, uploaded.attachments[0].id); assert.equal(writes, imageWriteCount);
const changedImage = new Blob([Uint8Array.from([1, 2, 3])], { type: "image/png" }); changedImage.name = "底稿.png";
await assert.rejects(() => api.uploadAttachments([changedImage], imageSession.session, imageRequest), /不能换成其它内容/);
const imageSave = await post("mobile/dialogue/save", { clientId: imageSession.session.clientId, sessionId: imageSession.session.id, expectedRevision: imageSession.session.revision, text: "", attachmentIds: [uploaded.attachments[0].id], requestedProfile: "high" });
assert.equal(imageSave.idea.title, "底稿.png"); assert.equal(imageSave.idea.attachmentIds.length, 1); assert.equal(imageSave.session.draft.attachmentIds.length, 0);
const readImage = await api.endpoint(`mobile/idea?id=${imageSave.idea.id}`);
assert.equal(readImage.detail.attachments[0].name, "底稿.png"); assert.match(readImage.detail.attachments[0].url, /^blob:/);
const imageClear = await post("mobile/dialogue/clear", { clientId: imageSession.session.clientId, sessionId: imageSave.session.id, expectedRevision: imageSave.session.revision });
assert.equal(imageClear.session.ideaId, null);
assert.equal((await api.endpoint(`mobile/idea?id=${imageSave.idea.id}`)).detail.attachments[0].id, uploaded.attachments[0].id);
await assert.rejects(() => post("mobile/dialogue/save", { ...scope(append.session), text: "跨讨论图片", attachmentIds: [uploaded.attachments[0].id] }), /图片尚未完整/);
console.log("Mobile local dialogue: existing data, drafts, nonce retries, clear isolation, append, archive, profile, image provenance passed.");
