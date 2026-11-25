import { useState } from "react";
import type { ReactNode } from "react";

import {
  RiBuilding2Line,
  RiFileSearchLine,
  RiPulseLine,
  RiUserAddLine,
} from "@remixicon/react";
import { Badge } from "@astryxdesign/core/Badge";
import { ClickableCard } from "@astryxdesign/core/ClickableCard";
import { Grid } from "@astryxdesign/core/Grid";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import { detectPlatform } from "./runtime";
import { defaultClinicalView } from "./platform";
import IntakeScreen from "./IntakeScreen";
import PatientHistoryScreen from "./PatientHistoryScreen";
import WardBoard from "./WardBoard";
import StudyInstrumentation from "./StudyInstrumentation";

type ClinicalView = "board" | "intake" | "history" | "study";

const clinicalViews: Array<{
  id: ClinicalView;
  title: string;
  description: string;
  icon: ReactNode;
  variant: "blue" | "green" | "purple" | "yellow";
}> = [
  {
    id: "board",
    title: "Today’s ward",
    description: "Beds, tasks, observations, and investigations",
    icon: <RiBuilding2Line aria-hidden="true" />,
    variant: "blue",
  },
  {
    id: "intake",
    title: "New patient",
    description: "Start an encounter and record intake details",
    icon: <RiUserAddLine aria-hidden="true" />,
    variant: "green",
  },
  {
    id: "history",
    title: "Find a patient",
    description: "Search records and review patient history",
    icon: <RiFileSearchLine aria-hidden="true" />,
    variant: "purple",
  },
  {
    id: "study",
    title: "Study timing",
    description: "Review workflow timing instrumentation",
    icon: <RiPulseLine aria-hidden="true" />,
    variant: "yellow",
  },
];

export default function ClinicalWorkspace() {
  const [view, setView] = useState<ClinicalView>(() =>
    defaultClinicalView(detectPlatform()),
  );

  return (
    <>
      <section aria-labelledby="clinical-workspace-heading">
        <VStack gap={4}>
          <VStack gap={1}>
            <Heading level={1} id="clinical-workspace-heading">Clinical workspace</Heading>
            <Text as="p" type="supporting" color="secondary">
              Choose the area you need. Your current workspace is highlighted.
            </Text>
          </VStack>
          <Grid columns={{ minWidth: 220, max: 4, repeat: "fit" }} gap={4}>
            {clinicalViews.map((item) => {
              const active = view === item.id;
              return (
                <ClickableCard
                  key={item.id}
                  label={`${item.title}${active ? ", current workspace" : ""}`}
                  onClick={() => setView(item.id)}
                  variant={item.variant}
                  elevation={active ? "med" : "low"}
                  height="100%"
                >
                  <VStack gap={4} vAlign="between" minHeight={132}>
                    <HStack hAlign="between" vAlign="center" gap={2}>
                      {item.icon}
                      {active ? <Badge variant="blue" label="Open" /> : null}
                    </HStack>
                    <VStack gap={1}>
                      <Heading level={2} accessibilityLevel={2}>{item.title}</Heading>
                      <Text as="p" type="supporting" color="secondary" textWrap="pretty">
                        {item.description}
                      </Text>
                    </VStack>
                  </VStack>
                </ClickableCard>
              );
            })}
          </Grid>
        </VStack>
      </section>

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
