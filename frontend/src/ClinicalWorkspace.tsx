import { useState } from "react";
import type { Selection } from "react-aria-components";

import {
  SegmentedControl,
  SegmentedControlItem,
} from "@/components/base/segmented-control/segmented-control";

import { detectPlatform } from "./runtime";
import { defaultClinicalView } from "./platform";
import IntakeScreen from "./IntakeScreen";
import PatientHistoryScreen from "./PatientHistoryScreen";
import QueueBoard from "./QueueBoard";

type ClinicalView = "queue" | "intake" | "history";

export default function ClinicalWorkspace() {
  const [view, setView] = useState<ClinicalView>(() =>
    defaultClinicalView(detectPlatform()),
  );

  return (
    <>
      {/*
       * min-h-11 keeps the view switch on the 44px touch minimum for bedside
       * use; the installed control's own py-1 yields a 28px target.
       */}
      <SegmentedControl
        aria-label="Clinical views"
        className="w-fit justify-self-start"
        selectedKeys={new Set([view])}
        onSelectionChange={(keys: Selection) => {
          const next = [...keys][0];
          if (next === "queue" || next === "intake" || next === "history") {
            setView(next);
          }
        }}
      >
        <SegmentedControlItem id="queue" className="min-h-11 px-4">
          Queue
        </SegmentedControlItem>
        <SegmentedControlItem id="intake" className="min-h-11 px-4">
          Intake
        </SegmentedControlItem>
        <SegmentedControlItem id="history" className="min-h-11 px-4">
          Patient history
        </SegmentedControlItem>
      </SegmentedControl>

      {view === "queue" ? (
        <QueueBoard />
      ) : view === "intake" ? (
        <IntakeScreen />
      ) : (
        <PatientHistoryScreen />
      )}
    </>
  );
}
