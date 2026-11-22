"use client";

import { useEffect, useState, type ReactNode } from "react";
import { RiInformationFill } from "@remixicon/react";
import { cx, sortCx } from "@/utils/cx";

/**
 * Touch-visible information display.
 *
 * On desktop: shows the full detail inline with an info icon.
 * On mobile: shows the summary with a tap-to-expand toggle for the detail.
 *
 * This replaces `title` tooltips which don't work on touch devices.
 */
export interface TappableInfoProps {
  /** Brief text always visible (e.g., "Override", "Differs: High → Low") */
  summary: ReactNode;
  /** Full explanation shown on desktop or when expanded on mobile */
  detail: ReactNode;
  /** Optional custom class for the summary container */
  className?: string;
  /** Optional render prop for the summary to allow conditional rendering based on showDetail */
  children?: (props: { showDetail: boolean }) => ReactNode;
}

const styles = sortCx({
  wrapper: "inline-flex items-center gap-1.5",
  summary: "text-body-2-medium text-text-secondary",
  detail: "text-body-2-regular text-text-secondary",
  icon: "size-4 shrink-0 text-foreground-icon-tertiary",
  expandButton: [
    "inline-flex items-center gap-1 rounded-md px-2 py-0.5",
    "text-caption-1-medium text-foreground-icon-secondary",
    "bg-background-tertiary-default",
    "hover:bg-background-tertiary-hover",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring",
    "transition-[background-color] duration-[var(--input-transition-ms)] ease",
  ].join(" "),
  expandedDetail: "mt-1.5 ml-5.5 text-body-2-regular text-text-tertiary",
});

export function TappableInfo({ summary, detail, className, children }: TappableInfoProps) {
  const [expanded, setExpanded] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Detect mobile viewport on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      // Use a media query to detect touch/mobile
      const mq = window.matchMedia("(pointer: coarse)");
      setIsMobile(mq.matches);
      const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
      mq.addEventListener("change", handler);
      return () => mq.removeEventListener("change", handler);
    }
  }, []);

  // On desktop, always show detail; on mobile, show detail when expanded
  const showDetail = !isMobile || expanded;

  const renderedSummary = children ? children({ showDetail }) : summary;

  return (
    <span className={cx(styles.wrapper, className)}>
      <span className={styles.summary}>{renderedSummary}</span>
      {isMobile ? (
        <>
          <RiInformationFill className={styles.icon} aria-hidden />
          <button
            type="button"
            className={styles.expandButton}
            onClick={() => setExpanded((prev) => !prev)}
            aria-expanded={expanded}
            aria-controls="tappable-info-detail"
          >
            {expanded ? "Hide" : "Show"} details
          </button>
        </>
      ) : (
        <RiInformationFill className={styles.icon} aria-hidden />
      )}
      {showDetail && (
        <span id="tappable-info-detail" className={styles.expandedDetail}>
          {detail}
        </span>
      )}
    </span>
  );
}