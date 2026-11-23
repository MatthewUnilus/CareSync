import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "@/components/base/segmented-control/segmented-control";
import { Select, SelectItem } from "@/components/base/select/select";
import { Textarea } from "@/components/base/textarea/textarea";
import { toast } from "@/components/base/toast/toast";
import { cx } from "@/utils/cx";

import { api, errorText } from "./api";
import type { BoardAdmission, NewTaskPayload, Task, TaskPerson } from "./api";
import {
  cardClass,
  figureClass,
  mutedTextClass,
  noticeClass,
  sectionLabelClass,
} from "./design";
import { formatInstant } from "./queueDisplay";
import { usePolling } from "./usePolling";

/**
 * Tasks and the ward round (ticket 33).
 *
 * A Task is a unit of work raised against an Admission, by hand from a patient's
 * page or from a saved Ward Round Entry note. This module holds the three faces
 * of that: the cross-patient list a nurse works from (open Tasks across every
 * patient on the ward, filterable to the ones assigned to them), the per-patient
 * writer and record mounted from a board row, and the batch writer that turns one
 * saved round entry into several Tasks at once.
 *
 * Nothing here decides anything clinically. The description is the words given,
 * the due time is optional and shown as given, and the assignee is optional and
 * only ever set by a person. Overdue is the server's mark on read: the list shows
 * the word and nothing acts on it — no escalation, no reassignment, no closing.
 */

/** Operational data: the cross-patient list re-reads every five seconds. */
const TASK_POLL_INTERVAL_MS = 5_000;

/** The sentinel a Select uses for "no assignee"; the wire value is `null`. */
const UNASSIGNED = "unassigned";

/**
 * The ward's staff, read once per consumer so an assignee can be chosen by name.
 * A failure here does not break a list — it only leaves the assign control
 * disabled — so it is reported quietly and retried on demand.
 */
function useWardStaff(): {
  staff: TaskPerson[] | null;
  staffError: string | null;
  reloadStaff: () => Promise<void>;
} {
  const [staff, setStaff] = useState<TaskPerson[] | null>(null);
  const [staffError, setStaffError] = useState<string | null>(null);
  const requestRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestRef.current;
    setStaffError(null);
    try {
      const { users } = await api.wardStaff();
      if (requestRef.current !== requestId) {
        return;
      }
      setStaff(users);
    } catch (caught) {
      if (requestRef.current !== requestId) {
        return;
      }
      setStaffError(errorText(caught));
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      requestRef.current += 1;
    };
  }, [load]);

  return { staff, staffError, reloadStaff: load };
}

/** Whether the assignee list can be offered: loaded, non-empty, and not mid-write. */
function staffReady(staff: TaskPerson[] | null): boolean {
  return staff !== null && staff.length > 0;
}

/**
 * The state of the ward's staff list, placed where a Task's assignee is chosen.
 *
 * `GET /api/ward/staff` failing must not leave the picker silently shut and
 * empty: the picker is disabled but the reason is said, and a Retry is offered so
 * a transient failure is recoverable without reloading the page. An empty staff
 * list is explained too. In every one of these states a Task can still be raised
 * and left unassigned.
 */
function WardStaffStatus({
  staff,
  staffError,
  onRetryStaff,
}: {
  staff: TaskPerson[] | null;
  staffError: string | null;
  onRetryStaff: () => Promise<void> | void;
}) {
  if (staffError !== null) {
    return (
      <section className="flex flex-wrap items-center gap-3 rounded-3xl border border-border-error-default p-4">
        <p className={noticeClass.error} role="alert">
          The ward&rsquo;s staff could not be loaded, so a Task cannot be assigned
          to a person right now. {staffError}
        </p>
        <Button
          variant="secondary"
          className="min-h-11"
          onClick={() => void onRetryStaff()}
        >
          Retry loading staff
        </Button>
      </section>
    );
  }
  if (staff === null) {
    return <p className={mutedTextClass}>Loading the ward&rsquo;s staff…</p>;
  }
  if (staff.length === 0) {
    return (
      <p className={mutedTextClass}>
        No ward staff are available to assign. A Task can still be raised and left
        unassigned.
      </p>
    );
  }
  return null;
}

