import { useCallback, useEffect, useRef, useState } from "react";
import { createProject, getProject, listProjects, projectEventsUrl, rerunProject, API_BASE } from "./api";
import type { ProjectListItem, ProjectState } from "./types";
import Panel from "./components/Panel";
import Markdown from "./components/Markdown";
import StatusTimeline from "./components/StatusTimeline";
import FilesPanel from "./components/FilesPanel";
import TestResults from "./components/TestResults";
import DiffView from "./components/DiffView";
import ReviewPanel from "./components/ReviewPanel";

const TABS = ["Overview", "Architecture", "Files", "Tests", "Fixes", "Review"] as const;
type Tab = (typeof TABS)[number];

export default function App() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [state, setState] = useState<ProjectState | null>(null);
  const [requirement, setRequirement] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("Overview");
  const [health, setHealth] = useState<{ provider: string; memory_backend: string } | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshList = useCallback(async () => {
    try {
      setProjects(await listProjects());
    } catch {
      /* backend not up yet */
    }
  }, []);

  useEffect(() => {
    void refreshList();
    fetch(`${API_BASE}/health`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setHealth)
      .catch(() => setHealth(null));
    return () => stopLive();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopLive = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  const startLive = useCallback((id: string) => {
    stopLive();
    // keep an SSE connection open - it wakes the backend and refreshes state on pings
    const es = new EventSource(projectEventsUrl(id));
    esRef.current = es;
    pollRef.current = setInterval(() => {
      void getProject(id).then(setState).catch(() => {});
    }, 2500);
  }, [stopLive]);

  const select = useCallback(
    (id: string) => {
      setSelected(id);
      setTab("Overview");
      void getProject(id).then(setState).catch(() => {});
      startLive(id);
    },
    [startLive]
  );

  const submit = useCallback(async () => {
    if (!requirement.trim() || busy) return;
    setBusy(true);
    try {
      const res = await createProject(requirement);
      await refreshList();
      select(res.project_id);
    } catch (err) {
      alert(`Failed to start: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }, [requirement, busy, refreshList, select]);

  const onRerun = useCallback(async () => {
    if (!selected) return;
    await rerunProject(selected);
    startLive(selected);
  }, [selected, startLive]);

  const running = selected && ["queued", "running", "planning", "coding", "testing", "debugging", "reviewing"].includes(state?.status ?? "");

  // keep the project list statuses in sync with the DB while something is running
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => void refreshList(), 5000);
    return () => clearInterval(id);
  }, [running, refreshList]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ice">Agentic Dev Assistant</h1>
          <p className="text-xs text-faint">
            Describe an idea in your own words and the assistant plans it, builds it, tests it, and reviews it.
            <span className="mono ml-2">
              {health
                ? health.provider === "openai"
                  ? "AI engine: online"
                  : "AI engine: demo mode"
                : "checking engine..."}
            </span>
          </p>
        </div>
        <button
          onClick={() => void refreshList()}
          className="rounded-lg border border-line px-3 py-1.5 text-xs text-faint hover:text-ice"
        >
          Refresh projects
        </button>
      </header>

      <Panel title="New Development Request" className="mb-6">
        <textarea
          value={requirement}
          onChange={(e) => setRequirement(e.target.value)}
          rows={2}
          className="w-full resize-none rounded-lg border border-line bg-ink p-3 text-sm text-ice outline-none focus:border-brand"
          placeholder="e.g. Build a CLI that converts temperatures between Celsius and Fahrenheit"
        />
        <div className="mt-3 flex items-center justify-between">
          <div className="text-[11px] text-faint">
            The assistant generates real code, runs the tests, fixes any failures, and gives you a review score.
          </div>
          <button
            onClick={() => void submit()}
            disabled={busy || !requirement.trim()}
            className="rounded-lg bg-brand px-5 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? "Starting..." : "Run Pipeline"}
          </button>
        </div>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
        {/* project list */}
        <Panel title="Projects" badge={<span className="text-xs text-faint">{projects.length}</span>} className="h-fit">
          {projects.length === 0 ? (
            <p className="text-sm text-faint">No runs yet. Submit a request to begin.</p>
          ) : (
            <ul className="space-y-2">
              {projects.map((p) => (
                <li key={p.project_id}>
                  <button
                    onClick={() => select(p.project_id)}
                    className={`w-full rounded-lg border p-3 text-left ${
                      selected === p.project_id ? "border-brand bg-brand/10" : "border-line bg-panel-2 hover:border-brand/50"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${
                          p.status === "completed"
                            ? "bg-ok"
                            : p.status === "failed"
                              ? "bg-bad"
                              : ["planning", "coding", "testing", "debugging", "reviewing", "running"].includes(p.status)
                                ? "animate-pulse bg-warn"
                                : "bg-line"
                        }`}
                      />
                      <span className="text-[10px] uppercase tracking-wide text-faint">{p.status}</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-ice">{p.requirement}</p>
                    <p className="mono mt-1 text-[10px] text-faint">{p.project_id.slice(0, 8)}…</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* main view */}
        <div className="min-w-0 space-y-4">
          {!selected || !state ? (
            <Panel title="Dashboard">
              <p className="text-sm text-faint">
                Select a project or start the pipeline. The dashboard streams live stage updates.
              </p>
            </Panel>
          ) : (
            <>
              <StatusTimeline status={state.status ?? "queued"} />

              {running && (
                <div className="rounded-lg border border-brand/40 bg-brand/10 px-4 py-2 text-xs text-brand animate-pulse">
                  Workflow in progress — planning, coding, testing, and reviewing your idea.
                </div>
              )}

              {/* tabs */}
              <div className="flex flex-wrap items-center gap-1 border-b border-line pb-2">
                {TABS.map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                      tab === t ? "bg-brand text-white" : "text-faint hover:text-ice"
                    }`}
                  >
                    {t}
                  </button>
                ))}
                <button
                  onClick={() => void onRerun()}
                  className="ml-auto rounded-lg border border-line px-3 py-1.5 text-xs text-faint hover:text-ice"
                >
                  Rerun
                </button>
              </div>

              <TabContent tab={tab} state={state} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function TabContent({ tab, state }: { tab: Tab; state: ProjectState }) {
  switch (tab) {
    case "Overview":
      return (
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Requirement">
            <p className="text-sm text-ice">{state.requirement}</p>
          </Panel>
          <Panel title="Development Summary" className={state.status === "failed" ? "border-bad/50" : ""}>
            {state.summary ? (
              <Markdown markdown={state.summary} />
            ) : (
              <p className="text-sm text-faint">Waiting for pipeline output...</p>
            )}
            {state.errors && state.errors.length > 0 && (
              <div className="mt-3 space-y-1">
                {state.errors.map((e, i) => (
                  <div key={i} className="rounded-lg bg-bad/10 px-3 py-1.5 text-xs text-bad">
                    {e}
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <Panel title="Requirement Analysis">
            {state.analysis ? <Markdown markdown={state.analysis} /> : <p className="text-sm text-faint">Analyzing...</p>}
          </Panel>
          <Panel title="Development Plan">
            {state.plan?.length ? (
              <ol className="list-decimal space-y-1 pl-5 text-sm text-ice">
                {state.plan.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-faint">Planning...</p>
            )}
          </Panel>
        </div>
      );
    case "Architecture":
      return <ArchitectureView architecture={state.architecture} />;
    case "Files":
      return (
        <>
          <FilesPanel files={state.files} />
          {state.commits && state.commits.length > 0 && (
            <Panel title="Git History">
              <ul className="mono space-y-1 text-xs text-faint">
                {state.commits.map((c, i) => (
                  <li key={i}>• {c}</li>
                ))}
              </ul>
            </Panel>
          )}
        </>
      );
    case "Tests":
      return <TestResults results={state.test_results} />;
    case "Fixes":
      return (
        <div className="space-y-4">
          <DiffView diffs={state.diffs} />
          {state.fixes && state.fixes.length > 0 && (
            <Panel title="Debug Agent Explanations">
              <ul className="space-y-2">
                {state.fixes.map((f, i) => (
                  <li key={i} className="text-xs text-ice">
                    <span className="mr-2 rounded bg-warn/15 px-1.5 py-0.5 text-warn">attempt {String(f.attempt)}</span>
                    <code className="mono text-faint">{String(f.path)}</code>
                    <p className="mt-1 whitespace-pre-wrap text-faint">{String(f.explanation)}</p>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      );
    case "Review":
      return <ReviewPanel review={state.review} />;
  }
}

function ArchitectureView({ architecture }: { architecture?: Record<string, unknown> }) {
  if (!architecture || Object.keys(architecture).length === 0) {
    return <Panel title="Architecture Plan">Designing the architecture...</Panel>;
  }
  const stack = Array.isArray(architecture.stack) ? (architecture.stack as string[]) : [];
  const modules = (architecture.modules && typeof architecture.modules === "object" && !Array.isArray(architecture.modules)
    ? (architecture.modules as Record<string, string>)
    : {}) as Record<string, string>;
  const apis = Array.isArray(architecture.apis) ? (architecture.apis as Record<string, unknown>[]) : [];
  const models = Array.isArray(architecture.data_models) ? (architecture.data_models as Record<string, unknown>[]) : [];
  const deps = architecture.dependencies && typeof architecture.dependencies === "object" && !Array.isArray(architecture.dependencies)
    ? (architecture.dependencies as Record<string, string>)
    : {};
  const rationale = typeof architecture.rationale === "string" ? architecture.rationale : "";

  return (
    <div className="space-y-4">
      <Panel title="Architecture Plan" badge={stack.length ? <span className="text-xs text-faint">{stack.join(" · ")}</span> : undefined}>
        {rationale && <p className="text-sm text-ice">{rationale}</p>}
      </Panel>

      {Object.keys(modules).length > 0 && (
        <Panel title="Modules">
          <ul className="space-y-2">
            {Object.entries(modules).map(([path, purpose]) => (
              <li key={path} className="flex gap-2 rounded-lg border border-line bg-panel-2 p-2 text-xs">
                <code className="mono shrink-0 text-brand">{path}</code>
                <span className="text-ice">{purpose}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {apis.length > 0 && (
        <Panel title="API Routes">
          <ul className="space-y-1 text-xs text-ice">
            {apis.map((api, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2">
                <span className="mono rounded bg-panel-2 px-1.5 py-0.5 font-semibold text-brand">
                  {String(api.method ?? "GET")}
                </span>
                <code className="mono">{String(api.path ?? "")}</code>
                <span className="text-faint">{String(api.purpose ?? "")}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {models.length > 0 && (
        <Panel title="Data Models">
          <ul className="space-y-1 text-xs text-ice">
            {models.map((m, i) => (
              <li key={i}>
                <code className="mono text-brand">{String(m.name ?? "Model")}</code>
                <span className="text-faint"> — {String(m.fields ?? "")}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {Object.keys(deps).length > 0 && (
        <Panel title="Key Dependencies">
          <ul className="space-y-1 text-xs text-ice">
            {Object.entries(deps).map(([pkg, why]) => (
              <li key={pkg}>
                <code className="mono text-brand">{pkg}</code>
                <span className="text-faint"> — {why}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}