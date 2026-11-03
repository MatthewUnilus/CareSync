import { useState } from "react";

import { detectPlatform } from "./runtime";
import { defaultClinicalView } from "./platform";
import IntakeScreen from "./IntakeScreen";
import QueueBoard from "./QueueBoard";

export default function ClinicalWorkspace() {
  const [view, setView] = useState(() =>
    defaultClinicalView(detectPlatform()),
  );

  return (
    <>
      <nav className="view-switch" aria-label="Clinical views">
        <button
          type="button"
          className={view === "queue" ? undefined : "secondary"}
          aria-pressed={view === "queue"}
          onClick={() => setView("queue")}
        >
          Queue
        </button>
        <button
          type="button"
          className={view === "intake" ? undefined : "secondary"}
          aria-pressed={view === "intake"}
          onClick={() => setView("intake")}
        >
          Intake
        </button>
      </nav>

      {view === "queue" ? <QueueBoard /> : <IntakeScreen />}
    </>
  );
}
