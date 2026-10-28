import { useState } from "react";
import {
  Button,
  Card,
  CardHeader,
  Field,
  IconButton,
  Input,
  Pill,
  Select,
  Slider,
  StatusDot,
  Switch,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from "@charie/shared";
import {
  CircleAlert,
  Database,
  Eye,
  Layers,
  Lock,
  PanelLeft,
  SquarePen,
  X,
} from "lucide-react";
import KitSection from "./KitSection";

const THINKING_OPTIONS = [
  { value: "short", label: "Short" },
  { value: "normal", label: "Normal" },
  { value: "detailed", label: "Detailed" },
];

export default function BasicBlocksSection() {
  const [thinking, setThinking] = useState("normal");
  return (
    <KitSection id="basic-blocks" title="Building blocks 1">
      <div className="flex flex-wrap gap-2">
        {(["primary", "soft", "outline", "ghost", "danger"] as const).map((variant) =>
          (["sm", "md", "lg"] as const).map((size) => (
            <Button key={`${variant}-${size}`} variant={variant} size={size}>
              {variant === "primary" && size === "md" ? (
                <>
                  <SquarePen aria-hidden="true" />
                  Ask
                </>
              ) : (
                `${variant} ${size}`
              )}
            </Button>
          )),
        )}
        <Button disabled>Disabled</Button>
      </div>
      <div className="mt-4 flex gap-2">
        <IconButton label="Hide sidebar">
          <PanelLeft />
        </IconButton>
        <IconButton label="Forget this">
          <X />
        </IconButton>
      </div>
      <Card padded className="mt-4">
        <CardHeader title="Cost per day" sub="October, in US dollars" />
        <p className="stat-value">$41.20</p>
      </Card>
      <div className="mt-4 grid max-w-[420px] gap-3">
        <Field
          label="Password"
          htmlFor="kit-password"
          hint="Stored safely and never shown again."
        >
          <Input
            id="kit-password"
            type="password"
            icon={Lock}
            placeholder="Enter the password"
            end={
              <IconButton label="Show password">
                <Eye />
              </IconButton>
            }
          />
        </Field>
        <Field label="Password check" htmlFor="kit-password-bad" error="That password didn't work. Try again.">
          <Input id="kit-password-bad" type="password" aria-invalid="true" defaultValue="nope" />
        </Field>
        <Field label="Disabled" htmlFor="kit-disabled">
          <Input id="kit-disabled" disabled placeholder="You cannot type here" />
        </Field>
        <Field label="Notes" htmlFor="kit-notes">
          <Textarea id="kit-notes" placeholder="For example: sales should not include delivery fees" />
        </Field>
        <Field label="Thinking time" htmlFor="kit-thinking">
          <Select
            id="kit-thinking"
            options={THINKING_OPTIONS}
            value={thinking}
            onValueChange={setThinking}
            placeholder="Thinking time"
          />
        </Field>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Pill tone="good">
          <StatusDot tone="good" />
          Connected
        </Pill>
        <Pill tone="accent" icon={Layers}>
          Version 14 · 26 Oct
        </Pill>
        <Pill tone="warn" icon={Database}>
          Data
        </Pill>
        <Pill tone="bad" icon={CircleAlert}>
          2 pages unreadable
        </Pill>
        <Pill tone="outline">Affects every sales number</Pill>
      </div>
      <Tabs defaultValue="waiting" className="mt-4">
        <TabsList aria-label="Questions">
          <TabsTrigger value="waiting" count={3}>
            Waiting
          </TabsTrigger>
          <TabsTrigger value="answered" count={12}>
            Answered
          </TabsTrigger>
          <TabsTrigger value="skipped" count={2}>
            Skipped
          </TabsTrigger>
        </TabsList>
        <TabsContent value="waiting">Waiting list</TabsContent>
        <TabsContent value="answered">Answered list</TabsContent>
        <TabsContent value="skipped">Skipped list</TabsContent>
      </Tabs>
      <div className="mt-4 flex flex-col gap-2">
        <label className="flex items-center gap-2 text-sm text-text-2">
          <Switch defaultChecked aria-label="Remember on" />
          Remember things I tell Charie
        </label>
        <label className="flex items-center gap-2 text-sm text-text-2">
          <Switch aria-label="Remember off" />
          Remember things I tell Charie
        </label>
        <label className="flex items-center gap-2 text-sm text-text-2">
          <Switch disabled aria-label="Remember disabled" />
          Remember things I tell Charie
        </label>
      </div>
      <div className="mt-4 max-w-[320px]">
        <p className="field-label">10 minutes</p>
        <Slider aria-label="10 minutes" defaultValue={10} min={2} max={15} step={1} />
      </div>
    </KitSection>
  );
}
