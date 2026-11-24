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
import WardBoard from "./WardBoard";
import StudyInstrumentation from "./StudyInstrumentation";

type ClinicalView = "board" | "intake" | "history" | "study";

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
        aria-label="Clinical workspace"
        className="w-fit justify-self-start"
        selectedKeys={new Set([view])}
        onSelectionChange={(keys: Selection) => {
          const next = [...keys][0];
          if (next === "board" || next === "intake" || next === "history" || next === "study") {
            setView(next);
          }
        }}
      >
        <SegmentedControlItem id="board" className="min-h-11 px-4">
          Today’s ward
        </SegmentedControlItem>
        <SegmentedControlItem id="intake" className="min-h-11 px-4">
          New patient
        </SegmentedControlItem>
        <SegmentedControlItem id="history" className="min-h-11 px-4">
          Find a patient
        </SegmentedControlItem>
        <SegmentedControlItem id="study" className="min-h-11 px-4">
          Study timing
        </SegmentedControlItem>
      </SegmentedControl>

      {view === "board" ? (
        <WardBoard />
      ) : view === "intake" ? (
        <IntakeScreen />
      ) : view === "history" ? (
        <PatientHistoryScreen />
      ) : (
        <StudyInstrumentation />
      )}
    </>
  );
}
