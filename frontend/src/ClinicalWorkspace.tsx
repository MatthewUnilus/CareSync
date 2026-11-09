import { useState } from "react";
import type { Selection } from "react-aria-components";

import {
  SegmentedControl,
  SegmentedControlItem,
} from "@/components/base/segmented-control/segmented-control";

import { detectPlatform } from "./runtime";
import { defaultClinicalView } from "./platform";
import IntakeScreen from "./IntakeScreen";
import QueueBoard from "./QueueBoard";

type ClinicalView = "queue" | "intake";

export default function ClinicalWorkspace() {
  const [view, setView] = useState<ClinicalView>(() =>
    defaultClinicalView(detectPlatform()),
  );

  return (
    <>
      <SegmentedControl
        aria-label="Clinical views"
        className="w-fit justify-self-start"
        selectedKeys={new Set([view])}
        onSelectionChange={(keys: Selection) => {
          const next = [...keys][0];
          if (next === "queue" || next === "intake") {
            setView(next);
          }
        }}
      >
        <SegmentedControlItem id="queue">Queue</SegmentedControlItem>
        <SegmentedControlItem id="intake">Intake</SegmentedControlItem>
      </SegmentedControl>

      {view === "queue" ? <QueueBoard /> : <IntakeScreen />}
    </>
  );
}
