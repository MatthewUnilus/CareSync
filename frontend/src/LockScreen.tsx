import { useState } from "react";
import type { FormEvent } from "react";

import { RiLockLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { LinkButton } from "@/components/base/buttons/link-button";
import { Input } from "@/components/base/input/input";

import { api, ApiError } from "./api";
import type { CurrentUser } from "./api";
import { LogoMark } from "./brand";
import { cardClass } from "./design";

interface LockScreenProps {
  /** The password check succeeded: resume the session and the workspace. */
  onUnlock: (user: CurrentUser) => void;
  /** Hand over to a different person: sign out and return to the sign-in screen. */
  onSwitchUser: () => Promise<void>;
}

/**
 * The lock, shown when a session is locked by inactivity or by the explicit
 * Lock action. Nothing of the workspace is rendered while this is up: the
 * patient record is hidden, but the session row still exists behind it, so
 * unlocking is the same credential check the server performs on every request.
 *
 * The button labels say "unlock", not "sign in", because the session is still
 * there. "Switch user" is the escape hatch for handing the tablet to someone
 * else deliberately.
 */
export default function LockScreen({ onUnlock, onSwitchUser }: LockScreenProps) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    setError(null);
    setPending(true);
    try {
      const user = await api.unlock(password);
      setPassword("");
      onUnlock(user);
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
        <div className={cardClass}>
          <div className="flex items-center gap-3">
            <LogoMark />
            <div>
              <h1 className="text-title-3-medium text-text-primary">
                Session locked
              </h1>
              <p className="text-body-2-regular text-text-secondary">
                Patient data is hidden until you unlock.
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
              label="Password"
              type="password"
              autoComplete="current-password"
              isRequired
              value={password}
              onChange={setPassword}
            />
            {error ? (
              <p
                role="alert"
                className="text-body-2-regular text-text-error-primary"
              >
                {error}
              </p>
            ) : null}
            <div>
              <Button
                type="submit"
                className="min-h-11"
                leadingIcon={RiLockLine}
                disabled={pending}
              >
                {pending ? "Unlocking…" : "Unlock"}
              </Button>
            </div>
          </form>
        </div>

        <LinkButton
          type="button"
          onClick={() => void onSwitchUser()}
          className="self-center"
        >
          Switch user
        </LinkButton>
      </div>
    </main>
  );
}
