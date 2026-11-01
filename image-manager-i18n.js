"use strict";
(() => {
  const host = typeof window === "undefined" ? globalThis : window;
  const normalize = value => /^en(?:[-_]|$)/i.test(String(value || "").replace(/^"|"$/g, "")) ? "en" : "zh-CN";
  let initial = "zh-CN";
  try { initial = host.localStorage?.getItem("codexControl.language.v1") || initial; } catch (_) { /* Optional preference. */ }
  let language = normalize(initial);
  const bindings = new Map();
  const staticBindings = new WeakMap();
  const slots = element => {
    let values = bindings.get(element);
    if (!values) { values = new Map(); bindings.set(element, values); }
    return values;
  };
  const text = (zh, en) => String(language === "en" ? en ?? zh ?? "" : zh ?? en ?? "");
  const read = (element, attribute) => attribute ? element.getAttribute(attribute) : element.textContent;
  const write = (element, binding) => {
    const value = text(binding.zh, binding.en);
    if (binding.attribute) element.setAttribute(binding.attribute, value);
    else element.textContent = value;
    binding.last = value;
  };
  function bind(element, attribute, zh, en) {
    if (!element) return;
    const binding = { attribute, zh: String(zh ?? ""), en: String(en ?? zh ?? ""), last: null };
    slots(element).set(attribute || "text", binding);
    write(element, binding);
  }
  function setText(element, zh, en) { bind(element, "", zh, en); }
  function setAttribute(element, attribute, zh, en) {
    if (!["aria-label", "title", "placeholder"].includes(attribute)) return;
    bind(element, attribute, zh, en);
  }
  function applyStatic() {
    if (typeof document === "undefined") return;
    const firstStaticBinding = (element, key) => {
      let keys = staticBindings.get(element);
      if (!keys) { keys = new Set(); staticBindings.set(element, keys); }
      if (keys.has(key)) return false;
      keys.add(key);
      return true;
    };
    for (const element of document.querySelectorAll("[data-image-en]")) {
      if (firstStaticBinding(element, "text") && !slots(element).has("text")) bind(element, "", element.textContent, element.getAttribute("data-image-en"));
    }
    for (const attribute of ["aria-label", "title", "placeholder"]) {
      for (const element of document.querySelectorAll(`[data-image-en-${attribute}]`)) {
        if (firstStaticBinding(element, attribute) && !slots(element).has(attribute)) bind(element, attribute, element.getAttribute(attribute), element.getAttribute(`data-image-en-${attribute}`));
      }
    }
  }
  function setLanguage(value) {
    const next = normalize(value), changed = next !== language;
    language = next;
    if (typeof document !== "undefined") {
      document.documentElement.lang = language;
      document.documentElement.dataset.imageLanguage = language;
    }
    for (const [element, values] of bindings) {
      if (element.isConnected === false) { bindings.delete(element); continue; }
      for (const [key, binding] of values) {
        // A later direct write may be a real path, filename or user text. Only
        // refresh content that this binding still owns; explicit setText wins.
        if (read(element, binding.attribute) !== binding.last) { values.delete(key); continue; }
        write(element, binding);
      }
    }
    applyStatic();
    return changed;
  }
  host.ImageManagerI18n = Object.freeze({ text, setText, setAttribute, setLanguage, getLanguage: () => language, applyStatic });
  if (typeof document !== "undefined") {
    const initialize = () => { applyStatic(); setLanguage(language); };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true });
    else initialize();
  }
})();
