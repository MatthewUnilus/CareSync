import { useState } from "react";

import IntakeScreen from "./IntakeScreen";
import QueueBoard from "./QueueBoard";

type ClinicalView = "queue" | "intake";

export default function ClinicalWorkspace() {
  const [view, setView] = useState<ClinicalView>("queue");

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
