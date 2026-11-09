# BoardUI usage examples (fetched from the read-only MCP catalogue, 2026-11-05)

Installed component source lives under frontend/components/. These examples are from the registry; the local source is authoritative if they disagree.

<!-- ============================== adoption decisions (2026-11-05) ============================== -->

## Brand layer (2026-11-05, unslop pass)

**`styles/brand.css` is the one re-tint point.** Imported after `typography.css` in `globals.css`; it re-points the accent ramp (deep teal, interactive stops one step darker so white-on-primary clears 4.5:1), the primary-button gradient stops, the page surfaces (`background-full` → cool graphite `#f1f4f8`, white cards over it) and both font families (IBM Plex Sans variable, IBM Plex Mono) onto `:root`. Components keep using semantic tokens only — no hex, no raw palette classes in components. Dark mode is untouched (unused in this app).

**Urgency colour is data colour, not chrome.** Urgency chips were demoted everywhere: queue cards carry the triage band (left border) plus the level name in `urgencyTextClass`; tables use the same quiet coloured text; Override (orange) and Unclassified (purple) chips remain because they are flags. `urgencyChipColor` was replaced by `urgencyTextClass` in `queueDisplay.ts`. The logo mark (`src/brand.tsx` `LogoMark`) is three flat triage bands — the only urgency colour in the chrome.

**AuthCard placeholders (installed copy, `auth-card.tsx`).** `you@company.com` → `name@example.com`; the signin password placeholder removed (empty). Same spirit as the earlier `showRememberMe`/`showForgotPassword`/`showSwitch` extension: registry behaviour for signin is otherwise unchanged.

**Shared class vocabulary moved to `design.ts`.** `sectionLabelClass` is sentence case (`text-caption-1-medium text-text-tertiary`, no uppercase, no tracking); `figureClass` adds the mono/tabular instrument treatment for waiting times, vitals and report figures; card gap bumped to `gap-5`. Report tables remain token-styled native tables (decision above unchanged).

**UI copy sentence-cases the domain nouns** (encounter, patient, machine recommendation, …). CONTEXT.md's capitalised terms remain the docs convention; the interface no longer shouts them.

## Decisions recorded during the frontend migration

**Legacy CSS retired.** `frontend/src/styles.css` is deleted; `main.tsx` imports only `@/styles/globals.css`. The shared class vocabulary lives in `frontend/src/design.ts` (card, inline notices, table primitives) and `frontend/src/queueDisplay.ts` (urgency mapping).

**Report tables are token-styled native tables, not the React Aria `table`.** The dashboard and Reports tables are read-only server figures with `scope="row"` headers and explanatory captions; none of them select, sort, or page, which is what `table`/`data-table` add. Converting eight dense statistical tables to React Aria collection components would buy no interaction and risk the careful a11y semantics, so they are styled with the shared primitives in `design.ts` instead. Revisit if sorting or selection is ever wanted.

**Urgency colours.** High → `rose`, Medium → `yellow`, Low → `lime` (chips), with the matching `status-*-text` tone as the queue card's left border. Medium is deliberately *yellow*, not orange — orange is the Override flag's colour, and the two appear together on the same card. Unclassified → `purple`; the accuracy matrix's correct diagonal → lime background; "needs review" inline warnings use the same purple family as the Unclassified flag.

**AuthCard source extended (installed copy, `auth-card.tsx`).** Added opt-in `showRememberMe`, `showForgotPassword`, `showSwitch` props (all default `true`, so registry behaviour is unchanged). TriageAssist has no password reset or self-service sign-up, and the old hardcoded controls advertised features the system does not have.

**Clinical view switcher uses `segmented-control`.** The previous button pair read backwards (the pressed view rendered as a plain `secondary` button while the unpressed one got the accent-tinted `ghost`). The registry's segmented control carries the selected state properly and exposes a real radiogroup.

**Inline notices stay plain paragraphs** (`role="status"` + `noticeClass` tokens). The BoardUI `Notification` card is built for toast stacks (dismiss, countdown, motion) and is too heavy for inline API errors and report caveats. Toasts are used only where the flow already had them (intake success/failure).


<!-- ============================== auth-card ============================== -->

# Auth Card

Sign-in and sign-up cards with social providers stacked with labels or inline as icons, plus email fields and a CTA.

## Dependencies

- npm: `@remixicon/react@^4.9.0`
- BoardUI items (installed): `button`, `checkbox`, `cx`, `direction`, `divider`, `input`, `input-otp`, `link-button`, `social-button`, `template-copy`

