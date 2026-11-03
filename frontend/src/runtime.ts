import { Capacitor } from "@capacitor/core";

import type { ClientPlatform } from "./platform";
import { readPlatform } from "./platform";

export function detectPlatform(): ClientPlatform {
  return readPlatform(Capacitor.getPlatform());
}
