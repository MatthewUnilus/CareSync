import { useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { RiArrowDownSLine, RiLockLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Toaster } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, ApiError } from "./api";
import type { CurrentUser, Role } from "./api";
import { LogoMark } from "./brand";
import { cardClass, noticeClass } from "./design";

interface ShellProps {
  user: CurrentUser;
  onLogout: () => Promise<void>;
  onLock: () => Promise<void>;
  children: ReactNode;
}

interface Notice {
  kind: "success" | "error";
  text: string;
}

function roleLabel(role: Role): string {
  return role === "clinical" ? "Clinical" : "Administrator";
}

const summaryClass =
  "-mx-2 -mt-2 flex min-h-11 cursor-pointer select-none list-none items-center justify-between rounded-lg p-2 text-title-3-medium text-text-primary outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring [&::-webkit-details-marker]:hidden";

export default function Shell({
  user,
  onLogout,
  onLock,
  children,
}: ShellProps) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordNotice, setPasswordNotice] = useState<Notice | null>(null);
  const [changingPassword, setChangingPassword] = useState(false);

  async function handleChangePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordNotice(null);
    setChangingPassword(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setPasswordNotice({
        kind: "success",
        text: "Password changed. Use the new password next time you sign in.",
      });
    } catch (caught) {
      setPasswordNotice({
        kind: "error",
        text:
          caught instanceof ApiError
            ? caught.message
            : "Unable to reach the server.",
      });
    } finally {
      setChangingPassword(false);
    }
  }

  return (
    <div className="min-h-dvh bg-background-full text-text-primary">
      <Toaster />
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-separator-border bg-background-primary-default px-6 py-4">
        <div className="flex items-center gap-3">
          <LogoMark />
          <div>
            <p className="text-body-medium font-medium text-text-primary">
              CareSync
            </p>
            <p className="text-caption-1-regular text-text-secondary">
              Nursing workflow management
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <span className="text-body-medium text-text-primary">
            {user.display_name}
          </span>
          <span className="text-caption-1-regular text-text-secondary">
            {roleLabel(user.role)}
          </span>
          {/*
           * Explicit lock: hands the tablet over without waiting for the
           * inactivity timer. The session survives behind the lock, so the
           * next person cannot see these patients but the same person can
           * unlock with their password.
           */}
          <Button
            variant="secondary"
            className="min-h-11"
            leadingIcon={RiLockLine}
            onClick={onLock}
          >
            Lock
          </Button>
          <Button
            variant="secondary"
            className="min-h-11"
            onClick={onLogout}
          >
            Switch user
          </Button>
        </div>
      </header>

      <main
        className={cx(
          "mx-auto grid w-full gap-5 px-6 pt-8 pb-12",
          user.role === "administrator" ? "max-w-7xl" : "max-w-6xl",
        )}
      >
        {children}

        <details className={cx(cardClass, "group")}>
          <summary className={summaryClass}>
            Change password
            <RiArrowDownSLine className="size-5 text-text-tertiary transition-transform group-open:rotate-180" />
          </summary>
          <form
            onSubmit={handleChangePassword}
            className="flex flex-col gap-4 pt-2"
          >
            <Input
              label="Current password"
              type="password"
              autoComplete="current-password"
              isRequired
              value={currentPassword}
              onChange={setCurrentPassword}
            />
            <Input
              label="New password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              isRequired
              value={newPassword}
              onChange={setNewPassword}
            />
            <div>
              <Button type="submit" className="min-h-11" disabled={changingPassword}>
                {changingPassword ? "Changing…" : "Change password"}
              </Button>
            </div>
          </form>
          {passwordNotice ? (
            <p className={noticeClass[passwordNotice.kind]} role="status">
              {passwordNotice.text}
            </p>
          ) : null}
        </details>
      </main>
    </div>
  );
}
