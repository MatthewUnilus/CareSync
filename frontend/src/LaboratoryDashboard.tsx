import { useCallback, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  RiCheckboxCircleLine,
  RiFileList3Line,
  RiFlaskLine,
  RiInboxArchiveLine,
  RiRefreshLine,
  RiTimeLine,
} from "@remixicon/react";
import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Grid } from "@astryxdesign/core/Grid";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { VStack } from "@astryxdesign/core/VStack";

import { api, errorText } from "./api";
import type { LaboratoryInvestigation, LaboratoryWorklist } from "./api";
import { formatInstant } from "./queueDisplay";
import { usePolling } from "./usePolling";

type WorkGroup = "incoming" | "acknowledged" | "published";

interface Feedback {
  message: string;
  error?: boolean;
}

export default function LaboratoryDashboard() {
  const [worklist, setWorklist] = useState<LaboratoryWorklist | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
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

  const incoming = worklist?.incoming.length ?? 0;
  const acknowledged = worklist?.acknowledged.length ?? 0;
  const published = worklist?.published.length ?? 0;
  const total = incoming + acknowledged + published;

  return (
    <VStack gap={6}>
      <section className="rounded-3xl border border-accent-100 bg-accent-50 p-6 sm:p-8">
        <HStack hAlign="between" vAlign="center" wrap="wrap" gap={4}>
          <VStack gap={2}>
            <HStack gap={2} vAlign="center">
              <StatusDot
                variant={loadError ? "error" : "success"}
                label={loadError ? "Worklist connection interrupted" : "Worklist connected"}
                isPulsing={!loadError}
              />
              <Text type="label" color="secondary">
                {loadError ? "Connection needs attention" : "Live laboratory operations"}
              </Text>
            </HStack>
            <Heading level={1} type="display-3" weight="semibold" textWrap="balance">
              Laboratory command centre
            </Heading>
            <Text as="p" type="large" color="secondary" textWrap="pretty">
              Receive samples, publish results, and keep every ward request moving.
            </Text>
          </VStack>
          <Button
            label={loadError ? "Retry loading" : "Refresh worklist"}
            variant="primary"
            size="lg"
            icon={<RiRefreshLine aria-hidden="true" />}
            clickAction={load}
          />
        </HStack>
      </section>

      {loadError ? (
        <Banner
          status="error"
          title="The worklist could not be refreshed"
          description={loadError}
          endContent={<Button label="Try again" variant="secondary" clickAction={load} />}
        />
      ) : null}

      {feedback ? (
        <Banner
          status={feedback.error ? "error" : "success"}
          title={feedback.error ? "The request was not updated" : "Worklist updated"}
          description={feedback.message}
          isDismissable={!feedback.error}
          dismissLabel="Dismiss message"
          onDismiss={() => setFeedback(null)}
        />
      ) : null}

      <Grid columns={{ minWidth: 180, max: 4, repeat: "fit" }} gap={4}>
        <MetricCard
          label="Awaiting receipt"
          value={incoming}
          detail="Samples sent by wards"
          icon={<RiInboxArchiveLine aria-hidden="true" />}
          variant="blue"
        />
        <MetricCard
          label="In progress"
          value={acknowledged}
          detail="Received, result pending"
          icon={<RiTimeLine aria-hidden="true" />}
          variant="yellow"
        />
        <MetricCard
          label="Published"
          value={published}
          detail="Results returned to wards"
          icon={<RiCheckboxCircleLine aria-hidden="true" />}
          variant="green"
        />
        <MetricCard
          label="Total workload"
          value={total}
          detail="Requests in this worklist"
          icon={<RiFlaskLine aria-hidden="true" />}
          variant="purple"
        />
      </Grid>

      {!worklist && !loadError ? (
        <Card padding={8} variant="muted">
          <EmptyState
            title="Opening the laboratory worklist"
            description="Current sample requests and results will appear here."
            icon={<RiFlaskLine aria-hidden="true" />}
            headingLevel={2}
          />
        </Card>
      ) : null}

      {worklist ? (
        <div className="grid min-w-0 gap-6 lg:grid-cols-3">
          <section className="min-w-0 lg:col-span-2" aria-labelledby="active-work-heading">
            <VStack gap={5}>
              <SectionHeading
                id="active-work-heading"
                title="Active work queue"
                description="Requests that still need a laboratory action."
                count={incoming + acknowledged}
              />

              <WorkGroupSection
                title="Needs receipt"
                description="Confirm that these samples reached the laboratory."
                items={worklist.incoming}
                group="incoming"
                empty="No samples are waiting to be received."
                reload={load}
                report={setFeedback}
              />

              <WorkGroupSection
                title="Ready for results"
                description="Samples received by the laboratory and awaiting a result."
                items={worklist.acknowledged}
                group="acknowledged"
                empty="No received samples are waiting for results."
                reload={load}
                report={setFeedback}
              />
            </VStack>
          </section>

          <section className="min-w-0" aria-labelledby="published-heading">
            <VStack gap={4}>
              <SectionHeading
                id="published-heading"
                title="Published results"
                description="Completed results visible to the ward."
                count={published}
              />
              {worklist.published.length ? (
                <VStack gap={3}>
                  {worklist.published.map((item) => (
                    <RequestCard
                      key={item.id}
                      item={item}
                      group="published"
                      reload={load}
                      report={setFeedback}
                      compact
                    />
                  ))}
                </VStack>
              ) : (
                <Card padding={6} variant="muted">
                  <EmptyState
                    title="No published results"
                    description="Completed results will collect here."
                    icon={<RiFileList3Line aria-hidden="true" />}
                    headingLevel={3}
                    isCompact
                  />
                </Card>
              )}
            </VStack>
          </section>
        </div>
      ) : null}
    </VStack>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon,
  variant,
}: {
  label: string;
  value: number;
  detail: string;
  icon: ReactNode;
  variant: "blue" | "yellow" | "green" | "purple";
}) {
  return (
    <Card padding={5} variant={variant} elevation="low" minHeight={144}>
      <VStack gap={4} vAlign="between" minHeight="100%">
        <HStack hAlign="between" vAlign="center" gap={2}>
          <Text type="label" weight="semibold">{label}</Text>
          {icon}
        </HStack>
        <VStack gap={0.5}>
          <Text type="display-2" weight="semibold" hasTabularNumbers>{value}</Text>
          <Text type="supporting" color="secondary">{detail}</Text>
        </VStack>
      </VStack>
    </Card>
  );
}

