import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  ChoiceCard,
  ChoiceGroup,
  DataTable,
  Dropzone,
  IconBox,
  StatCard,
  toast,
} from "@charie/shared";
import {
  Check,
  CircleAlert,
  CircleHelp,
  Database,
  MessageSquare,
} from "lucide-react";
import KitSection from "./KitSection";

interface ExpensiveQuestion {
  question: string;
  date: string;
  thinking: string;
  steps: number;
  cost: string;
}

const QUESTIONS_COLUMNS: ColumnDef<ExpensiveQuestion>[] = [
  {
    header: "Question",
    accessorKey: "question",
    cell: (info) => (
      <span>
        {info.row.original.question}
        <small className="block text-muted">{info.row.original.date}</small>
      </span>
    ),
  },
  { header: "Thinking time", accessorKey: "thinking" },
  { header: "AI steps", accessorKey: "steps", meta: { numeric: true } },
  {
    header: "Cost",
    accessorKey: "cost",
    meta: { numeric: true },
    cell: (info) => <b>{info.row.original.cost}</b>,
  },
];

const QUESTIONS_ROWS: ExpensiveQuestion[] = [
  { question: "Why did delivery drop in Austin?", date: "26 Oct", thinking: "6 min 12 s", steps: 41, cost: "$3.84" },
  { question: "Dallas vs Houston, last quarter", date: "22 Oct", thinking: "4 min 5 s", steps: 33, cost: "$2.96" },
  { question: "Coupon impact in September", date: "19 Oct", thinking: "3 min 18 s", steps: 27, cost: "$2.61" },
  { question: "Best hours to add staff", date: "21 Oct", thinking: "2 min 40 s", steps: 22, cost: "$2.18" },
  { question: "How are we doing this month?", date: "27 Oct", thinking: "38 s", steps: 14, cost: "$1.92" },
];

export default function CompositeBlocksSection() {
  const [meaning, setMeaning] = useState("with-fees");
  return (
    <KitSection id="composite-blocks" title="Building blocks 3">
      <ChoiceGroup aria-label='What should "sales" mean by default?' value={meaning} onValueChange={setMeaning}>
        <ChoiceCard
          value="with-fees"
          title="Including delivery fees"
          sub="Matches the Finance wiki"
          num="$1.42M"
        />
        <ChoiceCard
          value="without-fees"
          title="Without delivery fees"
          sub="Matches the Ops handbook"
          num="$1.31M"
        />
        <ChoiceCard
          value="ask"
          title="Ask me each time"
          sub="Charie shows both numbers when it's unclear"
        />
      </ChoiceGroup>
      <div className="mt-4 grid gap-[14px] min-[1000px]:grid-cols-4 grid-cols-2">
        <StatCard label="Spent this month" value="$41.20" foot="1–27 Oct" />
        <StatCard label="Questions answered" value="24" foot="About $1.31 each" />
        <StatCard label="Learning runs" value="2" foot="$9.80 in total" />
        <StatCard label="Expected by 31 Oct" value="$47" foot="Well within the credit" />
      </div>
      <div className="mt-4 flex items-center gap-2">
        <IconBox icon={Database} tone="accent" />
        <IconBox icon={Check} tone="good" />
        <IconBox icon={CircleHelp} tone="warn" />
        <IconBox icon={CircleAlert} tone="bad" />
        <IconBox icon={MessageSquare} tone="plain" />
        <IconBox icon={Database} tone="accent" size={46} />
      </div>
      <div className="mt-4 max-w-[520px]">
        <Dropzone
          onFiles={(files) =>
            toast(`Picked ${files.length} ${files.length === 1 ? "file" : "files"}.`)
          }
        />
      </div>
      <div className="mt-4">
        <DataTable columns={QUESTIONS_COLUMNS} data={QUESTIONS_ROWS} caption="Most expensive questions" />
      </div>
      <div className="mt-4">
        <DataTable
          columns={QUESTIONS_COLUMNS}
          data={[]}
          empty="No documents yet. Drop files here to start."
          caption="Documents"
        />
      </div>
    </KitSection>
  );
}
