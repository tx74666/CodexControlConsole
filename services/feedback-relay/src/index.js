const MAX_DESCRIPTION_LENGTH = 4000;
const MIN_DESCRIPTION_LENGTH = 10;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_REQUEST_BYTES = 8 * 1024 * 1024;
const CATEGORIES = new Set(["bug", "layout", "music", "update", "other"]);
const REPORT_STATUSES = new Set(["new", "resolved"]);

function json(payload, status = 200, headers = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...headers
    }
  });
}

function error(message, status = 400, headers = {}, details = {}) {
  return json({ error: message, ...details }, status, headers);
}

function boundedInteger(value, fallback, minimum, maximum) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? Math.max(minimum, Math.min(maximum, parsed)) : fallback;
}

function base64Bytes(value) {
  const clean = String(value || "").trim();
  if (!clean || clean.length > Math.ceil(MAX_IMAGE_BYTES / 3) * 4 + 16) {
    throw new Error("Screenshot must be 5 MB or smaller.");
  }
  let binary;
  try {
    binary = atob(clean);
  } catch {
    throw new Error("Screenshot data is invalid.");
  }
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  if (bytes.byteLength > MAX_IMAGE_BYTES) throw new Error("Screenshot must be 5 MB or smaller.");
  return bytes;
}

export function detectImageType(bytes) {
  if (bytes.length >= 8
    && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47
    && bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a) {
    return "image/png";
  }
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return "image/jpeg";
  }
  if (bytes.length >= 12
    && String.fromCharCode(...bytes.slice(0, 4)) === "RIFF"
    && String.fromCharCode(...bytes.slice(8, 12)) === "WEBP") {
    return "image/webp";
  }
  return "";
}

function imageExtension(contentType) {
  return contentType === "image/png" ? "png" : contentType === "image/jpeg" ? "jpg" : "webp";
}

function cleanImageName(value, contentType) {
  const extension = `.${imageExtension(contentType)}`;
  const leaf = String(value || "screenshot").replaceAll("\\", "/").split("/").pop();
  const clean = leaf.replace(/[^A-Za-z0-9._ -]+/g, "_").replace(/^[ ._]+|[ ._]+$/g, "").slice(0, 96);
  if (!clean) return `screenshot${extension}`;
  return /\.(png|jpe?g|webp)$/i.test(clean) ? clean : clean + extension;
}

export function normalizeReportInput(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("Invalid report.");
  const category = String(payload.category || "bug").trim().toLowerCase();
  if (!CATEGORIES.has(category)) throw new Error("Feedback category is invalid.");
  const description = String(payload.description || "").trim();
  if (description.length < MIN_DESCRIPTION_LENGTH) throw new Error("Please describe the problem in at least 10 characters.");
  if (description.length > MAX_DESCRIPTION_LENGTH) throw new Error("Feedback description is too long.");
  const installationId = String(payload.installationId || "").trim();
  if (!/^[0-9a-fA-F-]{32,40}$/.test(installationId)) throw new Error("Installation ID is invalid.");

  let screenshot = null;
  if (payload.screenshot) {
    if (typeof payload.screenshot !== "object" || Array.isArray(payload.screenshot)) {
      throw new Error("Screenshot data is invalid.");
    }
    const bytes = base64Bytes(payload.screenshot.data);
    const contentType = detectImageType(bytes);
    if (!contentType) throw new Error("Screenshot must be PNG, JPEG, or WebP.");
    const claimedType = String(payload.screenshot.type || "").trim().toLowerCase();
    if (claimedType && claimedType !== contentType) throw new Error("Screenshot file type does not match its contents.");
    screenshot = {
      bytes,
      contentType,
      name: cleanImageName(payload.screenshot.name, contentType)
    };
  }

  return {
    category,
    description,
    installationId,
    screenshot,
    appVersion: String(payload.appVersion || "").slice(0, 40),
    osVersion: String(payload.osVersion || "").slice(0, 180),
    locale: String(payload.locale || "").slice(0, 24),
    module: String(payload.module || "").slice(0, 48),
    turnstileToken: String(payload.turnstileToken || "").slice(0, 4096)
  };
}

async function readJson(request) {
  const declared = Number.parseInt(request.headers.get("Content-Length") || "0", 10);
  if (declared > MAX_REQUEST_BYTES) throw new Error("Feedback request is too large.");
  const body = await request.text();
  if (new TextEncoder().encode(body).byteLength > MAX_REQUEST_BYTES) throw new Error("Feedback request is too large.");
  try {
    return JSON.parse(body);
  } catch {
    throw new Error("Invalid JSON body.");
  }
}

async function hmacHex(secret, value) {
  if (!secret) throw new Error("Server rate-limit secret is not configured.");
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(value));
  return Array.from(new Uint8Array(signature), byte => byte.toString(16).padStart(2, "0")).join("");
}

