export type Role = "clinical" | "administrator";

export interface CurrentUser {
  id: number;
  email: string;
  display_name: string;
  role: Role;
}

export interface AccessResponse {
  role: Role;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail);
  }

  return body as T;
}

export const api = {
  me: () => request<CurrentUser>("/api/auth/me"),
  login: (email: string, password: string) =>
    request<CurrentUser>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),
  access: (scope: Role) =>
    request<AccessResponse>(`/api/${scope}/access`),
};
