import { useState, type ReactNode } from "react";
import { cx } from "@/utils/cx";
import {
  TriageButton,
  TriageConfirmationModal,
  TriageConnectionBanner,
  TriageLabeledInput,
  TriagePatientCardCompact,
  TriagePatientListItem,
  TriagePriorityBadge,
  TriagePriorityOverrideForm,
  TriagePriorityResultCard,
  TriageQueueState,
  TriageVitalSignsCard,
} from "@/components/triage";

/**
 * TriageAssist UI Kit gallery — renders every component in every state,
 * mirroring the kit's four Figma sheets:
 *   Foundations · Controls · Clinical patterns · Feedback & safety.
 *
 * Bound to BoardUI's semantic tokens and composite type utilities — the kit
 * has no token system of its own. Copy follows CONTEXT.md's glossary: Machine
 * Recommendation, Urgency Level, Override, Final Decision — never "AI", never
 * "reviewed". Connection states are the honest set (synced renders nothing;
 * no offline/local-cache claims — the product polls and shows load failures
 * inline).
 */

function Sheet({
  id,
  title,
  caption,
  children,
}: {
  id: string;
  title: string;
  caption: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h2 id={id} className="text-title-2-medium text-text-primary">
          {title}
        </h2>
        <p className="text-caption-1-regular text-text-secondary">{caption}</p>
      </header>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start gap-4">
      <span className="w-44 shrink-0 pt-3 text-caption-1-medium text-text-secondary">
        {label}
      </span>
      {children}
    </div>
  );
}

function Swatch({
  name,
  surface,
  ink,
}: {
  name: string;
  surface: string;
  ink: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <span
        className={cx(
          "flex h-10 w-16 items-center justify-center rounded-lg border border-border-button-default",
          surface,
        )}
      >
        <span className={cx("h-1.5 w-8 rounded-full", ink)} />
      </span>
      <span className="text-caption-1-regular text-text-secondary">{name}</span>
    </div>
  );
}

const DEMO_URGENCY_LEVELS = [
  "high",
  "medium",
  "low",
  "pending",
  "unavailable",
] as const;

