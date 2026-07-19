import assert from "node:assert/strict";
import test from "node:test";

import worker, { detectImageType, normalizeReportInput } from "../src/index.js";


const installationId = "123e4567-e89b-12d3-a456-426614174000";

class FakeStatement {
  constructor(database, sql) {
    this.database = database;
    this.sql = sql.replace(/\s+/g, " ").trim();
    this.args = [];
  }

  bind(...args) {
    this.args = args;
    return this;
  }

  async first() {
    if (!this.sql.startsWith("INSERT INTO daily_limits")) throw new Error(`Unexpected first(): ${this.sql}`);
    const [quotaKey, day, limit] = this.args;
    const key = `${quotaKey}|${day}`;
    const count = Number(this.database.limits.get(key) || 0);
    if (count >= Number(limit)) return null;
    this.database.limits.set(key, count + 1);
    return { count: count + 1 };
  }

  async run() {
    if (this.sql.startsWith("UPDATE daily_limits")) {
      const [quotaKey, day] = this.args;
      const key = `${quotaKey}|${day}`;
      const count = Number(this.database.limits.get(key) || 0);
      this.database.limits.set(key, Math.max(0, count - 1));
      return { meta: { changes: count > 0 ? 1 : 0 } };
    }
    if (this.sql.startsWith("INSERT INTO reports")) {
      if (this.database.failReports) throw new Error("Report storage failed");
      this.database.reports.push(this.args);
      return { meta: { changes: 1 } };
    }
    throw new Error(`Unexpected run(): ${this.sql}`);
  }
}

class FakeDatabase {
  constructor({ failReports = false } = {}) {
    this.failReports = failReports;
    this.limits = new Map();
    this.reports = [];
  }

  prepare(sql) {
    return new FakeStatement(this, sql);
  }
}

class FakeImages {
  async put() {}
  async delete() {}
}

function feedbackEnvironment(database, extra = {}) {
  return {
    DB: database,
    IMAGES: new FakeImages(),
    RATE_LIMIT_SECRET: "test-rate-limit-secret",
    ALLOW_UNVERIFIED_REPORTS: "true",
    DEVICE_DAILY_LIMIT: "10",
    IP_DAILY_LIMIT: "30",
    ...extra
  };
}

function reportRequest(id, ip = "192.0.2.10", description = "A valid feedback report for testing.") {
  return new Request("https://feedback.example/v1/reports", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "CF-Connecting-IP": ip
    },
    body: JSON.stringify({ category: "bug", description, installationId: id })
  });
}

test("normalizes a text-only report", () => {
  const report = normalizeReportInput({
    category: "layout",
    description: "The tabs overlap after startup.",
    installationId
  });
  assert.equal(report.category, "layout");
  assert.equal(report.screenshot, null);
});

test("validates image bytes instead of trusting the filename", () => {
  const png = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);
  assert.equal(detectImageType(png), "image/png");
  const report = normalizeReportInput({
    category: "bug",
    description: "A screenshot is attached to this report.",
    installationId,
    screenshot: {
      data: Buffer.from(png).toString("base64"),
      type: "image/png",
      name: "capture.exe"
    }
  });
  assert.equal(report.screenshot.contentType, "image/png");
  assert.equal(report.screenshot.name, "capture.exe.png");
});

test("rejects unknown categories and mismatched image types", () => {
  assert.throws(() => normalizeReportInput({
    category: "spam",
    description: "This category should not be accepted.",
    installationId
  }), /category/i);

  const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  assert.throws(() => normalizeReportInput({
    category: "bug",
    description: "The image type does not match the bytes.",
    installationId,
    screenshot: { data: png.toString("base64"), type: "image/jpeg" }
  }), /does not match/i);
});

test("marks burst limiting as temporary", async () => {
  const database = new FakeDatabase();
  const response = await worker.fetch(reportRequest(installationId), feedbackEnvironment(database, {
    SUBMIT_RATE_LIMITER: { limit: async () => ({ success: false }) }
  }));
  const payload = await response.json();
  assert.equal(response.status, 429);
  assert.equal(payload.code, "burst_limit");
  assert.equal(payload.limitReached, false);
  assert.equal(payload.retryAfter, 60);
  assert.equal(database.limits.size, 0);
});

test("refunds device quota when the network quota rejects a report", async () => {
  const database = new FakeDatabase();
  const environment = feedbackEnvironment(database, {
    DEVICE_DAILY_LIMIT: "1",
    IP_DAILY_LIMIT: "1"
  });
  const secondInstallation = "223e4567-e89b-12d3-a456-426614174001";

  const first = await worker.fetch(reportRequest(installationId), environment);
  assert.equal(first.status, 201);

  const blocked = await worker.fetch(reportRequest(secondInstallation), environment);
  const blockedPayload = await blocked.json();
  assert.equal(blocked.status, 429);
  assert.equal(blockedPayload.code, "daily_limit");
  assert.equal(blockedPayload.limitReached, true);

  const retried = await worker.fetch(reportRequest(secondInstallation, "192.0.2.11"), environment);
  assert.equal(retried.status, 201, "the rejected report consumed its device quota");
  assert.equal(database.reports.length, 2);
});

test("refunds both quotas when report storage fails", async () => {
  const database = new FakeDatabase({ failReports: true });
  const response = await worker.fetch(reportRequest(installationId), feedbackEnvironment(database));
  assert.equal(response.status, 500);
  assert.ok([...database.limits.values()].every(count => count === 0), "failed storage consumed daily quota");
});
