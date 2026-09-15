import { useMemo, useState } from "react";
import Panel from "./Panel";

export default function FilesPanel({ files }: { files?: Record<string, string> }) {
  const [selected, setSelected] = useState<string | null>(null);
  const entries = useMemo(() => (files ? Object.entries(files).sort(([a], [b]) => a.localeCompare(b)) : []), [files]);
  const active = selected ?? entries[0]?.[0] ?? null;
  const content = files?.[active ?? ""] ?? "";

  if (!entries.length) return <Panel title="Generated Files">No files generated yet.</Panel>;

  return (
    <Panel title="Generated Files" badge={<span className="text-xs text-faint">{entries.length} files</span>}>
      <div className="grid gap-3 lg:grid-cols-[220px_1fr]">
        <ul className="max-h-96 divide-y divide-line overflow-y-auto rounded-lg border border-line">
          {entries.map(([path, body]) => (
            <li key={path}>
              <button
                onClick={() => setSelected(path)}
                className={`mono w-full truncate px-3 py-1.5 text-left text-xs ${
                  active === path ? "bg-brand/20 text-ice" : "text-faint hover:bg-panel-2 hover:text-ice"
                }`}
              >
                {path}
                <span className="ml-2 text-[10px] text-faint">{body.split("\n").length} lines</span>
              </button>
            </li>
          ))}
        </ul>
        <pre className="mono max-h-[28rem] overflow-auto rounded-lg border border-line bg-ink p-3 text-xs leading-relaxed">
          <code>{content}</code>
        </pre>
      </div>
    </Panel>
  );
}