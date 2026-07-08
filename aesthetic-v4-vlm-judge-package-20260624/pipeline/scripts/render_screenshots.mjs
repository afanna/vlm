#!/usr/bin/env node
import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const VIEWPORTS = {
  desktop: { name: "desktop", width: 1440, height: 900, deviceScaleFactor: 1 },
  mobile: { name: "mobile", width: 390, height: 844, deviceScaleFactor: 2 },
};

const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);
const DIRECT_VIEWPORT_FIELDS = [
  "target_viewport",
  "target_surface",
  "canonical_viewport",
  "canonical_surface",
  "viewport_profile",
  "ui_type",
];
const QUERY_FIELDS = [
  "query",
  "query_text",
  "prompt",
  "instruction",
  "task",
  "description",
  "title",
  "layout",
  "task_group",
  "ui_type",
];
const MOBILE_STRONG_HINTS = [
  "手机h5",
  "移动端",
  "手机端",
  "小程序",
  "iphone",
  "android",
  "安卓",
  "ios",
  "手机应用",
  "移动应用",
  "底部导航",
  "tab bar",
  "tabbar",
  "竖屏",
  "灵动岛",
];
const MOBILE_WEAK_HINTS = ["mobile", "phone", "手机", "h5", "q_scene"];
const DESKTOP_STRONG_HINTS = [
  "官网",
  "网页",
  "网站",
  "web",
  "browser",
  "desktop",
  "pc端",
  "电脑端",
  "管理后台",
  "控制台",
  "dashboard",
  "仪表盘",
  "landing page",
];
const DESKTOP_WEAK_HINTS = ["pc", "电脑", "桌面"];
const DUAL_HINTS = [
  "手机和电脑",
  "电脑和手机",
  "手机与电脑",
  "电脑与手机",
  "pc和手机",
  "手机和pc",
  "pc端和手机端",
  "手机端和pc端",
  "移动端和桌面",
  "桌面和移动端",
  "web和移动端",
  "移动端和web",
  "同时适配",
  "兼容pc",
  "兼容电脑",
  "都好用",
  "响应式",
  "responsive",
  "mobile and desktop",
  "desktop and mobile",
];
const VIEWPORT_ALIASES = new Map(
  Object.entries({
    desktop: "desktop",
    web: "desktop",
    web_page: "desktop",
    browser: "desktop",
    pc: "desktop",
    computer: "desktop",
    "电脑": "desktop",
    "网页": "desktop",
    "官网": "desktop",
    mobile: "mobile",
    mobile_app: "mobile",
    phone: "mobile",
    iphone: "mobile",
    android: "mobile",
    ios: "mobile",
    app: "mobile",
    h5: "mobile",
    "手机": "mobile",
    "移动端": "mobile",
    image: "desktop",
    both: "all",
    dual: "all",
    all: "all",
  }),
);

function parseArgs(argv) {
  const args = {
    manifest: "runs/aesthetic_v1/manifest.jsonl",
    out: "runs/aesthetic_v1/screenshots",
    waitMs: 2000,
    timeoutMs: 30000,
    hardTimeoutMs: 90000,
    limit: 0,
    viewport: "auto",
    screenshotOnTimeout: false,
    captureScrollWidth: true,
    maxScreenshotCssWidth: 12000,
    fullPage: false,
    maxScreenshotCssHeight: 12000,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--manifest") {
      args.manifest = value;
      i += 1;
    } else if (key === "--out") {
      args.out = value;
      i += 1;
    } else if (key === "--wait-ms") {
      args.waitMs = Number(value);
      i += 1;
    } else if (key === "--timeout-ms") {
      args.timeoutMs = Number(value);
      i += 1;
    } else if (key === "--hard-timeout-ms") {
      args.hardTimeoutMs = Number(value);
      i += 1;
    } else if (key === "--limit") {
      args.limit = Number(value);
      i += 1;
    } else if (key === "--viewport") {
      args.viewport = value;
      i += 1;
    } else if (key === "--screenshot-on-timeout") {
      args.screenshotOnTimeout = true;
    } else if (key === "--capture-scroll-width") {
      args.captureScrollWidth = true;
    } else if (key === "--no-capture-scroll-width") {
      args.captureScrollWidth = false;
    } else if (key === "--max-screenshot-css-width") {
      args.maxScreenshotCssWidth = Number(value);
      i += 1;
    } else if (key === "--full-page") {
      args.fullPage = true;
    } else if (key === "--max-screenshot-css-height") {
      args.maxScreenshotCssHeight = Number(value);
      i += 1;
    } else {
      throw new Error(`unknown argument: ${key}`);
    }
  }
  return args;
}

