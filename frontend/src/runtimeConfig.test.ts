import assert from "node:assert/strict";
import test from "node:test";

import {
  defaultApiBaseUrl,
  normaliseApiBaseUrl,
  resolveApiBaseUrl,
} from "./runtimeConfig.ts";

test("the web build keeps relative API URLs", () => {
  assert.equal(defaultApiBaseUrl("web"), "");
  assert.equal(resolveApiBaseUrl({ platform: "web" }), "");
});

test("native builds default to the host loopback address", () => {
  assert.equal(defaultApiBaseUrl("android"), "http://localhost:8000");
  assert.equal(defaultApiBaseUrl("ios"), "http://localhost:8000");
  assert.equal(
    resolveApiBaseUrl({ platform: "android" }),
    "http://localhost:8000",
  );
});

test("a build-time URL applies to both client forms", () => {
  assert.equal(
    resolveApiBaseUrl({
      platform: "web",
      configured: "https://triage.example.org",
    }),
    "https://triage.example.org",
  );
  assert.equal(
    resolveApiBaseUrl({
      platform: "android",
      configured: "https://triage.example.org",
    }),
    "https://triage.example.org",
  );
});

test("a device override beats the build-time URL", () => {
  assert.equal(
    resolveApiBaseUrl({
      platform: "android",
      configured: "https://triage.example.org",
      override: "http://192.168.1.20:8000",
    }),
    "http://192.168.1.20:8000",
  );
});

test("an invalid override is ignored rather than breaking the client", () => {
  assert.equal(
    resolveApiBaseUrl({
      platform: "android",
      configured: "https://triage.example.org",
      override: "not a url",
    }),
    "https://triage.example.org",
  );
  assert.equal(
    resolveApiBaseUrl({ platform: "android", override: "ftp://host" }),
    "http://localhost:8000",
  );
});

test("normalisation trims whitespace and drops a trailing slash", () => {
  assert.equal(normaliseApiBaseUrl("  http://localhost:8000/  "), "http://localhost:8000");
  assert.equal(normaliseApiBaseUrl("https://Triage.Example.org"), "https://triage.example.org");
  assert.equal(normaliseApiBaseUrl("http://localhost:8000"), "http://localhost:8000");
});

test("normalisation rejects relative and non-http(s) values", () => {
  assert.equal(normaliseApiBaseUrl(""), null);
  assert.equal(normaliseApiBaseUrl("   "), null);
  assert.equal(normaliseApiBaseUrl("/api"), null);
  assert.equal(normaliseApiBaseUrl("localhost:8000"), null);
  assert.equal(normaliseApiBaseUrl("capacitor://localhost"), null);
  assert.equal(normaliseApiBaseUrl("ftp://localhost"), null);
});

test("normalisation rejects a base that already carries a path or query", () => {
  assert.equal(normaliseApiBaseUrl("http://localhost:8000/api"), null);
  assert.equal(normaliseApiBaseUrl("http://localhost:8000?x=1"), null);
  assert.equal(normaliseApiBaseUrl("http://user:pass@localhost:8000"), null);
});
