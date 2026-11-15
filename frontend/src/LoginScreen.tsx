import { useState } from "react";
import type { FormEvent } from "react";

import { AuthCard } from "@/components/application/auth/auth-card";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";

import { api, ApiError } from "./api";
import type { CurrentUser } from "./api";
import { LogoMark } from "./brand";
import { isNativePlatform } from "./platform";
import { detectPlatform } from "./runtime";
import {
  defaultApiBaseUrl,
  normaliseApiBaseUrl,
  readApiBaseUrlOverride,
  saveApiBaseUrlOverride,
  clearApiBaseUrlOverride,
} from "./runtimeConfig";

interface LoginScreenProps {
  onLogin: (user: CurrentUser) => void;
}

const logo = <LogoMark />;

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const platform = detectPlatform();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [serverUrl, setServerUrl] = useState(
    () => readApiBaseUrlOverride() ?? "",
  );
  const [serverNotice, setServerNotice] = useState<string | null>(null);

  function handleSaveServer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!serverUrl.trim()) {
      clearApiBaseUrlOverride();
      setServerNotice(`Cleared. Using ${defaultApiBaseUrl(platform)}.`);
      return;
    }
    if (!normaliseApiBaseUrl(serverUrl)) {
      setServerNotice("Enter an http(s) address, e.g. http://localhost:8000.");
      return;
    }
    saveApiBaseUrlOverride(serverUrl);
    setServerNotice("Saved. The next request uses this address.");
  }

  async function handleSubmit(data: FormData) {
    if (pending) {
      return;
    }
    setError(null);
    setPending(true);
    try {
      const user = await api.login(
        String(data.get("email") ?? "").trim(),
        String(data.get("password") ?? ""),
      );
      onLogin(user);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to reach the server.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center bg-background-full p-6">
      <div className="flex w-full max-w-[400px] flex-col gap-4">
        {error ? (
          <p role="alert" className="text-body-medium text-text-error-primary">
            {error}
          </p>
        ) : null}

        <AuthCard
          mode="signin"
          providers={[]}
          showRememberMe={false}
          showForgotPassword={false}
          showSwitch={false}
          logo={logo}
          title="Sign in to TriageAssist"
          description="Clinical decision support"
          onSubmit={(data) => void handleSubmit(data)}
        />

        {isNativePlatform(platform) ? (
          <details className="rounded-3xl border border-border-button-default bg-background-primary-default p-6">
            <summary className="cursor-pointer rounded-md text-body-medium text-text-primary outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring">
              Server
            </summary>
            <form
              onSubmit={handleSaveServer}
              className="mt-4 flex flex-col gap-4"
            >
              <Input
                label="API base URL"
                type="url"
                inputMode="url"
                autoComplete="off"
                inputDir="ltr"
                placeholder={defaultApiBaseUrl(platform)}
                value={serverUrl}
                onChange={setServerUrl}
              />
              <p className="text-body-2-regular text-text-secondary">
                The installed app calls the API cross-origin. Leave this empty
                for {defaultApiBaseUrl(platform)}, or enter the address the
                device or emulator can reach.
              </p>
              <div>
                <Button
                  type="submit"
                  variant="secondary"
                  className="min-h-11"
                >
                  Save server
                </Button>
              </div>
              {serverNotice ? (
                <p
                  role="status"
                  className="text-body-2-regular text-text-secondary"
                >
                  {serverNotice}
                </p>
              ) : null}
            </form>
          </details>
        ) : null}
      </div>
    </main>
  );
}
