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
    add: async (name, value) => { if (store(name).has(value.id)) throw Object.assign(new Error("Original media already exists"), { name: "ConstraintError" }); writes++; store(name).set(value.id, clone(value)); },
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
await assert.rejects(() => api.uploadAttachments([image, changedImage], imageSession.session, imageRequest), /不能换成其它内容/);
assert.equal(media.size, 1, "same upload nonce freezes the entire image manifest, including count");
const imageSave = await post("mobile/dialogue/save", { clientId: imageSession.session.clientId, sessionId: imageSession.session.id, expectedRevision: imageSession.session.revision, text: "", attachmentIds: [uploaded.attachments[0].id], requestedProfile: "high" });
assert.equal(imageSave.idea.title, "底稿.png"); assert.equal(imageSave.idea.attachmentIds.length, 1); assert.equal(imageSave.session.draft.attachmentIds.length, 0);
const readImage = await api.endpoint(`mobile/idea?id=${imageSave.idea.id}`);
assert.equal(readImage.detail.attachments[0].name, "底稿.png"); assert.match(readImage.detail.attachments[0].url, /^blob:/);
const imageClear = await post("mobile/dialogue/clear", { clientId: imageSession.session.clientId, sessionId: imageSave.session.id, expectedRevision: imageSave.session.revision });
assert.equal(imageClear.session.ideaId, null);
assert.equal((await api.endpoint(`mobile/idea?id=${imageSave.idea.id}`)).detail.attachments[0].id, uploaded.attachments[0].id);
const otherImageScope = await post("mobile/dialogue/open", { clientId, ideaId: legacyId, expectedIdeaRevision: 1 });
await assert.rejects(() => post("mobile/dialogue/save", { ...scope(otherImageScope.session), text: "跨讨论图片", attachmentIds: [uploaded.attachments[0].id] }), /图片尚未完整/);

const imageClientId = imageSession.session.clientId;
const reuse = await post("mobile/dialogue/open", { clientId: imageClientId, ideaId: imageSave.idea.id, expectedIdeaRevision: imageSave.idea.revision });
assert.equal(reuse.session.draft.attachmentIds.length, 0);
assert.deepEqual(Array.from(reuse.session.eligibleAttachmentIds), [uploaded.attachments[0].id]);
assert.equal(reuse.eligibleAttachments[0].name, "底稿.png");
const reused = await post("mobile/dialogue/draft", { clientId: imageClientId, sessionId: reuse.session.id, expectedRevision: reuse.session.revision, text: "使用原图继续", attachmentIds: [uploaded.attachments[0].id] });
assert.deepEqual(Array.from(reused.session.draft.attachmentIds), [uploaded.attachments[0].id]);
assert.equal(media.size, 1, "reuse should retain original bytes, not upload again");
const sourceChanged = await post("mobile/idea/update", { id: imageSave.idea.id, expectedRevision: imageSave.idea.revision, body: "另一端已修改图稿" });
await assert.rejects(() => post("mobile/dialogue/draft", { clientId: imageClientId, sessionId: reused.session.id, expectedRevision: reused.session.revision, text: "不能沿用旧图稿版本", attachmentIds: [uploaded.attachments[0].id] }), e => e.code === "revision_conflict");
const mediaBeforeRejectedUpload = media.size;
await assert.rejects(() => api.uploadAttachments([image], reused.session, { requestId: randomUUID(), recordId: reused.session.recordId }), e => e.code === "revision_conflict");
assert.equal(media.size, mediaBeforeRejectedUpload, "a stale source must not create orphan media");
const resetReuse = await post("mobile/dialogue/clear", { clientId: imageClientId, sessionId: reused.session.id, expectedRevision: reused.session.revision });
assert.equal(resetReuse.session.eligibleAttachmentIds.length, 0);

