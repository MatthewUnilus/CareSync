import { useCallback, useRef, useState } from "react";

import { Button } from "@astryxdesign/core/Button";
import { Divider } from "@astryxdesign/core/Divider";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Layout, LayoutContent } from "@astryxdesign/core/Layout";
import { List, ListItem } from "@astryxdesign/core/List";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { VStack } from "@astryxdesign/core/VStack";

import { api, errorText } from "./api";
import type { LaboratoryInvestigation, LaboratoryWorklist } from "./api";
import { formatInstant } from "./queueDisplay";
import { usePolling } from "./usePolling";

const groups = [
  { key: "incoming", title: "Incoming requests", empty: "No requests to acknowledge." },
  { key: "acknowledged", title: "Awaiting results", empty: "No acknowledged requests awaiting results." },
  { key: "published", title: "Published results", empty: "No results published yet." },
] as const;

type Group = (typeof groups)[number]["key"];

export default function LaboratoryDashboard() {
  const [worklist, setWorklist] = useState<LaboratoryWorklist | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ message: string; error?: boolean } | null>(null);
  const request = useRef(0);
  const load = useCallback(async () => {
    const id = ++request.current;
    try {
      const next = await api.laboratoryWorklist();
      if (id === request.current) {
        setWorklist(next);
        setLoadError(null);
      }
    } catch (caught) {
      if (id === request.current) setLoadError(errorText(caught));
    }
  }, []);
  usePolling(load, 5_000);

  return (
    <Layout
      height="fill"
      content={
        <LayoutContent isScrollable={false} padding={6}>
          <VStack gap={6}>
            <HStack hAlign="between" vAlign="center" wrap="wrap" gap={2}>
              <Heading level={1}>Laboratory worklist</Heading>
              <Button label={loadError ? "Retry loading" : "Refresh worklist"} clickAction={load} />
            </HStack>
            {loadError && <p role="alert"><Text>{loadError}</Text></p>}
            {feedback && (
              <p role={feedback.error ? "alert" : "status"}><Text>{feedback.message}</Text></p>
            )}
            {!worklist && !loadError && <p role="status"><Text>Loading laboratory requests…</Text></p>}
            {worklist && groups.map(({ key, title, empty }) => (
              <VStack as="section" gap={2} key={key}>
                <Divider />
                <Heading level={2}>{title}</Heading>
                {worklist[key].length ? (
                  <List hasDividers edge="flush">
                    {worklist[key].map((item) => (
                      <RequestRow key={item.id} item={item} group={key} reload={load} report={setFeedback} />
                    ))}
                  </List>
                ) : <Text as="p" color="secondary">{empty}</Text>}
              </VStack>
            ))}
          </VStack>
        </LayoutContent>
      }
    />
  );
}

function RequestRow({ item, group, reload, report }: {
  item: LaboratoryInvestigation;
  group: Group;
  reload: () => Promise<void>;
  report: (feedback: { message: string; error?: boolean }) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");
  const patient = item.patient.full_name;

  async function save(action: "receive" | "publish") {
    try {
      if (action === "receive") {
        await api.acknowledgeLaboratoryInvestigation(item.id);
        report({ message: `Receipt acknowledged for ${patient}.` });
      } else {
        await api.publishLaboratoryResult(item.id, note);
        report({ message: `Result published for ${patient}.` });
        setEditing(false);
        setNote("");
      }
    } catch (caught) {
      report({ error: true, message: `${patient}: ${errorText(caught)} Check the refreshed worklist before retrying.` });
    } finally {
      await reload();
    }
  }

  return (
    <ListItem
      label={<Text weight="semibold" wordBreak="break-word">{item.test_name} · {patient}</Text>}
      description={
        <VStack gap={1}>
          <Text as="p" color="secondary" wordBreak="break-word">
            {item.patient.hospital_number ? `Hospital number ${item.patient.hospital_number}` : "No hospital number"} · {item.ward}
          </Text>
          <Text as="p" color="secondary">
            Sample taken {formatInstant(item.sample_taken_at)} · Sent {formatInstant(item.lab_sent_at)} by {item.lab_sent_by.display_name}
          </Text>
          {item.lab_received_at && (
            <Text as="p" color="secondary">
              Acknowledged {formatInstant(item.lab_received_at)} by {item.lab_received_by?.display_name}
            </Text>
          )}
          {item.result_available_at && (
            <>
              <Text as="p" color="secondary">
                Published {formatInstant(item.result_available_at)} by {item.result_published_by?.display_name}
              </Text>
              <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}><Text>{item.result_note}</Text></p>
            </>
          )}
          <HStack gap={2} wrap="wrap">
            {group === "incoming" && (
              <Button label="Acknowledge receipt" clickAction={() => save("receive")} />
            )}
            {group === "acknowledged" && !editing && (
              <Button label="Enter result" onClick={() => setEditing(true)} />
            )}
          </HStack>
          {editing && (
            <VStack gap={2}>
              <Text as="p" weight="medium">Check the Patient and test above before publishing.</Text>
              <TextArea label="Result note" value={note} onChange={setNote} htmlMaxLength={2000} isRequired />
              <HStack gap={2} wrap="wrap">
                <Button label="Publish result" variant="primary" isDisabled={!note.trim()} clickAction={() => save("publish")} />
                <Button label="Cancel" onClick={() => { setEditing(false); setNote(""); }} />
              </HStack>
            </VStack>
          )}
        </VStack>
      }
    />
  );
}
