import { useCallback, useEffect, useState } from "react";
import type { Role } from "./api";

export function homePathForRole(role: Role): string {
  return `/${role}`;
}

/**
 * Minimal path routing for the single client. Each Role has its own landing
 * route; the API guards every surface's data, so the path is a convenience
 * rather than the security boundary.
 */
export function usePathname(): [string, (path: string) => void] {
  const [pathname, setPathname] = useState(() => window.location.pathname);

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const replace = useCallback((path: string) => {
    if (window.location.pathname === path) {
      return;
    }
    window.history.replaceState(null, "", path);
    setPathname(path);
  }, []);

  return [pathname, replace];
}
