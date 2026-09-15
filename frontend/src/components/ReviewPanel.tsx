import type { ReviewResult } from "../types";
import Panel from "./Panel";

const SEV: Record<string, string> = {
  critical: "bg-bad/15 text-bad",
  warning: "bg-warn/15 text-warn",
  info: "bg-brand/15 text-brand",
};

export default function ReviewPanel({ review }: { review?: ReviewResult }) {
  if (!review || review.score == null) return <Panel title="Code Review">Waiting for reviewer...</Panel>;

  return (
    <Panel
      title="Code Review"
      badge={
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
            review.passed ? "bg-ok/15 text-ok" : "bg-bad/15 text-bad"
          }`}
        >
          {review.passed ? "PASSED" : "NEEDS WORK"}
        </span>
      }
    >
      <div className="mb-3 flex items-center gap-3">
        <div className="relative h-16 w-16">
          <svg viewBox="0 0 36 36" className="h-16 w-16 -rotate-90">
            <circle cx="18" cy="18" r="16" fill="none" stroke="#22304a" strokeWidth="4" />
            <circle
              cx="18"
              cy="18"
              r="16"
              fill="none"
              stroke={review.score >= 80 ? "#34d399" : review.score >= 50 ? "#fbbf24" : "#f87171"}
              strokeWidth="4"
              strokeLinecap="round"
              strokeDasharray={`${(review.score / 100) * 100.5} 100.5`}
            />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-sm font-bold">
            {review.score}
          </span>
        </div>
        <p className="text-sm text-ice">{review.summary}</p>
      </div>

      {review.comments.length > 0 && (
        <ul className="space-y-2">
          {review.comments.map((c, i) => (
            <li key={i} className="flex gap-2 rounded-lg border border-line bg-panel-2 p-2 text-xs">
              <span className={`h-fit shrink-0 rounded px-1.5 py-0.5 font-semibold uppercase ${SEV[c.severity] ?? SEV.info}`}>
                {c.severity}
              </span>
              <span className="text-ice">
                {c.file && <code className="mono mr-1 text-faint">{c.file}</code>}
                {c.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}