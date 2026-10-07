/* Editable Dev Room text stays separate from its source and section markers. */
(function (global, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (global) global.CodexDevRoomEditor = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const marker = "<!-- rr-dev-room:";
  const maxMarkdownBytes = 2 * 1024 * 1024;
  const maxBodyBytes = 512 * 1024;
  const maxSections = 128;

  function fail(message) { throw new Error(message); }
  function object(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
  function keys(value, allowed, required = allowed) {
    if (!object(value) || Object.keys(value).some(key => !allowed.includes(key)) || required.some(key => !Object.hasOwn(value, key))) {
      fail("Dev Room text fields are invalid.");
    }
  }
  function text(value, maximum, heading = false, reserved = true) {
    if (typeof value !== "string") fail("Dev Room text must be a string.");
    let bytes = 0, characters = 0;
    for (let index = 0; index < value.length; index++) {
      const code = value.charCodeAt(index);
      if ((code < 32 && code !== 9 && code !== 10 && code !== 13) || code === 127) fail("Dev Room text contains an invalid control character.");
      if (code >= 0xd800 && code <= 0xdbff) {
        const next = value.charCodeAt(++index);
        if (!(next >= 0xdc00 && next <= 0xdfff)) fail("Dev Room text contains invalid Unicode.");
        bytes += 4;
      } else {
        if (code >= 0xdc00 && code <= 0xdfff) fail("Dev Room text contains invalid Unicode.");
        bytes += code < 0x80 ? 1 : code < 0x800 ? 2 : 3;
      }
      characters++;
    }
    if (bytes > maximum) fail("Dev Room text exceeds its size limit.");
    if (heading && (characters > 200 || /[\r\n\t]/.test(value))) fail("Dev Room headings must be a single line of at most 200 characters.");
    if (reserved && value.includes(marker)) fail("Dev Room text cannot contain reserved source or section markers.");
    return value;
  }
  function escape(value) { return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function identity(value) {
    keys(value, ["id", "guid"]);
    if (typeof value.id !== "string" || value.id.match(/^[a-z][a-z0-9-]{0,127}/)?.[0] !== value.id ||
        typeof value.guid !== "string" || value.guid.match(/^[0-9a-f]{32}/)?.[0] !== value.guid) fail("Dev Room source identity is invalid.");
  }

  function decode(markdown) {
    text(markdown, maxMarkdownBytes, false, false);
    const header = markdown.match(/^<!-- rr-dev-room:v1 ([^\r\n]+) -->(\r?\n)/);
    if (!header) fail("Dev Room source header is missing or invalid.");
    let source;
    try { source = JSON.parse(header[1]); } catch { fail("Dev Room source identity is invalid."); }
    identity(source);
    const newline = header[2], endline = escape(newline);
    let remainder = markdown.slice(header[0].length);
    const prefix = remainder.match(new RegExp("^# ([^\\r\\n]*)" + endline + endline +
      escape(marker + "summary -->") + endline + "([\\s\\S]*?)" + endline +
      escape(marker + "summary-end -->") + endline + endline));
    if (!prefix) fail("Dev Room title or summary markers are invalid.");
    const title = text(prefix[1], maxBodyBytes, true);
    const summary = text(prefix[2], 64 * 1024);
    remainder = remainder.slice(prefix[0].length);
    const sections = [];
    while (remainder.length) {
      const index = sections.length;
      if (index >= maxSections) fail("Dev Room has too many sections.");
      const section = remainder.match(new RegExp("^" + escape(marker + "section " + index + " -->") + endline +
        "## ([^\\r\\n]*)" + endline + "([\\s\\S]*?)" + endline +
        escape(marker + "section-end " + index + " -->") + endline + endline));
      if (!section) fail("Dev Room section count, order or markers are invalid.");
      sections.push({ index, title: text(section[1], maxBodyBytes, true), body: text(section[2], maxBodyBytes) });
      remainder = remainder.slice(section[0].length);
    }
    if (!sections.length) fail("Dev Room must retain its original sections.");
    return { header: header[0], title, summary, sections, source: Object.freeze({ ...source, newline }) };
  }

  function parse(markdown) {
    const { title, summary, sections, source } = decode(markdown);
    return { title, summary, sections, source };
  }

  function serialize(originalMarkdown, editedTextModel) {
    const original = decode(originalMarkdown);
    keys(editedTextModel, ["title", "summary", "sections", "source"], ["title", "summary", "sections"]);
    if (Object.hasOwn(editedTextModel, "source")) {
      keys(editedTextModel.source, ["id", "guid", "newline"]);
      if (Object.keys(original.source).some(key => editedTextModel.source[key] !== original.source[key])) {
        fail("Dev Room source identity and newline cannot change.");
      }
    }
    if (!Array.isArray(editedTextModel.sections) || editedTextModel.sections.length !== original.sections.length) {
      fail("Dev Room section count cannot change.");
    }
    const title = text(editedTextModel.title, maxBodyBytes, true);
    const summary = text(editedTextModel.summary, 64 * 1024);
    const newline = original.source.newline;
    let result = original.header + "# " + title + newline + newline;
    result += marker + "summary -->" + newline + summary + newline + marker + "summary-end -->" + newline + newline;
    for (let index = 0; index < editedTextModel.sections.length; index++) {
      const section = editedTextModel.sections[index];
      keys(section, ["index", "title", "body"]);
      if (!Number.isInteger(section.index) || section.index !== index) fail("Dev Room section order cannot change.");
      result += marker + "section " + index + " -->" + newline + "## " + text(section.title, maxBodyBytes, true) + newline +
        text(section.body, maxBodyBytes) + newline + marker + "section-end " + index + " -->" + newline + newline;
    }
    text(result, maxMarkdownBytes, false, false);
    return result;
  }

  // Presentation is a read-only projection. The canonical source is never
  // rewritten, and these helpers never create HTML, URLs, or network requests.
  const technicalTitles = /^(?:references?|sources?|agent\s*资料|参考资料|来源|代理资料)$/i;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  function technicalTitle(value) { return technicalTitles.test(value.trim().replace(/[:：]\s*$/, "")); }
  function readingLines(value) { return value.replace(/\r\n?/g, "\n").split("\n"); }

  function fenceFlags(lines) {
    let fence = null;
    return lines.map(line => {
      if (fence) {
        const close = line.match(/^ {0,3}(`+|~+)\s*$/);
        if (close && close[1][0] === fence.character && close[1].length >= fence.length) fence = null;
        return true;
      }
      const open = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
      if (open && !(open[1][0] === "`" && open[2].includes("`"))) {
        fence = { character: open[1][0], length: open[1].length };
        return true;
      }
      return /^(?: {4}|\t)/.test(line);
    });
  }

  function inlineCodeEnd(line, offset) {
    const opening = line.slice(offset).match(/^`+/)?.[0];
    if (!opening) return -1;
    let next = offset + opening.length;
    while (next < line.length) {
      const position = line.indexOf("`", next);
      if (position < 0) return -1;
      const closing = line.slice(position).match(/^`+/)[0];
      if (closing.length === opening.length) return position + closing.length;
      next = position + closing.length;
    }
    return -1;
  }

  function hideReadingComments(value) {
    const lines = readingLines(value), flags = fenceFlags(lines);
    const nextClosing = new Array(lines.length + 1).fill(-1);
    for (let index = lines.length - 1; index >= 0; index--) {
      nextClosing[index] = lines[index].includes("-->") ? index : nextClosing[index + 1];
    }
    let inComment = false, machineHeader = false;
    return lines.map((line, index) => {
      // A malformed multiline source header can contain Id/GUID JSON on its
      // own lines. Suppress only those metadata lines, stopping at human prose.
      if (machineHeader) {
        if (/^\s*(?:[{},]|"(?:id|guid)"\s*:)/.test(line) || /^\s*-->\s*$/.test(line)) {
          if (line.includes("-->")) machineHeader = false;
          return "";
        }
        machineHeader = false;
      }
      if (!inComment && flags[index]) return line;
      if (!inComment && /^ {0,3}<!--\s*rr-dev-room:/.test(line)) {
        machineHeader = /^ {0,3}<!--\s*rr-dev-room:v\d+\s+\{/.test(line) && !line.includes("-->");
        return "";
      }
      let result = "", offset = 0;
      while (offset < line.length) {
        if (inComment) {
          const end = line.indexOf("-->", offset);
          if (end < 0) break;
          offset = end + 3; inComment = false; continue;
        }
        if (line[offset] === "\\" && offset + 1 < line.length) {
          result += line.slice(offset, offset + 2); offset += 2; continue;
        }
        if (line[offset] === "`") {
          const end = inlineCodeEnd(line, offset);
          if (end >= 0) { result += line.slice(offset, end); offset = end; continue; }
        }
        if (line.startsWith("<!--", offset)) {
          const end = line.indexOf("-->", offset + 4);
          if (end >= 0) { offset = end + 3; continue; }
          if (/^<!--\s*rr-dev-room:/.test(line.slice(offset))) break;
          if (nextClosing[index + 1] >= 0) { inComment = true; break; }
        }
        result += line[offset++];
      }
      return result;
    }).join("\n");
  }

  function splitTechnical(value, initialTitle = null) {
    const lines = readingLines(value), flags = fenceFlags(lines), human = [], technical = [];
    let active = initialTitle ? { title: initialTitle, lines: [], label: false } : null;
    const flush = () => {
      if (active) technical.push({ index: null, title: active.title, body: active.lines.join("\n") });
      active = null;
    };
    for (let index = 0; index < lines.length; index++) {
      const line = lines[index];
      if (flags[index]) { (active ? active.lines : human).push(line); continue; }
      const heading = line.match(/^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$/);
      if (heading) heading[2] = heading[2].replace(/[ \t]+#+[ \t]*$/, "");
      const label = line.match(/^ {0,3}(References?|Sources?|Agent\s*资料|参考资料|来源|代理资料)\s*[:：]\s*(.*)$/i);
      if (heading && technicalTitle(heading[2]) || label) {
        flush();
        active = { title: heading ? heading[2] : label[1], lines: label && label[2] ? [label[2]] : [], label: Boolean(label) };
      } else if (heading || /^ {0,3}(?:Risks?|风险)\s*[:：]/i.test(line) || active?.label && !line.trim()) {
        flush(); human.push(line);
      } else (active ? active.lines : human).push(line);
    }
    flush();
    return { body: human.join("\n"), technical };
  }

  function present(markdown) {
    text(markdown, maxMarkdownBytes, false, false);
    let model;
    try { model = parse(markdown); } catch { model = null; }
    if (!model) {
      const split = splitTechnical(hideReadingComments(markdown));
      const title = split.body.match(/^\s*# ([^\r\n]+)(?:\n|$)/)?.[1] || null;
      return { body: split.body, title, source: null, canonical: false, technical: split.technical };
    }
    const parts = ["# " + model.title, "", hideReadingComments(model.summary), ""], technical = [];
    for (const section of model.sections) {
      const isTechnical = technicalTitle(section.title);
      const split = splitTechnical(hideReadingComments(section.body), isTechnical ? section.title : null);
      // A mixed References section with a human Risks subsection must remain
      // visible/editable. Only a whole technical section has its canonical index.
      if (!isTechnical || split.body.trim()) parts.push(...(!isTechnical ? ["## " + section.title] : []), split.body, "");
      for (const item of split.technical) {
        const wholeSection = isTechnical && !split.body.trim() && split.technical.length === 1;
        technical.push({ ...item, index: wholeSection ? section.index : null });
      }
    }
    return { body: parts.join("\n"), title: model.title, source: model.source, canonical: true, technical };
  }

  function catalog(markdown, allowedIds) {
    text(markdown, maxMarkdownBytes, false, false);
    let allowed = null;
    if (allowedIds !== undefined) {
      if (!(allowedIds instanceof Set) && !Array.isArray(allowedIds)) fail("Dev Room catalog identities are invalid.");
      allowed = new Set(allowedIds);
    }
    const lines = readingLines(hideReadingComments(markdown)), flags = fenceFlags(lines), result = [], seen = new Set();
    let group = null;
    for (let index = 0; index < lines.length; index++) {
      if (flags[index]) continue;
      const heading = lines[index].match(/^ {0,3}##[ \t]+([^\r\n]+?)[ \t]*$/);
      if (heading) {
        try { group = text(heading[1].replace(/[ \t]+#+[ \t]*$/, ""), maxBodyBytes, true); } catch { group = null; }
        continue;
      }
      if (!group) continue;
      const link = lines[index].match(/^ {0,3}[-*+]\s+\[(?:\\.|[^\]\\])*\]\(([0-9a-f-]+)\.md\)\s*$/);
      const id = link?.[1];
      if (!id || !uuid.test(id) || seen.has(id) || allowed && !allowed.has(id)) continue;
      seen.add(id); result.push({ id, group });
    }
    return result;
  }

  return Object.freeze({ parse, serialize, present, catalog });
});
