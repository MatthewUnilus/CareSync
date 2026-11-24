import assert from "node:assert/strict";
import test from "node:test";

import {
  defaultClinicalView,
  isNativePlatform,
  readPlatform,
} from "./platform.ts";

test("Capacitor's android platform is native", () => {
  assert.equal(readPlatform("android"), "android");
  assert.equal(isNativePlatform(readPlatform("android")), true);
});

test("Capacitor's ios platform is native", () => {
  assert.equal(readPlatform("ios"), "ios");
  assert.equal(isNativePlatform(readPlatform("ios")), true);
});

test("the web platform stays the web build", () => {
  assert.equal(readPlatform("web"), "web");
  assert.equal(isNativePlatform(readPlatform("web")), false);
});

test("an unknown platform falls back to the web build", () => {
  assert.equal(readPlatform("electron"), "web");
  assert.equal(readPlatform(""), "web");
});

test("the workspace opens on today's ward on every platform", () => {
  assert.equal(defaultClinicalView("android"), "board");
  assert.equal(defaultClinicalView("ios"), "board");
  assert.equal(defaultClinicalView("web"), "board");
});