const splitSource = await post("mobile/idea/update", { id: legacyId, expectedRevision: 1, body: "前😀后\n保留原文", executionDraft: "原执行稿", keyPoints: [{ id: "c".repeat(32), text: "只是一项建议", kind: "suggestion" }] });
const splitRequest = { requestId: randomUUID(), id: legacyId, expectedRevision: splitSource.idea.revision, start: 1, end: 2, title: "拆出的表情" };
const sourceBeforeSplit = JSON.stringify((await api.endpoint(`mobile/idea?id=${legacyId}`)).idea);
const split = await api.endpoint("mobile/idea/split", splitRequest);
assert.equal(split.idea.body, "😀"); assert.equal(split.idea.executionDraft, ""); assert.equal(split.idea.keyPoints.length, 0); assert.equal(split.idea.attachmentIds.length, 0);
assert.equal(split.idea.provenance[0].kind, "user_split"); assert.equal(split.idea.provenance[0].authorityVerified, false);
assert.equal(JSON.stringify((await api.endpoint(`mobile/idea?id=${legacyId}`)).idea), sourceBeforeSplit);
assert.equal(records.get("incubator").mobile.managementSources[split.idea.id].sources[0].body, splitSource.idea.body);
await assert.rejects(() => post("mobile/idea/split", { ...splitRequest, requestId: randomUUID(), start: 1, end: 1000 }), /准确文字范围/);
const changedSplit = await post("mobile/idea/update", { id: split.idea.id, expectedRevision: split.idea.revision, title: "已编辑拆分结果" });
await post("mobile/idea/update", { id: legacyId, expectedRevision: splitSource.idea.revision, body: "原想法以后再改" });
const splitRetry = await api.endpoint("mobile/idea/split", splitRequest);
assert.equal(splitRetry.duplicate, true); assert.equal(splitRetry.idea.id, split.idea.id); assert.equal(splitRetry.idea.revision, changedSplit.idea.revision);
await assert.rejects(() => api.endpoint("mobile/idea/split", { ...splitRequest, title: "同编号改内容" }), /不同内容/);