function SectionHeading({
  id,
  title,
  description,
  count,
}: {
  id: string;
  title: string;
  description: string;
  count: number;
}) {
  return (
    <HStack hAlign="between" vAlign="start" gap={3}>
      <VStack gap={1}>
        <Heading level={2} id={id}>{title}</Heading>
        <Text as="p" type="supporting" color="secondary">{description}</Text>
      </VStack>
      <Badge variant="blue" label={count} />
    </HStack>
  );
}

function WorkGroupSection({
  title,
  description,
  items,
  group,
  empty,
  reload,
  report,
}: {
  title: string;
  description: string;
  items: LaboratoryInvestigation[];
  group: Exclude<WorkGroup, "published">;
  empty: string;
  reload: () => Promise<void>;
  report: (feedback: Feedback) => void;
}) {
  return (
    <VStack as="section" gap={3}>
      <HStack hAlign="between" vAlign="center" gap={3}>
        <VStack gap={0.5}>
          <Heading level={3}>{title}</Heading>
          <Text as="p" type="supporting" color="secondary">{description}</Text>
        </VStack>
        {items.length ? <Text type="label" hasTabularNumbers>{items.length}</Text> : null}
      </HStack>
      {items.length ? (
        <VStack gap={3}>
          {items.map((item) => (
            <RequestCard
              key={item.id}
              item={item}
              group={group}
              reload={reload}
              report={report}
            />
          ))}
        </VStack>
      ) : (
        <Card padding={5} variant="muted">
          <EmptyState
            title="Queue clear"
            description={empty}
            icon={<RiCheckboxCircleLine aria-hidden="true" />}
            headingLevel={4}
            isCompact
          />
        </Card>
      )}
    </VStack>
  );
}