function normalizeViewportValue(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const normalized = String(value).trim().toLowerCase().replace(/[-\s]+/g, "_");
  if (!normalized) {
    return null;
  }
  return VIEWPORT_ALIASES.get(normalized) ?? null;
}

function collectTextValues(record, keys) {
  const values = [];
  if (!record || typeof record !== "object") {
    return values;
  }
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      values.push(value.trim());
    }
  }
  return values;
}

async function readSidecarMetadata(inputPath) {
  if (typeof inputPath !== "string" || !inputPath) {
    return {};
  }
  const parsed = path.parse(inputPath);
  const candidates = [
    path.join(parsed.dir, `${parsed.name}.meta.json`),
    path.join(parsed.dir, "query_instruction.json"),
    path.join(parsed.dir, "metadata.json"),
  ];
  for (const candidate of candidates) {
    try {
      const text = await fs.readFile(candidate, "utf8");
      const payload = JSON.parse(text.replace(/^\uFEFF/, ""));
      if (payload && typeof payload === "object" && !Array.isArray(payload)) {
        return payload;
      }
    } catch {
      // Missing or malformed sidecar metadata should not block rendering.
    }
  }
  return {};
}

async function queryContextText(record) {
  const parts = [];
  parts.push(...collectTextValues(record, QUERY_FIELDS));
  parts.push(...collectTextValues(record, ["id", "sample_relpath", "input_path", "input_type"]));
  if (record.sample_metadata && typeof record.sample_metadata === "object") {
    parts.push(...collectTextValues(record.sample_metadata, QUERY_FIELDS));
  }
  const sidecar = await readSidecarMetadata(record.input_path);
  parts.push(...collectTextValues(sidecar, QUERY_FIELDS));
  return parts.join(" ").toLowerCase();
}

async function explicitViewportFromRecord(record) {
  for (const key of DIRECT_VIEWPORT_FIELDS) {
    const viewport = normalizeViewportValue(record[key]);
    if (viewport) {
      return { viewport, source: `record.${key}` };
    }
  }
  if (record.sample_metadata && typeof record.sample_metadata === "object") {
    for (const key of DIRECT_VIEWPORT_FIELDS) {
      const viewport = normalizeViewportValue(record.sample_metadata[key]);
      if (viewport) {
        return { viewport, source: `sample_metadata.${key}` };
      }
    }
  }
  const sidecar = await readSidecarMetadata(record.input_path);
  for (const key of DIRECT_VIEWPORT_FIELDS) {
    const viewport = normalizeViewportValue(sidecar[key]);
    if (viewport) {
      return { viewport, source: `sidecar.${key}` };
    }
  }
  return { viewport: null, source: null };
}

async function inferViewportName(record) {
  const explicit = await explicitViewportFromRecord(record);
  if (explicit.viewport && explicit.viewport !== "all") {
    return explicit.viewport;
  }

  const text = await queryContextText(record);
  const hasDual = DUAL_HINTS.some((token) => text.includes(token));
  const hasMobileStrong = MOBILE_STRONG_HINTS.some((token) => text.includes(token));
  const hasDesktopStrong =
    DESKTOP_STRONG_HINTS.some((token) => text.includes(token)) ||
    /\.(com|co\.uk|studio|care|design)\b/.test(text);
  const hasAppConcept = /\bapp\b/.test(text) || text.includes("应用");
  const hasMobile =
    hasMobileStrong ||
    MOBILE_WEAK_HINTS.some((token) => text.includes(token)) ||
    (hasAppConcept && !hasDesktopStrong);
  const hasDesktop = hasDesktopStrong || DESKTOP_WEAK_HINTS.some((token) => text.includes(token));

  if (explicit.viewport === "all") {
    if (hasMobile && !hasDesktop) {
      return "mobile";
    }
    return "desktop";
  }
  if (hasDual) {
    if (hasMobile && !hasDesktop) {
      return "mobile";
    }
    return "desktop";
  }
  if (hasMobile && !hasDesktop) {
    return "mobile";
  }
  if (hasDesktop && !hasMobile) {
    return "desktop";
  }
  if (hasMobileStrong) {
    return "mobile";
  }
  return "desktop";
}

