import { useState } from "react";
import type { ExecutionResult } from "../types";
import Panel from "./Panel";

function color(outcome: string) {
  switch (outcome) {
    case "passed":
      return "text-ok";
    case "failed":
    case "error":
      return "text-bad";
    default:
      return "text-warn";
  }
}

export default function TestResults({ results }: { results?: ExecutionResult }) {
  const [showOutput, setShowOutput] = useState(false);
  if (!results || !results.cases) return <Panel title="Test Execution">Tests have not run yet.</Panel>;

  const stats = [
    { label: "Passed", value: results.passed, cls: "text-ok" },
    { label: "Failed", value: results.failed, cls: "text-bad" },
    { label: "Errors", value: results.error, cls: "text-bad" },
    { label: "Skipped", value: results.skipped, cls: "text-warn" },
  ];
  const green = results.failed === 0 && results.error === 0;

  return (
    <Panel
      title="Test Execution"
      badge={
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${green ? "bg-ok/15 text-ok" : "bg-bad/15 text-bad"}`}>
          {green ? "ALL GREEN" : "FAILING"}
        </span>
      }
    >
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-lg border border-line bg-panel-2 p-3 text-center">
            <div className={`text-2xl font-bold ${s.cls}`}>{s.value}</div>
            <div className="text-[11px] uppercase tracking-wide text-faint">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="max-h-72 overflow-y-auto rounded-lg border border-line">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-panel-2 text-faint">
            <tr>
              <th className="px-3 py-2">Test</th>
              <th className="px-3 py-2">Outcome</th>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {results.cases.map((c, i) => (
              <tr key={i} className="hover:bg-panel-2/60">
                <td className="mono px-3 py-1.5">{c.name}</td>
                <td className={`px-3 py-1.5 font-medium ${color(c.outcome)}`}>{c.outcome}</td>
                <td className="px-3 py-1.5 text-faint">{c.duration_ms != null ? `${c.duration_ms}ms` : "—"}</td>
                <td className="max-w-xs truncate px-3 py-1.5 text-faint">{c.description || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {results.output && (
        <div className="mt-3">
          <button
            onClick={() => setShowOutput((v) => !v)}
            className="mb-2 text-xs font-medium text-brand hover:underline"
          >
            {showOutput ? "Hide" : "Show"} pytest output{" "}
            <span className="text-faint">({results.duration_ms}ms total)</span>
          </button>
          {showOutput && (
            <pre className="mono max-h-64 overflow-auto rounded-lg border border-line bg-ink p-3 text-xs whitespace-pre-wrap">
              {results.output}
            </pre>
          )}
        </div>
      )}
    </Panel>
  );
}