function RequestCard({
  item,
  group,
  reload,
  report,
  compact = false,
}: {
  item: LaboratoryInvestigation;
  group: WorkGroup;
  reload: () => Promise<void>;
  report: (feedback: Feedback) => void;
  compact?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState<"receive" | "publish" | null>(null);
  const patient = item.patient.full_name;

  async function save(action: "receive" | "publish") {
    setPending(action);
    try {
      if (action === "receive") {
        await api.acknowledgeLaboratoryInvestigation(item.id);
        report({ message: `Receipt acknowledged for ${patient}.` });
      } else {
        await api.publishLaboratoryResult(item.id, note.trim());
        report({ message: `Result published for ${patient}.` });
        setEditing(false);
        setNote("");
      }
    } catch (caught) {
      report({
        error: true,
        message: `${patient}: ${errorText(caught)} Check the refreshed worklist before retrying.`,
      });
    } finally {
      setPending(null);
      await reload();
    }
  }

  return (
    <Card padding={compact ? 4 : 5} elevation="low">
      <VStack gap={compact ? 3 : 4}>
        <HStack hAlign="between" vAlign="start" wrap="wrap" gap={3}>
          <VStack gap={1}>
            <Heading level={compact ? 3 : 4} wordBreak="break-word">{item.test_name}</Heading>
            <Text as="p" weight="semibold" wordBreak="break-word">{patient}</Text>
          </VStack>
          {group === "incoming" ? (
            <Badge variant="warning" label="Needs receipt" />
          ) : group === "acknowledged" ? (
            <Badge variant="info" label="In progress" />
          ) : (
            <Badge variant="green" label="Published" />
          )}
        </HStack>

        <Grid columns={{ minWidth: compact ? 130 : 160, max: compact ? 1 : 2, repeat: "fit" }} gap={3}>
          <Metadata label="Patient number" value={item.patient.hospital_number ?? "Not recorded"} />
          <Metadata label="Location" value={`Ward ${item.ward}`} />
          {!compact ? <Metadata label="Sample taken" value={formatInstant(item.sample_taken_at)} /> : null}
          {!compact ? <Metadata label="Sent to lab" value={formatInstant(item.lab_sent_at)} /> : null}
        </Grid>

        {!compact ? (
          <Text as="p" type="supporting" color="secondary" wordBreak="break-word">
            Sent by {item.lab_sent_by.display_name}
            {item.lab_received_at
              ? ` · Received ${formatInstant(item.lab_received_at)} by ${item.lab_received_by?.display_name ?? "laboratory"}`
              : ""}
          </Text>
        ) : null}

        {item.result_available_at ? (
          <VStack gap={2}>
            <Text as="p" type="supporting" color="secondary">
              Published {formatInstant(item.result_available_at)} by {item.result_published_by?.display_name ?? "laboratory"}
            </Text>
            <div className="rounded-xl bg-background-secondary-default p-3">
              <Text as="p" wordBreak="break-word">{item.result_note}</Text>
            </div>
          </VStack>
        ) : null}

        {group === "incoming" ? (
          <div>
            <Button
              label="Acknowledge receipt"
              variant="primary"
              isLoading={pending === "receive"}
              clickAction={() => save("receive")}
            />
          </div>
        ) : null}

        {group === "acknowledged" && !editing ? (
          <div>
            <Button label="Enter result" variant="primary" onClick={() => setEditing(true)} />
          </div>
        ) : null}

        {editing ? (
          <VStack gap={3}>
            <Text as="p" type="supporting" color="secondary">
              Confirm the patient and test above, then enter the result exactly as supplied.
            </Text>
            <TextArea
              label="Result note"
              value={note}
              onChange={setNote}
              htmlMaxLength={2000}
              rows={5}
              width="100%"
              isRequired
            />
            <HStack gap={2} wrap="wrap">
              <Button
                label="Publish result"
                variant="primary"
                isDisabled={!note.trim()}
                isLoading={pending === "publish"}
                clickAction={() => save("publish")}
              />
              <Button
                label="Cancel"
                variant="secondary"
                isDisabled={pending !== null}
                onClick={() => {
                  setEditing(false);
                  setNote("");
                }}
              />
            </HStack>
          </VStack>
        ) : null}
      </VStack>
    </Card>
  );
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <VStack gap={0.5}>
      <Text type="supporting" color="secondary">{label}</Text>
      <Text type="label" weight="medium" wordBreak="break-word">{value}</Text>
    </VStack>
  );
}