export default function TriageKitGallery() {
  const [modalOpen, setModalOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [overrideSaved, setOverrideSaved] = useState(false);

  return (
    <main className="min-h-dvh bg-background-full">
      <div className="mx-auto flex max-w-[1100px] flex-col gap-10 px-6 py-10">
        <header className="flex flex-col gap-2">
          <p className="text-caption-1-medium text-text-secondary">
            TriageAssist · UI kit
          </p>
          <h1 className="text-title-1-medium text-text-primary">
            TriageAssist UI Kit
          </h1>
          <p className="text-body-regular text-text-secondary">
            Reusable local components · BoardUI token bindings · Visible state
            variants
          </p>
        </header>

        {/* ============ Foundations ============ */}
        <Sheet
          id="foundations"
          title="Foundations"
          caption="Pair every Urgency Level with its label."
        >
          <Row label="Urgency badge">
            <div className="flex flex-wrap gap-2">
              {DEMO_URGENCY_LEVELS.map((priority) => (
                <TriagePriorityBadge key={priority} priority={priority} />
              ))}
            </div>
          </Row>
          <Row label="Status pairs">
            <div className="flex flex-wrap items-start gap-3 rounded-3xl border border-border-button-default bg-background-primary-default p-6">
              <Swatch
                name="status/rose (High)"
                surface="bg-status-rose-background"
                ink="bg-status-rose-text"
              />
              <Swatch
                name="status/yellow (Medium)"
                surface="bg-status-yellow-background"
                ink="bg-status-yellow-text"
              />
              <Swatch
                name="status/lime (Low)"
                surface="bg-status-lime-background"
                ink="bg-status-lime-text"
              />
              <Swatch
                name="status/blue (awaiting)"
                surface="bg-status-blue-background"
                ink="bg-status-blue-text"
              />
              <Swatch
                name="status/orange (Override flag)"
                surface="bg-status-orange-background"
                ink="bg-status-orange-text"
              />
            </div>
          </Row>
          <Row label="Type ramp">
            <div className="flex flex-col gap-2 rounded-3xl border border-border-button-default bg-background-primary-default p-6">
              {(
                [
                  ["text-title-1-medium", "Page title"],
                  ["text-title-2-medium", "Section title"],
                  ["text-title-3-medium", "Card title"],
                  ["text-headline-semibold", "Headline"],
                  ["text-body-medium", "Body medium"],
                  ["text-body-regular", "Body regular"],
                  ["text-caption-1-medium", "Caption medium"],
                  ["text-caption-1-regular", "Caption regular"],
                ] as const
              ).map(([utility, sample]) => (
                <div key={utility} className="flex items-baseline gap-4">
                  <span className="w-52 shrink-0 font-mono text-caption-1-regular text-text-tertiary">
                    {utility}
                  </span>
                  <span
                    className={cx(
                      utility,
                      "text-text-primary",
                      utility === "text-caption-1-regular" && "text-text-secondary",
                    )}
                  >
                    {sample}
                  </span>
                </div>
              ))}
            </div>
          </Row>
        </Sheet>

        {/* ============ Controls ============ */}
        <Sheet
          id="controls"
          title="Controls"
          caption="48 px minimum touch targets · One primary action per section."
        >
          <Row label="Buttons">
            <div className="flex flex-wrap items-start gap-3">
              {(["primary", "secondary", "destructive"] as const).map(
                (variant) => (
                  <div key={variant} className="flex flex-col gap-2">
                    <TriageButton variant={variant}>
                      {variant[0].toUpperCase() + variant.slice(1)}
                    </TriageButton>
                    <TriageButton variant={variant} state="disabled">
                      {variant[0].toUpperCase() + variant.slice(1)}
                    </TriageButton>
                    <TriageButton variant={variant} state="loading">
                      {variant[0].toUpperCase() + variant.slice(1)}
                    </TriageButton>
                  </div>
                ),
              )}
            </div>
          </Row>
          <Row label="Labeled input">
            <div className="flex flex-wrap items-start gap-3">
              <TriageLabeledInput
                label="Patient name *"
                helper="Use the name on the patient record."
                placeholder="Enter full name"
              />
              <TriageLabeledInput
                label="Oxygen saturation"
                unit="%"
                helper="Measure with the pulse oximeter on record."
                defaultValue="97"
              />
              <TriageLabeledInput
                label="Oxygen saturation"
                unit="%"
                error
                helper="Enter a value between 50 and 100."
                defaultValue="145"
              />
              <TriageLabeledInput
                label="Patient name *"
                helper="Unavailable while saving."
                disabled
                value="Maya Patel"
              />
            </div>
          </Row>
        </Sheet>

        {/* ============ Clinical patterns ============ */}
        <Sheet
          id="clinical-patterns"
          title="Clinical patterns"
          caption="Separate the Machine Recommendation from the Final Decision."
        >
          <Row label="Patient list">
            <div className="flex flex-col gap-3">
              <TriagePatientListItem
                name="01 · Maya Patel"
                meta="TA-0104 · 46 years"
                priority="high"
                symptom="Chest pain, shortness of breath"
                waiting="Waiting 04 min"
                reviewStatus="Machine recommendation: High · Awaiting Override"
                onSelect={() => {}}
              />
              <TriagePatientListItem
                name="02 · Louis Baker"
                meta="TA-0105 · 61 years"
                priority="medium"
                symptom="Fever, dehydration"
                waiting="Waiting 11 min"
                reviewStatus="Machine recommendation: Medium · Overridden by A. Chen — clinical gestalt"
                onSelect={() => {}}
              />
              <TriagePatientListItem
                name="03 · Sofia Reyes"
                meta="TA-0106 · 33 years"
                priority="low"
                symptom="Sprained ankle"
                waiting="Waiting 26 min"
                reviewStatus="Machine recommendation: Low · Awaiting Override"
                onSelect={() => {}}
              />
            </div>
          </Row>
          <Row label="Compact cards">
            <div className="flex flex-wrap gap-3">
              <TriagePatientCardCompact
                name="Alex Morgan · TA-0107"
                urgency="high"
                queue="Position 07 · Waiting 12 min"
                aiStatus="Machine recommendation: High · Awaiting Override"
                actionLabel="Override"
                onAction={() => {}}
              />
              <TriagePatientCardCompact
                name="Jordan Lee · TA-0108"
                urgency="pending"
                aiStatus="Assessment not yet requested"
                actionLabel="Open local draft"
                onAction={() => {}}
              />
            </div>
          </Row>
          <Row label="Vital signs">
            <div className="flex flex-wrap gap-3">
              <TriageVitalSignsCard
                rows={[
                  { label: "Heart rate", value: "88 bpm" },
                  { label: "Blood pressure", value: "128 / 84 mmHg" },
                  { label: "SpO₂", value: "97 %" },
                  { label: "Respiratory rate", value: "18 / min" },
                ]}
                recorded="Recorded 09:42 · A. Chen"
              />
              <TriageVitalSignsCard
                title="Vital signs · Sofia Reyes"
                rows={[
                  { label: "Heart rate", value: null },
                  { label: "Blood pressure", value: "118 / 76 mmHg" },
                  { label: "SpO₂", value: null },
                ]}
              />
            </div>
          </Row>
          <Row label="Machine Recommendation">
            <div className="flex flex-wrap gap-3">
              <TriagePriorityResultCard
                patient="Sofia Reyes · TA-0106"
                recommendation="low"
                explanation="Stable vitals, no red-flag symptoms, minor mechanism of injury."
                assessedAt="Assessment · 09:42"
                decisionStatus="awaiting"
                onAction={() => {}}
              />
              <TriagePriorityResultCard
                patient="Sofia Reyes · TA-0106"
                recommendation="low"
                explanation="Stable vitals, no red-flag symptoms, minor mechanism of injury."
                assessedAt="Assessment · 09:42"
                decisionStatus="overridden"
                decisionNote="Overridden by A. Chen · 09:44 — clinical gestalt"
                finalDecision="Final Decision: Medium"
                onAction={() => {}}
              />
              <TriagePriorityResultCard
                patient="Sofia Reyes · TA-0106"
                recommendation="unavailable"
                explanation="Vital-signs capture is incomplete, so no recommendation was produced."
                assessedAt="Assessment · 09:42"
                decisionStatus="unavailable"
                onAction={() => {}}
              />
            </div>
          </Row>
          <Row label="Override form">
            <div className="flex flex-col items-start gap-3">
              <TriagePriorityOverrideForm
                key={overrideSaved ? "saved" : "form"}
                patient="Sofia Reyes · TA-0106"
                recommendation="low"
                currentPriority="low"
                onConfirm={async () => {
                  await new Promise((resolve) => setTimeout(resolve, 800));
                  setOverrideSaved(true);
                }}
                onCancel={() => {}}
              />
              {overrideSaved ? (
                <p className="text-body-medium text-status-lime-text" role="status">
                  Override recorded — the queue's Final Decision updated.
                </p>
              ) : null}
            </div>
          </Row>
          <Row label="Reset form">
            <TriageButton
              variant="secondary"
              onClick={() => setOverrideSaved(false)}
            >
              Reset override form
            </TriageButton>
          </Row>
        </Sheet>

        {/* ============ Feedback & safety ============ */}
        <Sheet
          id="feedback-safety"
          title="Feedback & safety"
          caption="Show incomplete records and sync states explicitly."
        >
          <Row label="Connection banner">
            <div className="flex max-w-prose flex-col items-start gap-3">
              <p className="text-body-regular text-text-secondary">
                <code className="font-mono">synced</code> renders nothing — the
                product screens poll every 5 seconds and show load failures
                inline, so the banner only mounts while syncing or after a
                failed load.
              </p>
              <TriageConnectionBanner state="syncing" />
              <TriageConnectionBanner
                state="error"
                message="The server didn't respond to the last request."
                onRetry={() => {}}
              />
            </div>
          </Row>
          <Row label="Queue state">
            <div className="flex flex-wrap gap-3">
              <TriageQueueState mode="loading" />
              <TriageQueueState
                mode="empty"
                title="Queue is empty"
                description="New arrivals will appear here."
                actionLabel="Open intake"
                onAction={() => {}}
              />
              <TriageQueueState
                mode="error"
                title="Couldn't load the queue"
                description="Check the connection, then try again."
                onAction={() => {}}
              />
            </div>
          </Row>
          <Row label="Confirmation modal">
            <TriageButton
              variant="destructive"
              onClick={() => setModalOpen(true)}
            >
              Delete local draft…
            </TriageButton>
          </Row>
        </Sheet>

        <TriageConfirmationModal
          open={modalOpen}
          deleting={deleting}
          title="Delete intake draft?"
          contextLine="Alex Morgan · Local draft TA-0107"
          onConfirm={async () => {
            setDeleting(true);
            await new Promise((resolve) => setTimeout(resolve, 800));
            setDeleting(false);
            setModalOpen(false);
          }}
          onCancel={() => setModalOpen(false)}
        >
          This will remove the saved intake from this device. Records already
          synchronized with the server are not affected.
        </TriageConfirmationModal>

        <footer className="flex flex-col gap-1 border-t border-separator-border pt-6">
          <p className="text-caption-1-regular text-text-secondary">
            Radius: rounded-lg inputs · rounded-2lg buttons · rounded-3xl
            cards, banners and dialogs. Prefer borders over elevation.
          </p>
        </footer>
      </div>
    </main>
  );
}