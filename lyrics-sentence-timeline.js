/* Sentence timing drafts are separate from Insert's acknowledged mark journal. */
(function (root) {
  "use strict";
  const copy = value => JSON.parse(JSON.stringify(value));
  const keyOf = point => `${point.lineIndex}:${point.role}`;
  const round = value => Math.round(value * 1000) / 1000;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const storageKey = "codexControl.sentenceTimelineDrafts.v1";

  function createController(hooks) {
    let context = null, draft = null, visible = false, selected = "", drag = null;
    let start = 0, span = 10, follow = true, error = "", busy = false;
    let stored = {};
    const acknowledged = new Map();
    try {
      const saved = JSON.parse(hooks.storage?.getItem(storageKey) || "null");
      if (saved?.schema === 1 && saved.drafts && typeof saved.drafts === "object") stored = saved.drafts;
    } catch { error = "storage"; }
    const labels = () => hooks.labels();
    const cleanupPending = () => Boolean(context && [...acknowledged.values()].includes(JSON.stringify([context.key, context.signature])));
    function write(next = stored) {
      try {
        if (Object.keys(next).length) hooks.storage?.setItem(storageKey, JSON.stringify({ schema: 1, drafts: next }));
        else hooks.storage?.removeItem(storageKey);
        stored = next;
        return true;
      } catch { error = "storage"; return false; }
    }
    function points() {
      if (!context) return [];
      return context.points.map(point => ({ ...point, time: draft?.changes[keyOf(point)]?.time ?? point.time,
        changed: Boolean(draft?.changes[keyOf(point)]) }));
    }
    function setContext(next) {
      if (!next?.key || !Array.isArray(next.points)) { context = null; draft = null; render(); return; }
      const switched = context?.key !== next.key;
      context = next;
      const saved = stored[next.key];
      // A changed lyric source is retained for recovery, never mapped onto different lines.
      draft = saved?.signature === next.signature && saved.changes && saved.history ? saved : null;
      if (draft && Object.values(draft.changes).every(change => {
        const point = next.points.find(p => keyOf(p) === keyOf(change));
        return point?.expectedTime === change.time && point.manualNote === "manual sentence timeline";
      })) acknowledged.set(JSON.stringify([next.key, next.signature, draft.changes]), JSON.stringify([next.key, next.signature]));
      if (saved && !draft) error = "sourceChanged";
      else if (cleanupPending()) error = "cleanup";
      else if (switched) error = "";
      if (switched) { selected = ""; drag = null; start = 0; span = 10; follow = true; }
      render();
    }
    function violations(next) {
      const rows = context.rows;
      const errors = {};
      for (let i = 0; i < rows.length; i += 1) {
        const first = next.find(p => p.lineIndex === rows[i] && p.role === "start");
        const last = next.find(p => p.lineIndex === rows[i] && p.role === "end");
        if (first && last && last.time <= first.time) errors[`${rows[i]}:length`] = first.time - last.time + .001;
        for (const point of [first, last].filter(Boolean)) {
          if (!finite(point.time)) errors[`${keyOf(point)}:finite`] = Infinity;
          else if (point.time < 0 || point.time > context.duration) errors[`${keyOf(point)}:bounds`] = Math.max(-point.time, point.time - context.duration);
        }
        const previous = next.find(p => p.lineIndex === rows[i - 1] && p.role === "end");
        if (previous && first && previous.time > first.time) errors[`${rows[i]}:overlap`] = previous.time - first.time;
      }
      return errors;
    }
    function validate(next, previous) {
      const before = violations(previous), after = violations(next);
      // Existing invalid captions do not block an unrelated repair; a move must not add/worsen a violation.
      return Object.entries(after).every(([key, severity]) => key in before && severity <= before[key]);
    }
    function move(pointKey, time) {
      if (busy || !context || !finite(time)) return false;
      if (cleanupPending()) { error = "cleanup"; render(); return false; }
      if (stored[context.key] && !draft) { error = "sourceChanged"; render(); return false; }
      const current = points(), point = current.find(p => keyOf(p) === pointKey);
      if (!point || point.locked || hooks.conflicted?.(point.lineIndex, point.role)) { error = "pending"; render(); return false; }
      const original = context.points.find(p => keyOf(p) === pointKey);
      const changed = [pointKey];
      // Only a shared boundary moves together. Separate vocal ends/rests remain independent.
      const position = context.rows.indexOf(point.lineIndex);
      const adjacent = current.find(p => p.lineIndex === context.rows[position + (point.role === "end" ? 1 : -1)]
        && p.role !== point.role && p.time === point.time);
      if (adjacent) {
        if (adjacent.locked || hooks.conflicted?.(adjacent.lineIndex, adjacent.role)) { error = "pending"; render(); return false; }
        changed.push(keyOf(adjacent));
      }
      const next = current.map(p => changed.includes(keyOf(p)) ? { ...p, time: round(time) } : p);
      if (!validate(next, current)) { error = "order"; render(); return false; }
      const previousChanges = copy(draft?.changes || {});
      const changes = copy(previousChanges);
      for (const changedKey of changed) {
        const base = context.points.find(p => keyOf(p) === changedKey);
        const existing = changes[changedKey];
        // Capture CAS from the first edit, even if an Insert receipt arrives later.
        const before = existing ? existing.before : base.expectedTime;
        const baseTime = existing ? existing.baseTime : base.time;
        if (round(time) === round(baseTime)) delete changes[changedKey];
        else changes[changedKey] = { lineIndex: base.lineIndex, role: base.role, time: round(time),
          before, baseTime, lineText: base.lineText, source: base.source };
      }
      if (JSON.stringify(changes) === JSON.stringify(previousChanges)) return true;
      const nextDraft = { signature: context.signature, changes,
        history: [...(drag ? drag.historyBefore : draft?.history || []), drag ? drag.changesBefore : previousChanges].slice(-60) };
      const nextStored = { ...stored };
      if (Object.keys(changes).length) nextStored[context.key] = nextDraft;
      else delete nextStored[context.key];
      if (!write(nextStored)) { render(); return false; }
      draft = Object.keys(changes).length ? nextDraft : null;
      selected = keyOf(original); error = "";
      render(); hooks.preview?.();
      return true;
    }
    function undo() {
      if (busy || !draft?.history.length) return false;
      if (cleanupPending()) { error = "cleanup"; render(); return false; }
      const history = draft.history.slice(), changes = history.pop();
      const next = { ...stored };
      const nextDraft = { ...draft, changes, history };
      if (Object.keys(changes).length) next[context.key] = nextDraft;
      else delete next[context.key];
      if (!write(next)) { render(); return false; }
      draft = Object.keys(changes).length ? nextDraft : null;
      error = ""; render(); hooks.preview?.(); return true;
    }
    function cancel() {
      if (busy || !context) return false;
      if (cleanupPending()) { error = "cleanup"; render(); return false; }
      const next = { ...stored }; delete next[context.key];
      if (!write(next)) { render(); return false; }
      draft = null; error = ""; render(); hooks.preview?.(); return true;
    }
    async function save() {
      if (busy || !draft || !context) return false;
      const target = copy(context), sent = copy(draft.changes);
      if (Object.values(sent).some(p => hooks.conflicted?.(p.lineIndex, p.role))) { error = "pending"; render(); return false; }
      busy = true; error = ""; render();
      try {
        const acknowledgementKey = JSON.stringify([target.key, target.signature, sent]);
        const result = acknowledged.has(acknowledgementKey) ? { ok: true } : await hooks.save(target, Object.values(sent));
        if (result?.ok !== true) throw new Error(result?.error || labels().saveFailed);
        acknowledged.set(acknowledgementKey, JSON.stringify([target.key, target.signature]));
        // Only this captured song/language is cleared. A late acknowledgement cannot retarget another draft.
        const currentStored = stored[target.key];
        if (currentStored?.signature === target.signature && JSON.stringify(currentStored.changes) === JSON.stringify(sent)) {
          const next = { ...stored }; delete next[target.key];
          if (!write(next)) throw new Error(labels().cleanup || labels().storage);
          if (context?.key === target.key) draft = null;
          acknowledged.delete(acknowledgementKey);
        }
        return true;
      } catch (reason) {
        if (context?.key === target.key) error = reason.message || labels().saveFailed;
        return false;
      } finally { busy = false; render(); hooks.preview?.(); }
    }
    function activeAt(time) {
      if (!draft || !context) return undefined;
      let active = -1;
      const list = points();
      for (const index of context.rows) {
        const first = list.find(p => p.lineIndex === index && p.role === "start");
        if (first && time >= (first.changed ? first.time : first.playbackTime ?? first.time)) active = index;
      }
      const last = list.find(p => p.lineIndex === active && p.role === "end");
      const endTime = last?.changed ? last.time : last?.playbackTime ?? last?.time;
      return last && (last.changed || last.confirmedEnd || ["manual", "boundary", "acoustic", "rest"].includes(last.source)) && time >= endTime ? -1 : active;
    }
    function windowLimits() {
      const duration = Math.max(1, context?.duration || 10), width = Math.min(span, duration);
      return { start: clamp(start, 0, Math.max(0, duration - width)), width, duration };
    }
    function changeWindow(amount) { follow = false; start += amount * windowLimits().width; render(); }
    function zoom(value) { span = value === "all" ? Math.max(10, context?.duration || 10) : Number(value); follow = false; render(); }
    function clock(time) {
      if (!visible || !context) return;
      const bounds = windowLimits();
      const windowTime = clamp(time, 0, bounds.duration);
      if (follow && !drag && (windowTime < bounds.start || windowTime > bounds.start + bounds.width)) {
        const nextStart = clamp(Math.floor(windowTime / bounds.width) * bounds.width, 0, Math.max(0, bounds.duration - bounds.width));
        if (nextStart !== bounds.start) { start = nextStart; render(); }
      }
      const current = windowLimits(), cursor = hooks.root?.querySelector(".lyrics-timeline-playhead");
      if (cursor) { cursor.hidden = time < current.start || time > current.start + current.width;
        cursor.style.left = `${clamp((time - current.start) / current.width, 0, 1) * 100}%`; }
      const clockNode = hooks.root?.querySelector(".lyrics-timeline-clock");
      if (clockNode) clockNode.textContent = hooks.format(time);
    }
    function select(pointKey) { selected = pointKey; hooks.selected?.(points().find(p => keyOf(p) === pointKey)); render(); }
    function render() {
      const host = hooks.root;
      if (!host) return;
      host.hidden = !visible || !context;
      if (host.hidden) return;
      const focusKey = host.ownerDocument?.activeElement?.dataset?.timelinePoint;
      const l = labels(), bounds = windowLimits();
      host.replaceChildren();
      const make = (tag, className, content) => { const node = host.ownerDocument.createElement(tag); node.className = className || "";
        if (content != null) node.textContent = content; return node; };
      const button = (caption, action, title = caption) => { const node = make("button", "", caption); node.type = "button"; node.title = title;
        node.addEventListener("click", action); return node; };
      const controls = make("div", "lyrics-timeline-actions");
      const saveButton = button(l.save, () => void save()); saveButton.disabled = busy || !draft; controls.appendChild(saveButton);
      const undoButton = button(l.undo, undo); undoButton.disabled = busy || !draft?.history.length; controls.appendChild(undoButton);
      const cancelButton = button(l.cancel, cancel); cancelButton.disabled = busy || !stored[context.key]; controls.appendChild(cancelButton);
      controls.appendChild(button("‹", () => changeWindow(-1), l.previous));
      const zoomSelect = make("select", ""); zoomSelect.setAttribute("aria-label", l.zoom);
      for (const [value, caption] of [["5", "5s"], ["10", "10s"], ["20", "20s"], ["all", l.all]]) {
        const option = make("option", "", caption); option.value = value; zoomSelect.appendChild(option);
      }
      zoomSelect.value = [5, 10, 20].includes(span) ? String(span) : "all";
      zoomSelect.addEventListener("change", () => zoom(zoomSelect.value)); controls.appendChild(zoomSelect);
      controls.appendChild(button("›", () => changeWindow(1), l.nextWindow));
      const followButton = button(l.follow, () => { follow = true; clock(hooks.time()); render(); });
      followButton.setAttribute("aria-pressed", String(follow)); controls.appendChild(followButton);
      const status = make("span", "lyrics-timeline-status", busy ? l.saving : error ? (l[error] || error) : draft ? l.unsaved : l.legend);
      status.setAttribute("role", "status"); controls.appendChild(status); host.appendChild(controls);
      const rail = make("div", "lyrics-timeline-rail"); rail.setAttribute("aria-label", l.timeline);
      for (let i = 0; i <= 5; i += 1) { const scale = make("span", "lyrics-timeline-scale", hooks.format(bounds.start + bounds.width * i / 5));
        scale.style.left = `${i * 20}%`; rail.appendChild(scale); }
      const playhead = make("span", "lyrics-timeline-playhead"); rail.appendChild(playhead);
      const pointerTime = event => { const rect = rail.getBoundingClientRect();
        return round(bounds.start + (event.clientX - rect.left) / rect.width * bounds.width); };
      for (const point of points().filter(p => p.time >= bounds.start && p.time <= bounds.start + bounds.width)) {
        const dot = button("", () => select(keyOf(point)));
        dot.className = `lyrics-timeline-dot is-${point.role}${selected === keyOf(point) ? " is-selected" : ""}${point.changed ? " is-draft" : ""}`;
        dot.dataset.timelinePoint = keyOf(point); dot.style.left = `${(point.time - bounds.start) / bounds.width * 100}%`;
        dot.title = `${point.lineText} · ${point.role === "start" ? l.start : l.end} ${hooks.format(point.time)} · ${l[point.source] || point.source}`;
        dot.setAttribute("aria-label", dot.title); dot.setAttribute("role", "slider"); dot.setAttribute("aria-valuemin", "0");
        dot.setAttribute("aria-valuemax", String(context.duration)); dot.setAttribute("aria-valuenow", String(point.time));
        dot.disabled = busy || point.locked;
        dot.addEventListener("pointerdown", event => {
          if (event.button !== 0 || busy) return;
          event.preventDefault(); selected = keyOf(point); follow = false;
          drag = { key: selected, pointerId: event.pointerId, lastTime: point.time, rect: rail.getBoundingClientRect(), bounds,
            historyBefore: copy(draft?.history || []), changesBefore: copy(draft?.changes || {}) };
          hooks.selected?.(point);
          // Capture on the stable host; the dot DOM may be rerendered during preview.
          host.setPointerCapture?.(event.pointerId);
        });
        dot.addEventListener("keydown", event => {
          if (!["ArrowLeft", "ArrowRight"].includes(event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
          event.preventDefault(); selected = keyOf(point);
          move(selected, point.time + (event.key === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? .1 : .01));
        });
        rail.appendChild(dot);
      }
      rail.addEventListener("dblclick", event => { if (!event.target.closest?.(".lyrics-timeline-dot")) hooks.seek?.(clamp(pointerTime(event), 0, context.duration)); });
      host.appendChild(rail);
      const selection = points().find(p => keyOf(p) === selected);
      const detail = make("div", "lyrics-timeline-detail");
      const clockNode = make("time", "lyrics-timeline-clock", hooks.format(hooks.time())); detail.appendChild(clockNode);
      if (selection) detail.appendChild(make("span", "", `${selection.lineText} · ${selection.role === "start" ? l.start : l.end} ${hooks.format(selection.time)} · ${l[selection.source] || selection.source}`));
      else detail.appendChild(make("span", "", l.dragHint));
      host.appendChild(detail);
      clock(hooks.time());
      if (focusKey) host.querySelector(`[data-timeline-point="${focusKey}"]`)?.focus({ preventScroll: true });
    }
    hooks.root?.addEventListener("pointermove", event => {
      if (!drag || drag.pointerId !== event.pointerId) return;
      const time = round(drag.bounds.start + (event.clientX - drag.rect.left) / drag.rect.width * drag.bounds.width);
      if (time !== drag.lastTime && move(drag.key, time)) drag.lastTime = time;
    });
    const finishDrag = event => { if (drag?.pointerId === event.pointerId) { hooks.root?.releasePointerCapture?.(event.pointerId); drag = null; } };
    hooks.root?.addEventListener("pointerup", finishDrag); hooks.root?.addEventListener("pointercancel", finishDrag);
    return { setContext, move, undo, cancel, save, activeAt, clock, select, points,
      show(value = true) { visible = value; render(); }, render,
      hasDraft() { return Object.keys(stored).length > 0; }, canReload() { return !busy && !drag && !Object.keys(stored).length; },
      currentHasDraft() { return Boolean(draft); },
      conflicts(points) { return Boolean(draft && points.some(point => draft.changes[keyOf(point)])); },
      state() { return { visible, selected, start: windowLimits().start, span, follow, error, busy, draft: copy(draft), key: context?.key }; } };
  }
  root.ConsoleLyricsTimelineFactory = { createController };
})(typeof window === "object" ? window : globalThis);