const mergeFirst = await api.endpoint(`mobile/idea?id=${legacyId}`);
const mergeSecond = await post("mobile/idea/update", { id: split.idea.id, expectedRevision: changedSplit.idea.revision, executionDraft: "新执行稿", keyPoints: [{ id: "d".repeat(32), text: "只是一项建议", kind: "suggestion" }, { id: "e".repeat(32), text: "只是一项建议", kind: "decision" }] });
const mergeRequest = { requestId: randomUUID(), firstId: mergeFirst.idea.id, firstRevision: mergeFirst.idea.revision, secondId: mergeSecond.idea.id, secondRevision: mergeSecond.idea.revision, title: "明确合成第三份" };
const sourcePair = [mergeFirst.idea, mergeSecond.idea].map(idea => JSON.stringify(idea));
const merged = await api.endpoint("mobile/idea/merge", mergeRequest);
assert.equal(merged.idea.body, mergeFirst.idea.body + "\n\n" + mergeSecond.idea.body);
assert.equal(merged.idea.executionDraft, "原执行稿\n\n新执行稿");
assert.deepEqual(Array.from(merged.idea.keyPoints, point => point.kind), ["suggestion", "decision"]);
assert.equal(merged.idea.provenance[0].sources.length, 2); assert.equal(merged.idea.archived, false); assert.equal(merged.idea.targetKind, "none");
for (const [index, id] of [mergeFirst.idea.id, mergeSecond.idea.id].entries()) assert.equal(JSON.stringify((await api.endpoint(`mobile/idea?id=${id}`)).idea), sourcePair[index]);
assert.equal((await api.endpoint("mobile/idea/merge", mergeRequest)).idea.id, merged.idea.id);
await assert.rejects(() => post("mobile/idea/merge", { ...mergeRequest, requestId: randomUUID(), secondId: mergeFirst.idea.id, secondRevision: mergeFirst.idea.revision }), /不同的已保存/);
await assert.rejects(() => post("mobile/idea/merge", { ...mergeRequest, requestId: randomUUID(), firstRevision: mergeFirst.idea.revision - 1 }), e => e.code === "revision_conflict");
await assert.rejects(() => post("mobile/idea/split", { id: legacyId, expectedRevision: mergeFirst.idea.revision, start: 0, end: 1, title: "拒绝其它想法图片", attachmentIds: [uploaded.attachments[0].id] }), /不属于/);
const copiedImage = await post("mobile/idea/split", { id: sourceChanged.idea.id, expectedRevision: sourceChanged.idea.revision, start: 0, end: 1, title: "明确复制一张原图", attachmentIds: [uploaded.attachments[0].id] });
assert.equal(copiedImage.idea.attachmentIds.length, 1); assert.notEqual(copiedImage.idea.attachmentIds[0], uploaded.attachments[0].id);
const originalMedia = media.get(`dialogue-image:${uploaded.attachments[0].id}`), copiedMedia = media.get(`dialogue-image:${copiedImage.idea.attachmentIds[0]}`);
assert.equal(copiedMedia.sha256, originalMedia.sha256); assert.deepEqual(new Uint8Array(await copiedMedia.blob.arrayBuffer()), new Uint8Array(await originalMedia.blob.arrayBuffer()));
const accumulatingClient = randomUUID();
let accumulating = await post("mobile/dialogue/open", { clientId: accumulatingClient }), latest;
for (let index = 0; index < 4; index++) {
  const added = await api.uploadAttachments([image], accumulating.session, { requestId: randomUUID(), recordId: accumulating.session.recordId });
  latest = await post("mobile/dialogue/save", { clientId: accumulatingClient, sessionId: accumulating.session.id, expectedRevision: accumulating.session.revision, text: `原图${index}`, attachmentIds: [added.attachments[0].id] });
  accumulating = latest;
}
assert.equal(latest.idea.attachmentIds.length, 4);
const fifth = await api.uploadAttachments([image], accumulating.session, { requestId: randomUUID(), recordId: accumulating.session.recordId });
const fifthDraft = await post("mobile/dialogue/draft", { clientId: accumulatingClient, sessionId: accumulating.session.id, expectedRevision: accumulating.session.revision, text: "第五张原图片草稿", attachmentIds: [fifth.attachments[0].id] });
const savedFour = JSON.stringify((await api.endpoint(`mobile/idea?id=${latest.idea.id}`)).idea), mediaBeforeLimit = media.size;
await assert.rejects(() => post("mobile/dialogue/save", { clientId: accumulatingClient, sessionId: fifthDraft.session.id, expectedRevision: fifthDraft.session.revision, text: fifthDraft.session.draft.text, attachmentIds: fifthDraft.session.draft.attachmentIds }), /最多保存四张/);
assert.equal(JSON.stringify((await api.endpoint(`mobile/idea?id=${latest.idea.id}`)).idea), savedFour);
assert.equal((await api.endpoint(`mobile/dialogue?clientId=${accumulatingClient}`)).session.draft.text, "第五张原图片草稿");
assert.equal(media.size, mediaBeforeLimit, "capacity rejection must preserve the fifth original draft image");
const racing = await post("mobile/dialogue/open", { clientId: randomUUID() }), racingRequest = { requestId: randomUUID(), recordId: racing.session.recordId };
const racingUploads = await Promise.allSettled([api.uploadAttachments([image], racing.session, racingRequest), api.uploadAttachments([image], racing.session, racingRequest)]);
const acceptedUpload = racingUploads.find(result => result.status === "fulfilled");
assert.ok(acceptedUpload, "one actual upload must remain accepted");
const acceptedId = acceptedUpload.value.attachments[0].id;
assert.ok(media.get(`dialogue-image:${acceptedId}`)?.blob, "a concurrent duplicate must never delete the accepted original");
const raceRetry = await api.uploadAttachments([image], racing.session, racingRequest);
assert.equal(raceRetry.duplicate, true); assert.equal(raceRetry.attachments[0].id, acceptedId);
assert.equal(records.get("incubator").receipts.old.signature, "preserved");
const longClient = randomUUID(), longSession = await post("mobile/dialogue/open", { clientId: longClient });
const longSaved = await post("mobile/dialogue/save", { clientId: longClient, sessionId: longSession.session.id, expectedRevision: longSession.session.revision, text: "长要点的原正文", attachmentIds: [] });
const longPoint = "😀".repeat(20000), longPointId = "f".repeat(32);
const longEdited = await post("mobile/idea/update", { id: longSaved.idea.id, expectedRevision: longSaved.idea.revision, executionDraft: longPoint, keyPoints: [{ id: longPointId, text: longPoint, kind: "suggestion" }] });
assert.equal(longEdited.idea.keyPoints[0].text, longPoint); assert.equal(longEdited.idea.executionDraft, longPoint); assert.equal(Array.from(longPoint).length, 20000);
const longSnapshot = clone(records.get("incubator"));
await assert.rejects(() => post("mobile/idea/update", { id: longEdited.idea.id, expectedRevision: longEdited.idea.revision, keyPoints: [{ id: longPointId, text: longPoint + "😀", kind: "suggestion" }] }), /过长/);
assert.deepEqual(records.get("incubator"), longSnapshot, "one extra Unicode codepoint must not replace the legal original or its receipt");
const otherLongClient = randomUUID(), otherLongSession = await post("mobile/dialogue/open", { clientId: otherLongClient }), otherLongSaved = await post("mobile/dialogue/save", { clientId: otherLongClient, sessionId: otherLongSession.session.id, expectedRevision: otherLongSession.session.revision, text: "另一条新想法", attachmentIds: [] });
const longMerged = await post("mobile/idea/merge", { firstId: longEdited.idea.id, firstRevision: longEdited.idea.revision, secondId: otherLongSaved.idea.id, secondRevision: otherLongSaved.idea.revision, title: "完整Unicode要点合并" });
assert.equal(longMerged.idea.keyPoints[0].text, longPoint); assert.equal(longMerged.idea.keyPoints[0].kind, "suggestion"); assert.ok(longMerged.idea.executionDraft.startsWith(longPoint));
console.log("Mobile local dialogue: drafts, clear isolation, explicit source-image reuse, immutable split/merge sources, nonce retries, Unicode ranges and original image bytes passed.");
