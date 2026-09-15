import type { WorkflowStage } from "../types";

const STAGES: { key: WorkflowStage; label: string }[] = [
  { key: "planning", label: "Planning" },
  { key: "coding", label: "Coding" },
  { key: "testing", label: "Testing" },
  { key: "debugging", label: "Debugging" },
  { key: "reviewing", label: "Reviewing" },
  { key: "completed", label: "Completed" },
];

const ORDER: Record<string, number> = {
  planning: 0,
  coding: 1,
  testing: 2,
  debugging: 3,
  reviewing: 4,
  completed: 5,
  failed: 5,
};

export default function StatusTimeline({ status }: { status: string }) {
  const current = ORDER[status] ?? 0;
  return (
    <div className="flex items-center justify-between gap-1 rounded-xl border border-line bg-panel p-4">
      {STAGES.map((stage, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <div key={stage.key} className="flex flex-1 items-center gap-2 last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`h-3 w-3 rounded-full ${
                  done
                    ? "bg-ok"
                    : active
                      ? status === "debugging"
                        ? "animate-pulse bg-warn"
                        : "animate-pulse bg-brand"
                      : "bg-line"
                }`}
              />
              <span
                className={`text-[11px] font-medium ${
                  done ? "text-ok" : active ? "text-ice" : "text-faint"
                }`}
              >
                {stage.label}
              </span>
            </div>
            {i < STAGES.length - 1 && (
              <div className={`h-px flex-1 ${done ? "bg-ok" : "bg-line"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}