## Usage

```tsx
import { AuthCard } from "@/components/application/auth/auth-card";

export function Example() {
  return (
    <AuthCard
      mode="signin"
      layout="stacked"
      providers={[]}
      onSubmit={(data) => signIn("credentials", Object.fromEntries(data))}
    />
  );
}
```

- `providers={[]}` gives email-only; the divider disappears.
- `logo` takes a node; `title` and `description` customise the header; `centered` centres the header.
- Modes: `signin`, `signup`, `verify`.
- Split layout: `media={<AuthMediaCarousel slides={[...]} />}` or any node.

<!-- ============================== button ============================== -->

# Button

Primary, secondary, ghost, and danger buttons in three sizes with icon support.

```tsx
import { RiArrowRightLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";

<Button>Get started</Button>
<Button variant="secondary" trailingIcon={RiArrowRightLine}>Continue</Button>
<Button variant="ghost">Mark as done</Button>
<Button variant="danger">Delete</Button>
<Button size="small">Small</Button>   {/* 32px */}
<Button size="xs">Xs</Button>         {/* 24px */}
<Button leadingIcon={RiAddLine}>New project</Button>
<Button iconOnly leadingIcon={RiAddLine} aria-label="Add" />
```

<!-- ============================== input ============================== -->

# Input

Text input with label, hint text, error states, and leading icon support.

```tsx
import { Input } from "@/components/base/input/input";

<Input
  label="Email"
  type="email"
  isRequired
  placeholder="Enter your email"
  hint="This is a hint about this input."
  errorMessage="Enter a valid email address."
  leadingIcon={RiUserSmileLine}
/>
```

- Sizes: `medium` (36px, default), `small` (32px).
- `isDisabled`, `isInvalid` repaint field/hint/label. `errorMessage` replaces the hint while invalid.
- Controlled: `value` + `onChange` (React Aria; onChange receives the string).
- `type="number"` works; with `validationBehavior="aria"` the form always submits and `isInvalid` is yours.
- Phone pattern: a Select in `leadingAddon`.

<!-- ============================== textarea ============================== -->

# Textarea

```tsx
import { Textarea } from "@/components/base/textarea/textarea";

<Textarea label="Release notes" isRequired placeholder="What changed?" hint="Markdown is supported." rows={4} />
<Textarea label="Message" autoResize rows={2} maxRows={8} />
<Textarea label="Bio" value={bio} onChange={setBio} hint="Appears on your profile." maxLength={160} showCount />
<Textarea label="Cover letter" isInvalid hint="Please write at least 200 characters." />
```

<!-- ============================== select ============================== -->

# Select

React Aria select with styled trigger, non-modal popover, and free-form item content.

```tsx
import { Select, SelectItem } from "@/components/base/select/select";

<Select label="Role" placeholder="Select a role" className="w-[240px]">
  <SelectItem id="admin" textValue="Admin">Admin</SelectItem>
  <SelectItem id="editor" textValue="Editor">Editor</SelectItem>
  <SelectItem id="viewer" textValue="Viewer">Viewer</SelectItem>
</Select>

import { StatusDot } from "@/components/base/badges/status-dot";

<Select aria-label="Purchase status" defaultSelectedKey="completed" className="w-[142px]">
  <SelectItem id="completed" textValue="Completed"><StatusDot color="green" />Completed</SelectItem>
  <SelectItem id="waiting" textValue="Waiting"><StatusDot color="yellow" />Waiting</SelectItem>
</Select>
```

<!-- ============================== checkbox ============================== -->

# Checkbox

```tsx
import { Checkbox } from "@/components/base/checkbox/checkbox";

<Checkbox defaultSelected>Remember me</Checkbox>
<Checkbox isSelected={checked} onChange={setChecked}>Terms</Checkbox>
```

<!-- ============================== badge / chip / status-dot ============================== -->

```tsx
import { Badge } from "@/components/base/badges/badge";
import { Chip } from "@/components/base/badges/chip";
import { StatusDot } from "@/components/base/badges/status-dot";

<Badge color="neutral">91</Badge>
<Badge color="primary">152</Badge>
<Chip variant="bold" color="lime">Active</Chip>      {/* statuses, deltas */}
<Chip variant="subtle" color="cyan">$3.252</Chip>    {/* values */}
<Chip variant="caption" color="rose">Designer</Chip> {/* tags */}
<StatusDot color="green" /> <StatusDot color="yellow" /> <StatusDot color="indigo" />
```

