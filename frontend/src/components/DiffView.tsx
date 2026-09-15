import type { DiffEntry } from "../types";
import Panel from "./Panel";

function DiffLine({ text }: { text: string }) {
  const cls = text.startsWith("+")
    ? "bg-ok/10 text-ok"
    : text.startsWith("-")
      ? "bg-bad/10 text-bad"
      : text.startsWith("@@")
        ? "bg-brand/20 text-brand"
        : "text-faint";
  return (
    <div className={`mono whitespace-pre px-3 text-xs leading-relaxed ${cls}`}>{text || " "}</div>
  );
}

export default function DiffView({ diffs }: { diffs?: DiffEntry[] }) {
  if (!diffs || !diffs.length) return <Panel title="Corrections">No corrections applied.</Panel>;

  return (
    <Panel title="Corrections (diff)" badge={<span className="text-xs text-faint">{diffs.length} patch(es)</span>}>
      <div className="space-y-4">
        {diffs.map((d, i) => (
          <div key={i} className="overflow-hidden rounded-lg border border-line">
            <div className="flex items-center justify-between gap-2 border-b border-line bg-panel-2 px-3 py-2">
              <span className="mono text-xs font-semibold text-ice">{d.path}</span>
              <span className="text-[11px] text-faint">{d.applied_at}</span>
            </div>
            <div className="max-h-80 overflow-auto">
              {d.diff
                .split("\n")
                .filter((l) => !l.startsWith("\\"))
                .map((l, j) => (
                  <DiffLine key={j} text={l} />
                ))}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}