async function safeTokenMatch(actual, expected) {
  if (!actual || !expected) return false;
  const encoder = new TextEncoder();
  const [left, right] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(actual)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected))
  ]);
  const leftBytes = new Uint8Array(left);
  const rightBytes = new Uint8Array(right);
  let difference = 0;
  for (let index = 0; index < leftBytes.length; index += 1) difference |= leftBytes[index] ^ rightBytes[index];
  return difference === 0;
}

async function requireAdmin(request, env) {
  const authorization = request.headers.get("Authorization") || "";
  const token = authorization.startsWith("Bearer ") ? authorization.slice(7).trim() : "";
  return safeTokenMatch(token, String(env.ADMIN_TOKEN || ""));
}

async function verifyTurnstile(input, request, env) {
  if (String(env.ALLOW_UNVERIFIED_REPORTS || "").toLowerCase() === "true") return true;
  if (!env.TURNSTILE_SECRET_KEY || !input.turnstileToken) return false;
  const form = new FormData();
  form.set("secret", env.TURNSTILE_SECRET_KEY);
  form.set("response", input.turnstileToken);
  const remoteIp = request.headers.get("CF-Connecting-IP") || "";
  if (remoteIp) form.set("remoteip", remoteIp);
  const response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    body: form
  });
  if (!response.ok) return false;
  const result = await response.json();
  return result.success === true;
}

async function consumeDailyQuota(db, key, day, limit) {
  const row = await db.prepare(`
    INSERT INTO daily_limits (quota_key, day, count)
    VALUES (?, ?, 1)
    ON CONFLICT (quota_key, day) DO UPDATE SET count = daily_limits.count + 1
    WHERE daily_limits.count < ?
    RETURNING count
  `).bind(key, day, limit).first();
  return row ? Number(row.count || 0) : 0;
}

async function releaseDailyQuota(db, key, day) {
  await db.prepare(`
    UPDATE daily_limits
    SET count = MAX(0, count - 1)
    WHERE quota_key = ? AND day = ? AND count > 0
  `).bind(key, day).run();
}

function secondsUntilUtcMidnight(now = new Date()) {
  const midnight = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
  return Math.max(1, Math.ceil((midnight - now.getTime()) / 1000));
}