Chip colors are accent-palette names (lime, rose, cyan, orange, blue, etc. — check chip.tsx source).

<!-- ============================== modal ============================== -->

# Modal

```tsx
import { Button } from "@/components/base/buttons/button";
import { Modal, ModalBody, ModalFooter, ModalHeader, ModalTrigger } from "@/components/base/modal/modal";

<ModalTrigger>
  <Button leadingIcon={RiUserAddLine}>Invite teammates</Button>
  <Modal>
    {({ close }) => (
      <>
        <ModalHeader title="Invite teammates" description="They get an email with a link." />
        <ModalBody>
          <form id="invite-form" className="flex flex-col gap-4" onSubmit={(event) => { event.preventDefault(); close(); }}>
            <Input label="Email address" type="email" placeholder="name@company.com" isRequired />
          </form>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={close}>Cancel</Button>
          <Button type="submit" form="invite-form">Send invite</Button>
        </ModalFooter>
      </>
    )}
  </Modal>
</ModalTrigger>
```

Alert dialog (destructive confirm):

```tsx
import { AlertDialog, ModalTrigger } from "@/components/base/modal/modal";

<ModalTrigger>
  <Button variant="danger" leadingIcon={RiDeleteBinLine}>Delete project</Button>
  <AlertDialog
    title="Delete project?"
    description="You can't undo this."
    confirmLabel="Delete project"
    pendingLabel="Deleting..."
    onConfirm={() => deleteProject(projectId)} // return the promise to keep it open until done
  />
</ModalTrigger>
```

<!-- ============================== tabs ============================== -->

# Tabs

```tsx
import { Tab, TabList, TabPanel, Tabs } from "@/components/base/tabs/tabs";

<Tabs defaultSelectedKey="banners">
  <TabList aria-label="Content types">
    <Tab id="banners" icon={RiImage2Line} count={152}>Banners</Tab>
    <Tab id="settings">Settings</Tab>
  </TabList>
  <TabPanel id="banners" />
  <TabPanel id="posts" />
</Tabs>
```

<!-- ============================== data-table ============================== -->

# Data Table

TanStack-powered table with sorting, selection, pagination. Installed source: `components/application/data-table/data-table.tsx` (exports `DataTableExample` plus the built-up pieces). For real data, build columns with TanStack and render with the base `table` primitives (`components/base/table/table.tsx`), or adapt the example's wiring.

<!-- ============================== stat-cards ============================== -->

# Stat Cards

```tsx
import { StatCards, type Stat } from "@/components/application/dashboard/stat-cards";
import { RiCoinsFill } from "@remixicon/react";

const stats: Stat[] = [
  {
    icon: RiCoinsFill,
    label: "Total revenue",
    value: "$152,313.92",
    delta: "16%",
    deltaColor: "lime",   // lime | rose | neutral
    tone: "blue",         // icon tile tint (footer variant)
    caption: "From last month",
    hint: "Gross revenue across all channels.",
  },
];

<StatCards stats={stats} />                  {/* compact */}
<StatCards variant="footer" stats={stats} /> {/* footer band */}
```

<!-- ============================== patient-info-card ============================== -->

# Patient Info Card

Profile card with avatar and label/value detail rows. Installed source: `components/application/medical/patient-info-card.tsx`. Read its props from the source.

<!-- ============================== toast ============================== -->

# Toast

```tsx
// Once, near the root:
import { Toaster } from "@/components/base/toast/toast";
<Toaster />

// Anywhere:
import { toast } from "@/components/base/toast/toast";

toast.success("Changes saved", { description: "Your workspace settings are up to date." });
toast.error("Upload failed", { description: "Q3-report.pdf is larger than 20MB." });

const id = toast.info("Exporting", { duration: Infinity, dismissible: false });
toast.update(id, { title: "Export ready", status: "success", duration: 4000, dismissible: true });
```

<!-- ============================== tokens reminder ============================== -->

Style only with BoardUI semantic tokens: text-text-primary/-secondary/-tertiary/-placeholder, bg-background-full (page), bg-background-primary-default, bg-background-secondary-default/-hover, border-border-button-default, border-separator-border (hairlines), text-foreground-icon-*, accent ramp for CTAs. Type: composite utilities only (text-title-2-medium, text-headline-medium, text-body-medium, text-caption-1-semibold, ...). Merge classes with cx() from @/utils/cx. Cards/panels: rounded-3xl with border-border-button-default. Focus: outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring. No raw palette classes, no hex, no dark: overrides.