async function chooseViewport(record, args) {
  const requested = args.viewport === "auto" ? await inferViewportName(record) : args.viewport;
  if (requested === "image") {
    return VIEWPORTS.desktop;
  }
  const viewport = VIEWPORTS[requested];
  if (!viewport) {
    throw new Error(`unsupported viewport: ${requested}`);
  }
  return viewport;
}

async function chooseViewports(record, args) {
  if (args.viewport === "both" || args.viewport === "all") {
    return [VIEWPORTS.desktop, VIEWPORTS.mobile];
  }
  return [await chooseViewport(record, args)];
}

async function readJsonl(filePath) {
  const text = await fs.readFile(filePath, "utf8");
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

async function sha256File(filePath) {
  const hash = createHash("sha256");
  await new Promise((resolve, reject) => {
    const stream = createReadStream(filePath);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("error", reject);
    stream.on("end", resolve);
  });
  return hash.digest("hex");
}

function sanitizeId(value) {
  return String(value).replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 140);
}

async function writeJson(filePath, payload) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, JSON.stringify(payload, null, 2), "utf8");
}

async function withHardTimeout(promise, timeoutMs, label) {
  let timer = null;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} exceeded ${timeoutMs}ms`)), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}

async function fileBytes(filePath) {
  const stat = await fs.stat(filePath);
  return stat.size;
}

function pngDimensions(buffer) {
  if (
    buffer.length >= 24 &&
    buffer[0] === 0x89 &&
    buffer[1] === 0x50 &&
    buffer[2] === 0x4e &&
    buffer[3] === 0x47
  ) {
    return {
      width: buffer.readUInt32BE(16),
      height: buffer.readUInt32BE(20),
    };
  }
  return null;
}

async function imageInfo(filePath) {
  const buffer = await fs.readFile(filePath);
  const dims = pngDimensions(buffer);
  return {
    bytes: buffer.length,
    sha256: createHash("sha256").update(buffer).digest("hex"),
    width: dims?.width ?? null,
    height: dims?.height ?? null,
  };
}

function summarizeRequests(requests) {
  const failed = requests.filter((entry) => entry.kind === "failed");
  const httpErrors = requests.filter((entry) => entry.kind === "http_error");
  const domains = {};
  for (const entry of requests) {
    try {
      const host = new URL(entry.url).host || "local";
      domains[host] = (domains[host] ?? 0) + 1;
    } catch {
      domains.local = (domains.local ?? 0) + 1;
    }
  }
  return {
    total_logged: requests.length,
    failed_count: failed.length,
    http_error_count: httpErrors.length,
    domains,
  };
}

async function captureViewport(browser, record, viewport, sampleOutDir, args) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: viewport.deviceScaleFactor,
    isMobile: viewport.name === "mobile",
    hasTouch: viewport.name === "mobile",
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();
  const requests = [];
  page.on("requestfailed", (request) => {
    requests.push({
      kind: "failed",
      url: request.url(),
      method: request.method(),
      resource_type: request.resourceType(),
      failure: request.failure()?.errorText ?? "unknown",
    });
  });
  page.on("response", (response) => {
    const status = response.status();
    if (status >= 400) {
      requests.push({
        kind: "http_error",
        url: response.url(),
        status,
        resource_type: response.request().resourceType(),
      });
    }
  });

  const screenshotPath = path.join(sampleOutDir, `${viewport.name}.png`);
  const requestLogPath = path.join(sampleOutDir, `${viewport.name}.requests.json`);
  const startedAt = new Date().toISOString();
  let status = "ok";
  let error = null;
  let pageMetrics = null;
  let navigationTimedOut = false;
  let navigationError = null;

  try {
    try {
      await page.goto(pathToFileURL(record.input_path).href, {
        waitUntil: "domcontentloaded",
        timeout: args.timeoutMs,
      });
    } catch (gotoError) {
      const message = String(gotoError?.stack || gotoError);
      if (!args.screenshotOnTimeout || !message.includes("Timeout")) {
        throw gotoError;
      }
      navigationTimedOut = true;
      navigationError = message;
    }
    await page.waitForTimeout(args.waitMs);
    pageMetrics = await page.evaluate(() => {
      const body = document.body;
      const rect = body ? body.getBoundingClientRect() : null;
      const doc = document.documentElement;
      return {
        title: document.title || null,
        body_text_length: body?.innerText?.trim().length ?? 0,
        element_count: document.querySelectorAll("*").length,
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        client_width: doc?.clientWidth ?? null,
        scroll_width: doc?.scrollWidth ?? null,
        body_scroll_width: body?.scrollWidth ?? null,
        scroll_height: doc?.scrollHeight ?? null,
        body_scroll_height: body?.scrollHeight ?? null,
        body_rect: rect
          ? { width: rect.width, height: rect.height, top: rect.top, left: rect.left }
          : null,
      };
    });
    const rawCaptureWidth = args.captureScrollWidth
      ? Math.max(
          viewport.width,
          Number(pageMetrics?.scroll_width) || 0,
          Number(pageMetrics?.body_scroll_width) || 0,
          Number(pageMetrics?.body_rect?.width) || 0,
        )
      : viewport.width;
    const captureWidth = Math.max(
      1,
      Math.min(Math.ceil(rawCaptureWidth), args.maxScreenshotCssWidth),
    );
    const rawCaptureHeight = args.fullPage
      ? Math.max(
          viewport.height,
          Number(pageMetrics?.scroll_height) || 0,
          Number(pageMetrics?.body_scroll_height) || 0,
          Number(pageMetrics?.body_rect?.height) || 0,
        )
      : viewport.height;
    const captureHeight = Math.max(
      1,
      Math.min(Math.ceil(rawCaptureHeight), args.maxScreenshotCssHeight),
    );
    pageMetrics.screenshot_clip = {
      x: 0,
      y: 0,
      width: captureWidth,
      height: captureHeight,
      raw_width: rawCaptureWidth,
      raw_height: rawCaptureHeight,
      clipped_width: rawCaptureWidth > captureWidth,
      clipped_height: rawCaptureHeight > captureHeight,
      capture_scroll_width: args.captureScrollWidth,
      full_page: args.fullPage,
      full_page_capture_strategy: args.fullPage ? "resize_viewport_then_clip" : null,
    };
    if (args.fullPage) {
      // Resize the viewport to the captured document height so fixed/sticky elements
      // render at the natural long-screenshot edge instead of being frozen mid-page.
      await page.setViewportSize({ width: viewport.width, height: captureHeight });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(100);
    }
    if (args.fullPage || (args.captureScrollWidth && captureWidth > viewport.width)) {
      await withHardTimeout(
        (async () => {
          const client = await context.newCDPSession(page);
          const result = await client.send("Page.captureScreenshot", {
            format: "png",
            captureBeyondViewport: true,
            fromSurface: true,
            clip: {
              x: 0,
              y: 0,
              width: captureWidth,
              height: captureHeight,
              scale: viewport.deviceScaleFactor,
            },
          });
          await fs.writeFile(screenshotPath, Buffer.from(result.data, "base64"));
          await client.detach();
        })(),
        args.hardTimeoutMs,
        "Page.captureScreenshot hard timeout",
      );
    } else {
      await withHardTimeout(
        page.screenshot({
          path: screenshotPath,
          fullPage: false,
          clip: { x: 0, y: 0, width: captureWidth, height: captureHeight },
          animations: "disabled",
        }),
        args.hardTimeoutMs,
        "page.screenshot hard timeout",
      );
    }
  } catch (captureError) {
    status = "failed";
    error = String(captureError?.stack || captureError);
  } finally {
    await writeJson(requestLogPath, {
      schema_version: 1,
      sample_id: record.id,
      viewport: viewport.name,
      started_at: startedAt,
      requests,
      summary: summarizeRequests(requests),
    });
    try {
      await withHardTimeout(context.close(), 10000, "browser context close hard timeout");
    } catch (closeError) {
      status = "failed";
      const closeMessage = String(closeError?.stack || closeError);
      error = error ? `${error}\n${closeMessage}` : closeMessage;
    }
  }

  if (status === "failed") {
    return {
      viewport: viewport.name,
      status,
      width: viewport.width,
      height: viewport.height,
      device_scale_factor: viewport.deviceScaleFactor,
      request_log_path: path.resolve(requestLogPath),
      request_summary: summarizeRequests(requests),
      error,
      page_metrics: pageMetrics,
    };
  }

  const info = await imageInfo(screenshotPath);
  return {
    viewport: viewport.name,
    status,
    width: viewport.width,
    height: viewport.height,
    device_scale_factor: viewport.deviceScaleFactor,
    screenshot_path: path.resolve(screenshotPath),
    screenshot_sha256: info.sha256,
    screenshot_bytes: info.bytes,
    screenshot_width: info.width,
    screenshot_height: info.height,
    request_log_path: path.resolve(requestLogPath),
    request_summary: summarizeRequests(requests),
    page_metrics: pageMetrics,
    navigation_timed_out: navigationTimedOut,
    navigation_error: navigationError,
  };
}

async function passthroughImage(record) {
  const info = await imageInfo(record.input_path);
  return {
    ...record,
    render_schema_version: 1,
    render_status: "ok",
    views: [
      {
        viewport: "image",
        status: "ok",
        screenshot_path: path.resolve(record.input_path),
        screenshot_sha256: info.sha256,
        screenshot_bytes: info.bytes,
        screenshot_width: info.width,
        screenshot_height: info.height,
      },
    ],
    render_errors: [],
  };
}

async function renderHtmlRecord(browser, record, args) {
  const sampleOutDir = path.join(args.out, sanitizeId(record.id));
  await fs.mkdir(sampleOutDir, { recursive: true });
  const renderErrors = [];
  const viewports = await chooseViewports(record, args);
  const views = [];
  for (const viewport of viewports) {
    const view = await captureViewport(browser, record, viewport, sampleOutDir, args);
    views.push(view);
    if (view.status !== "ok") {
      renderErrors.push({ viewport: viewport.name, error: view.error });
    }
  }
  return {
    ...record,
    render_schema_version: 1,
    render_status: renderErrors.length === 0 ? "ok" : "partial",
    views,
    render_errors: renderErrors,
  };
}

async function main() {
  const args = parseArgs(process.argv);
  await fs.mkdir(args.out, { recursive: true });
  const records = await readJsonl(args.manifest);
  const selected = args.limit > 0 ? records.slice(0, args.limit) : records;
  const outPath = path.join(args.out, "render_manifest.jsonl");
  await fs.rm(outPath, { force: true });
  const browser = await chromium.launch({
    headless: true,
    args: ["--allow-file-access-from-files"],
  });
  const rendered = [];
  try {
    for (const record of selected) {
      const ext = path.extname(record.input_path).toLowerCase();
      const outRecord =
        record.input_type === "image" || IMAGE_EXTENSIONS.has(ext)
          ? await passthroughImage(record)
          : await renderHtmlRecord(browser, record, args);
      rendered.push(outRecord);
      await fs.appendFile(outPath, `${JSON.stringify(outRecord)}\n`, "utf8");
      console.log(
        JSON.stringify({
            id: record.id,
            source: record.source,
            render_status: outRecord.render_status,
            viewport: outRecord.views?.map((view) => view.viewport).join(","),
          }),
      );
    }
  } finally {
    await browser.close();
  }

  const summary = {
    out: outPath,
    records: rendered.length,
    ok: rendered.filter((record) => record.render_status === "ok").length,
    partial: rendered.filter((record) => record.render_status === "partial").length,
    by_viewport: rendered.reduce((acc, record) => {
      const views = Array.isArray(record.views) && record.views.length > 0 ? record.views : [{ viewport: "none" }];
      for (const view of views) {
        const viewport = view.viewport || "none";
        acc[viewport] = (acc[viewport] || 0) + 1;
      }
      return acc;
    }, {}),
  };
  await writeJson(path.join(args.out, "render_summary.json"), summary);
  console.log(JSON.stringify(summary));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
