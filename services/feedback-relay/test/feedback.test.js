import assert from "node:assert/strict";
import test from "node:test";

import { detectImageType, normalizeReportInput } from "../src/index.js";


const installationId = "123e4567-e89b-12d3-a456-426614174000";

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