async function submitReport(request, env) {
  if (!env.DB || !env.IMAGES) return error("Feedback storage is not configured.", 503);
  let input;
  try {
    input = normalizeReportInput(await readJson(request));
  } catch (problem) {
    const message = String(problem?.message || "Invalid report.");
    return error(message, message.includes("too large") ? 413 : 400);
  }
  if (!await verifyTurnstile(input, request, env)) return error("Human verification failed. Please try again.", 403);

  const secret = String(env.RATE_LIMIT_SECRET || "");
  const remoteIp = request.headers.get("CF-Connecting-IP") || "unknown";
  let deviceHash;
  let ipHash;
  try {
    [deviceHash, ipHash] = await Promise.all([
      hmacHex(secret, `device:${input.installationId}`),
      hmacHex(secret, `ip:${remoteIp}`)
    ]);
  } catch {
    return error("Feedback rate limiting is not configured.", 503);
  }

  if (env.SUBMIT_RATE_LIMITER) {
    const burst = await env.SUBMIT_RATE_LIMITER.limit({ key: deviceHash });
    if (!burst.success) {
      return error(
        "Too many reports. Please wait a minute.",
        429,
        { "Retry-After": "60" },
        { code: "burst_limit", retryAfter: 60, limitReached: false }
      );
    }
  }

  const now = new Date();
  const day = now.toISOString().slice(0, 10);
  const deviceLimit = boundedInteger(env.DEVICE_DAILY_LIMIT, 10, 1, 100);
  const ipLimit = boundedInteger(env.IP_DAILY_LIMIT, 30, deviceLimit, 500);
  const deviceQuotaKey = `device:${deviceHash}`;
  const ipQuotaKey = `ip:${ipHash}`;
  const retryAfter = secondsUntilUtcMidnight(now);
  const dailyLimitDetails = { code: "daily_limit", retryAfter, limitReached: true };
  const deviceCount = await consumeDailyQuota(env.DB, deviceQuotaKey, day, deviceLimit);
  if (!deviceCount) {
    return error(
      "This device has reached its daily report limit.",
      429,
      { "Retry-After": String(retryAfter) },
      dailyLimitDetails
    );
  }
  const ipCount = await consumeDailyQuota(env.DB, ipQuotaKey, day, ipLimit);
  if (!ipCount) {
    await Promise.allSettled([releaseDailyQuota(env.DB, deviceQuotaKey, day)]);
    return error(
      "This network has reached its daily report limit.",
      429,
      { "Retry-After": String(retryAfter) },
      dailyLimitDetails
    );
  }

  const id = crypto.randomUUID();
  const createdAt = now.toISOString();
  let imageKey = "";
  try {
    if (input.screenshot) {
      imageKey = `reports/${id}/screenshot.${imageExtension(input.screenshot.contentType)}`;
      await env.IMAGES.put(imageKey, input.screenshot.bytes, {
        httpMetadata: { contentType: input.screenshot.contentType },
        customMetadata: { reportId: id }
      });
    }
    await env.DB.prepare(`
      INSERT INTO reports (
        id, category, description, image_key, image_type, image_name, status,
        app_version, os_version, locale, module, device_hash, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      id,
      input.category,
      input.description,
      imageKey || null,
      input.screenshot?.contentType || null,
      input.screenshot?.name || null,
      input.appVersion,
      input.osVersion,
      input.locale,
      input.module,
      deviceHash,
      createdAt,
      createdAt
    ).run();
  } catch (problem) {
    await Promise.allSettled([
      imageKey ? env.IMAGES.delete(imageKey) : Promise.resolve(),
      releaseDailyQuota(env.DB, deviceQuotaKey, day),
      releaseDailyQuota(env.DB, ipQuotaKey, day)
    ]);
    throw problem;
  }
  const remaining = Math.max(0, deviceLimit - deviceCount);
  return json({
    ok: true,
    id,
    remaining,
    dailyLimit: deviceLimit,
    retryAfter: remaining === 0 ? retryAfter : 0
  }, 201);
}

async function listReports(request, env) {
  if (!await requireAdmin(request, env)) return error("Unauthorized.", 401);
  const url = new URL(request.url);
  const status = url.searchParams.get("status") || "new";
  const limit = boundedInteger(url.searchParams.get("limit"), 50, 1, 100);
  const filter = status === "all" ? "" : REPORT_STATUSES.has(status) ? "WHERE status = ?" : "WHERE status = 'new'";
  const statement = env.DB.prepare(`
    SELECT id, category, description, status, app_version AS appVersion,
      os_version AS osVersion, locale, module, created_at AS createdAt,
      updated_at AS updatedAt, image_key IS NOT NULL AS hasImage,
      image_type AS imageType, image_name AS imageName
    FROM reports
    ${filter}
    ORDER BY created_at DESC
    LIMIT ?
  `);
  const result = status === "all"
    ? await statement.bind(limit).all()
    : await statement.bind(REPORT_STATUSES.has(status) ? status : "new", limit).all();
  const count = await env.DB.prepare("SELECT COUNT(*) AS count FROM reports WHERE status = 'new'").first();
  return json({ reports: result.results || [], newCount: Number(count?.count || 0) });
}

async function reportImage(request, env, id) {
  if (!await requireAdmin(request, env)) return error("Unauthorized.", 401);
  const row = await env.DB.prepare("SELECT image_key, image_type FROM reports WHERE id = ?").bind(id).first();
  if (!row?.image_key) return error("Screenshot was not found.", 404);
  const object = await env.IMAGES.get(row.image_key);
  if (!object) return error("Screenshot was not found.", 404);
  return new Response(object.body, {
    headers: {
      "Content-Type": row.image_type || object.httpMetadata?.contentType || "application/octet-stream",
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff"
    }
  });
}

async function updateReport(request, env, id) {
  if (!await requireAdmin(request, env)) return error("Unauthorized.", 401);
  let payload;
  try {
    payload = await readJson(request);
  } catch (problem) {
    return error(String(problem?.message || "Invalid request."), 400);
  }
  const status = String(payload.status || "").trim().toLowerCase();
  if (!REPORT_STATUSES.has(status)) return error("Report status is invalid.", 400);
  const result = await env.DB.prepare(
    "UPDATE reports SET status = ?, updated_at = ? WHERE id = ?"
  ).bind(status, new Date().toISOString(), id).run();
  if (!result.meta?.changes) return error("Report was not found.", 404);
  return json({ ok: true, id, status });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/v1/config") {
      return json({
        siteKey: String(env.TURNSTILE_SITE_KEY || ""),
        dailyLimit: boundedInteger(env.DEVICE_DAILY_LIMIT, 10, 1, 100),
        maxImageBytes: MAX_IMAGE_BYTES
      });
    }
    if (request.method === "POST" && url.pathname === "/v1/reports") {
      try {
        return await submitReport(request, env);
      } catch {
        return error("Feedback could not be saved. Please try again.", 500);
      }
    }
    if (request.method === "GET" && url.pathname === "/v1/admin/reports") {
      return listReports(request, env);
    }
    const imageMatch = url.pathname.match(/^\/v1\/admin\/reports\/([0-9a-fA-F-]{16,64})\/image$/);
    if (request.method === "GET" && imageMatch) return reportImage(request, env, imageMatch[1]);
    const reportMatch = url.pathname.match(/^\/v1\/admin\/reports\/([0-9a-fA-F-]{16,64})$/);
    if (request.method === "PATCH" && reportMatch) return updateReport(request, env, reportMatch[1]);
    return error("Not found.", 404);
  }
};