/**
 * The cross-patient Task list: every open Task across the ward, ordered by the
 * server, so a nurse's outstanding work is visible without walking the corridor.
 * It is operational data, so it re-reads every five seconds through `usePolling`.
 *
 * The filter is by assignee only — "assigned to me", not "my patients" — because
 * a ward that shares the list and a ward that assigns patients both work, and
 * the filter is honest about which question it answers. Completing or assigning a
 * Task writes through the server and then re-reads; nothing is decided here.
 */
export default function TaskList({
  admissions,
  onTasksChanged,
}: {
  /** The open Admissions, so a Task can name where its patient is. */
  admissions: BoardAdmission[];
  /** Called after a write, so the board's open-Task counts refresh too. */
  onTasksChanged: () => Promise<void> | void;
}) {
  const [mine, setMine] = useState(false);
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const { staff, staffError, reloadStaff } = useWardStaff();
  const requestRef = useRef(0);

  // `load` closes over `mine`, so changing the filter re-subscribes the poll and
  // re-reads immediately. A late reply for the previous filter is dropped by the
  // request token rather than shown under the filter now chosen.
  const load = useCallback(async () => {
    const requestId = ++requestRef.current;
    try {
      const { tasks: loaded } = await api.wardTasks(mine, false);
      if (requestRef.current !== requestId) {
        return;
      }
      setTasks(loaded);
      setLoadError(null);
    } catch (caught) {
      if (requestRef.current !== requestId) {
        return;
      }
      setLoadError(errorText(caught));
    }
  }, [mine]);

  usePolling(load, TASK_POLL_INTERVAL_MS);

  // Where each admission's patient is, as the board holds it.
  const locations = new Map(
    admissions.map((admission) => [
      admission.id,
      `${admission.ward} · ${admission.bed}`,
    ]),
  );

  // A write from this list changes both the list and the board's counts.
  const handleChanged = useCallback(async () => {
    await load();
    await onTasksChanged();
  }, [load, onTasksChanged]);

  return (
    <section className={cardClass}>
      <h3 className="text-title-3-medium text-text-primary">
        Open tasks across the ward
      </h3>
      <p className={mutedTextClass}>
        Every open Task across the ward, ordered by the server and re-read every
        few seconds so the list follows the record. Filter to the Tasks assigned
        to you — this is assignment only, not a claim about whose patients these
        are. A Task past its due time is marked overdue and nothing else happens:
        nothing is escalated, reassigned or closed.
      </p>

      <section className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          aria-label="Task filter"
          selectedKeys={[mine ? "mine" : "all"]}
          onSelectionChange={(keys) => {
            setMine(keys.has("mine"));
          }}
        >
          <SegmentedControlItem id="all">All tasks</SegmentedControlItem>
          <SegmentedControlItem id="mine">Assigned to me</SegmentedControlItem>
        </SegmentedControl>
        <Button
          variant="secondary"
          className="min-h-11"
          onClick={() => void load()}
        >
          Refresh tasks
        </Button>
      </section>

      {loadError !== null ? (
        <section className="flex flex-col gap-2">
          <p className={noticeClass.error} role="alert">
            {loadError}
          </p>
          <footer>
            <Button
              variant="secondary"
              className="min-h-11"
              onClick={() => void load()}
            >
              Retry loading tasks
            </Button>
          </footer>
        </section>
      ) : tasks === null ? (
        <p className={mutedTextClass}>Loading tasks…</p>
      ) : tasks.length === 0 ? (
        <p className={mutedTextClass}>
          {mine
            ? "No open tasks are assigned to you."
            : "No open tasks across the ward."}
        </p>
      ) : (
        <>
          <WardStaffStatus
            staff={staff}
            staffError={staffError}
            onRetryStaff={reloadStaff}
          />
          <ol className="flex flex-col gap-4">
            {tasks.map((task) => (
              <TaskItem
                key={task.id}
                task={task}
                staff={staff}
                location={locations.get(task.admission_id) ?? "Not on the board"}
                onChanged={handleChanged}
              />
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

/**
 * One Admission's Tasks: the hand-raiser and the record of what was raised,
 * mounted from a patient's row on the board so a Task can be raised by hand from
 * the patient's own page. The record shows open and done Tasks together, so
 * marking one done removes it from the open lists but keeps it in the record.
 */
export function AdmissionTasks({
  admissionId,
  onTasksChanged,
}: {
  admissionId: number;
  onTasksChanged: () => Promise<void> | void;
}) {
  const { staff, staffError, reloadStaff } = useWardStaff();

  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [assignee, setAssignee] = useState<string>(UNASSIGNED);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const requestRef = useRef(0);

  const load = useCallback(async (id: number) => {
    const requestId = ++requestRef.current;
    setLoadError(null);
    try {
      const { tasks: loaded } = await api.admissionTasks(id);
      if (requestRef.current !== requestId) {
        return;
      }
      setTasks(loaded);
    } catch (caught) {
      if (requestRef.current !== requestId) {
        return;
      }
      setLoadError(errorText(caught));
    }
  }, []);

  // A change of Admission is a change of patient: clear the raiser and re-read.
  useEffect(() => {
    setDescription("");
    setDueAt("");
    setAssignee(UNASSIGNED);
    setSaveError(null);
    void load(admissionId);
    return () => {
      requestRef.current += 1;
    };
  }, [admissionId, load]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = description.trim();
    if (!trimmed) {
      setSaveError("Describe the task.");
      return;
    }
    let due: string | null = null;
    if (dueAt !== "") {
      const parsed = new Date(dueAt);
      if (Number.isNaN(parsed.getTime())) {
        setSaveError("Enter a valid due time, or leave it blank.");
        return;
      }
      due = parsed.toISOString();
    }
    const payload: NewTaskPayload = {
      description: trimmed,
      due_at: due,
      assignee_user_id: assignee === UNASSIGNED ? null : Number(assignee),
    };
    setSaving(true);
    setSaveError(null);
    try {
      await api.createAdmissionTask(admissionId, payload);
      toast.success("Task raised.");
      setDescription("");
      setDueAt("");
      setAssignee(UNASSIGNED);
      await load(admissionId);
      // The board's open-Task count changes with a new Task.
      await onTasksChanged();
    } catch (caught) {
      setSaveError(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={cardClass}>
      <h4 className="text-title-3-medium text-text-primary">Tasks</h4>
      <p className={mutedTextClass}>
        Raise a unit of work against this patient by hand. The description is the
        instruction as given; the due time is optional, so work with a deadline is
        distinguishable from work without one; and the assignee is optional, so a
        Task can sit on one person or on the shared ward. Nothing is escalated or
        reassigned on its own.
      </p>

      <form className="flex flex-col gap-4" onSubmit={save}>
        <fieldset className="grid min-w-0 gap-4 sm:grid-cols-2">
          <legend className={sectionLabelClass}>Raise a task</legend>
          <Textarea
            className="sm:col-span-2"
            rows={2}
            label="Description"
            hint="The work as instructed"
            value={description}
            isDisabled={saving}
            onChange={setDescription}
          />
          <Input
            label="Due (optional)"
            type="datetime-local"
            value={dueAt}
            isDisabled={saving}
            onChange={setDueAt}
          />
          <Select
            label="Assign to (optional)"
            className="w-full"
            triggerClassName="min-h-11"
            placeholder="Unassigned"
            selectedKey={assignee}
            isDisabled={saving || !staffReady(staff)}
            onSelectionChange={(key) => {
              if (typeof key === "string") {
                setAssignee(key);
              }
            }}
          >
            <SelectItem id={UNASSIGNED} textValue="Unassigned">
              Unassigned
            </SelectItem>
            {(staff ?? []).map((user) => (
              <SelectItem
                key={user.id}
                id={String(user.id)}
                textValue={user.display_name}
              >
                {user.display_name}
              </SelectItem>
            ))}
          </Select>
        </fieldset>

        <WardStaffStatus
          staff={staff}
          staffError={staffError}
          onRetryStaff={reloadStaff}
        />

        {saveError !== null ? (
          <p className={noticeClass.error} role="alert">
            {saveError}
          </p>
        ) : null}

        <footer>
          <Button type="submit" className="min-h-11" disabled={saving}>
            {saving ? "Saving…" : "Raise task"}
          </Button>
        </footer>
      </form>

      <section className="flex flex-col gap-3">
        <h4 className={sectionLabelClass}>Recorded tasks</h4>
        <p className="text-body-2-regular text-text-secondary">
          Open and done Tasks together, so marking one done removes it from the
          open lists but keeps it in the record.
        </p>

        {loadError !== null ? (
          <p className={noticeClass.error} role="alert">
            {loadError}
          </p>
        ) : null}

        {tasks === null ? (
          loadError !== null ? null : (
            <p className={mutedTextClass}>Loading tasks…</p>
          )
        ) : tasks.length === 0 ? (
          <p className={mutedTextClass}>No tasks recorded for this patient yet.</p>
        ) : (
          <ol className="flex flex-col gap-4">
            {tasks.map((task) => (
              <TaskItem
                key={task.id}
                task={task}
                staff={staff}
                showPatient={false}
                onChanged={async () => {
                  await load(admissionId);
                  await onTasksChanged();
                }}
              />
            ))}
          </ol>
        )}
      </section>
    </section>
  );
}

interface TaskDraft {
  key: number;
  description: string;
  dueAt: string;
  assignee: string;
}

/**
 * Raise several Tasks from one saved Ward Round Entry, because a round gives
 * several instructions in one conversation and a single-task-at-a-time form
 * turns that into several submissions. The form sits on the saved note itself
 * rather than in a standalone draft, so the Tasks are plainly attached to the
 * entry that raised them, and it belongs to the Admission on that note.
 */
export function WardRoundTasks({
  admissionId,
  noteId,
  seedDescription = "",
  dueHint = "",
  onTasksRaised,
}: {
  /** The Admission on the note the Tasks belong to. */
  admissionId: number;
  /** The saved Ward Round Entry the Tasks are raised from. */
  noteId: number;
  /** A first description to offer, typically the entry's plan field. */
  seedDescription?: string;
  /** The entry's own due hint (free text), shown beside the due field. */
  dueHint?: string;
  /** Called after Tasks are raised, so the board's counts refresh. */
  onTasksRaised?: () => Promise<void> | void;
}) {
  const { staff, staffError, reloadStaff } = useWardStaff();

  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<TaskDraft[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const seqRef = useRef(0);
  const newDraft = useCallback((description: string): TaskDraft => {
    seqRef.current += 1;
    return {
      key: seqRef.current,
      description,
      dueAt: "",
      assignee: UNASSIGNED,
    };
  }, []);

  function openForm() {
    setError(null);
    setRows((current) =>
      current.length > 0 ? current : [newDraft(seedDescription)],
    );
    setOpen(true);
  }

  function closeForm() {
    setRows([]);
    setError(null);
    setOpen(false);
  }

  function updateRow(key: number, patch: Partial<TaskDraft>) {
    setRows((current) =>
      current.map((row) => (row.key === key ? { ...row, ...patch } : row)),
    );
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payloads: NewTaskPayload[] = [];
    for (const row of rows) {
      const trimmed = row.description.trim();
      if (!trimmed) {
        continue;
      }
      let due: string | null = null;
      if (row.dueAt !== "") {
        const parsed = new Date(row.dueAt);
        if (Number.isNaN(parsed.getTime())) {
          setError("Enter valid due times, or leave them blank.");
          return;
        }
        due = parsed.toISOString();
      }
      payloads.push({
        description: trimmed,
        due_at: due,
        assignee_user_id: row.assignee === UNASSIGNED ? null : Number(row.assignee),
      });
    }
    if (payloads.length === 0) {
      setError("Add at least one task with a description.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createWardRoundTasks(admissionId, noteId, payloads);
      toast.success(
        payloads.length === 1
          ? "Task raised from the round entry."
          : `${payloads.length} tasks raised from the round entry.`,
      );
      setRows([]);
      setOpen(false);
      await onTasksRaised?.();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <footer className="flex flex-wrap items-center gap-2">
        <Button
          variant={open ? "primary" : "secondary"}
          className="min-h-11"
          onClick={open ? closeForm : openForm}
        >
          {open ? "Cancel" : "Raise tasks from this entry"}
        </Button>
        <small className="text-body-2-regular text-text-secondary">
          Raises one Task per instruction, each against this patient.
        </small>
      </footer>

      {open ? (
        <form className="flex flex-col gap-4" onSubmit={save}>
          <p className={mutedTextClass}>
            A round gives several instructions at once, so add a row per
            instruction. Each Task belongs to this patient and names this entry as
            where it came from.
          </p>

          <ul className="flex flex-col gap-3">
            {rows.map((row, index) => (
              <li key={row.key}>
                <fieldset className="flex flex-col gap-3 rounded-3xl border border-border-button-default p-4">
                  <legend className={sectionLabelClass}>Task {index + 1}</legend>
                  <Textarea
                    rows={2}
                    label="Description"
                    value={row.description}
                    isDisabled={saving}
                    onChange={(next) => updateRow(row.key, { description: next })}
                  />
                  <Input
                    label="Due (optional)"
                    hint={
                      dueHint !== ""
                        ? `The entry says review due: ${dueHint}`
                        : undefined
                    }
                    type="datetime-local"
                    value={row.dueAt}
                    isDisabled={saving}
                    onChange={(next) => updateRow(row.key, { dueAt: next })}
                  />
                  <Select
                    label="Assign to (optional)"
                    className="w-full"
                    triggerClassName="min-h-11"
                    placeholder="Unassigned"
                    selectedKey={row.assignee}
                    isDisabled={saving || !staffReady(staff)}
                    onSelectionChange={(key) => {
                      if (typeof key === "string") {
                        updateRow(row.key, { assignee: key });
                      }
                    }}
                  >
                    <SelectItem id={UNASSIGNED} textValue="Unassigned">
                      Unassigned
                    </SelectItem>
                    {(staff ?? []).map((user) => (
                      <SelectItem
                        key={user.id}
                        id={String(user.id)}
                        textValue={user.display_name}
                      >
                        {user.display_name}
                      </SelectItem>
                    ))}
                  </Select>
                  {rows.length > 1 ? (
                    <footer>
                      <Button
                        variant="secondary"
                        className="min-h-11"
                        disabled={saving}
                        onClick={() =>
                          setRows((current) =>
                            current.filter((item) => item.key !== row.key),
                          )
                        }
                      >
                        Remove this task
                      </Button>
                    </footer>
                  ) : null}
                </fieldset>
              </li>
            ))}
          </ul>

          <WardStaffStatus
            staff={staff}
            staffError={staffError}
            onRetryStaff={reloadStaff}
          />

          {error !== null ? (
            <p className={noticeClass.error} role="alert">
              {error}
            </p>
          ) : null}

          <footer className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              className="min-h-11"
              disabled={saving}
              onClick={() => setRows((current) => [...current, newDraft("")])}
            >
              Add another task
            </Button>
            <Button type="submit" className="min-h-11" disabled={saving}>
              {saving ? "Saving…" : "Raise tasks"}
            </Button>
          </footer>
        </form>
      ) : null}
    </section>
  );
}

/**
 * One Task in a list: who it is for and where, the description as given, the due
 * state (a time or none), the assignee (a person or none) and the overdue mark —
 * then, for an open Task, the two actions a person takes: mark it done, or assign
 * it. Nothing here decides; both actions are explicit and go to the server.
 */
function TaskItem({
  task,
  staff,
  location,
  showPatient = true,
  onChanged,
}: {
  task: Task;
  /** The ward's staff, or null while it loads; the assign control waits (and
   *  says why, through the container's `WardStaffStatus`) until the list is ready. */
  staff: TaskPerson[] | null;
  /** Where the patient is, when the board knows it. */
  location?: string;
  /** Show the patient's name; off inside a single patient's own record. */
  showPatient?: boolean;
  onChanged: () => Promise<void> | void;
}) {
  const [saving, setSaving] = useState(false);

  const isOpen = task.status === "open";

  async function complete() {
    setSaving(true);
    try {
      await api.completeTask(task.id);
      toast.success("Task marked done.");
      await onChanged();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  async function assign(key: string | number | null) {
    const next = key === null || key === UNASSIGNED ? null : Number(key);
    if ((task.assignee?.id ?? null) === next) {
      return;
    }
    setSaving(true);
    try {
      await api.assignTask(task.id, next);
      toast.success(next === null ? "Task unassigned." : "Task assigned.");
      await onChanged();
    } catch (caught) {
      toast.error(errorText(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className={cx(cardClass, "gap-2")}>
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {showPatient ? (
          <h5 className="text-body-semibold text-text-primary">
            {task.patient.full_name}
          </h5>
        ) : null}
        {location !== undefined ? (
          <Chip variant="caption" color="soft">
            {location}
          </Chip>
        ) : null}
        {task.overdue ? (
          <Chip variant="bold" color="rose">
            overdue
          </Chip>
        ) : null}
        {task.status === "done" ? (
          <Chip variant="bold" color="lime">
            done
          </Chip>
        ) : null}
        {task.note_id !== null ? (
          <Chip variant="caption" color="neutral">
            from ward round entry #{task.note_id}
          </Chip>
        ) : null}
      </header>

      <p className="text-body-regular text-text-primary wrap-anywhere">
        {task.description}
      </p>

      <p className="text-body-2-regular text-text-secondary">
        {task.due_at !== null ? (
          <>
            Due{" "}
            <time dateTime={task.due_at} className={figureClass}>
              {formatInstant(task.due_at)}
            </time>
          </>
        ) : (
          "No due time"
        )}
        {" · "}
        {task.assignee !== null ? (
          <>
            Assigned to <bdi>{task.assignee.display_name}</bdi>
          </>
        ) : (
          "Unassigned"
        )}
        {" · raised by "}
        <bdi>{task.author.display_name}</bdi>
      </p>

      {task.status === "done" ? (
        <p className="text-body-2-regular text-text-secondary">
          Marked done
          {task.completed_by !== null ? (
            <>
              {" by "}
              <bdi>{task.completed_by.display_name}</bdi>
            </>
          ) : null}
          {task.completed_at !== null ? (
            <>
              {" "}
              <time dateTime={task.completed_at} className={figureClass}>
                {formatInstant(task.completed_at)}
              </time>
            </>
          ) : null}
          .
        </p>
      ) : null}

      {isOpen ? (
        <footer className="flex flex-wrap items-end gap-2">
          <Button
            variant="secondary"
            className="min-h-11"
            disabled={saving}
            onClick={() => void complete()}
          >
            {saving ? "Working…" : "Mark done"}
          </Button>
          <Select
            label="Assign to"
            className="w-full sm:w-64"
            triggerClassName="min-h-11"
            selectedKey={task.assignee !== null ? String(task.assignee.id) : UNASSIGNED}
            isDisabled={saving || !staffReady(staff)}
            onSelectionChange={(key) => {
              void assign(key);
            }}
          >
            <SelectItem id={UNASSIGNED} textValue="Unassigned">
              Unassigned
            </SelectItem>
            {(staff ?? []).map((user) => (
              <SelectItem
                key={user.id}
                id={String(user.id)}
                textValue={user.display_name}
              >
                {user.display_name}
              </SelectItem>
            ))}
          </Select>
        </footer>
      ) : null}
    </li>
  );
}
