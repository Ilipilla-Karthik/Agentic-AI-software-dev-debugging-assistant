import { useCallback, useEffect, useRef, useState } from "react";
import { createProject, getProject, listProjects, projectEventsUrl, rerunProject, API_BASE } from "./api";
import type { LiveEvent, ProjectListItem, ProjectState } from "./types";
import Panel from "./components/Panel";
import Markdown from "./components/Markdown";
import StatusTimeline from "./components/StatusTimeline";
import FilesPanel from "./components/FilesPanel";
import TestResults from "./components/TestResults";
import DiffView from "./components/DiffView";
import ReviewPanel from "./components/ReviewPanel";

const TABS = ["Overview", "Architecture", "Files", "Tests", "Debug", "Review", "Logs"] as const;
type Tab = (typeof TABS)[number];

const DEFAULT_REQ =
  "Create a FastAPI task-management API with PostgreSQL, JWT authentication, CRUD operations, validation, and automated tests.";

function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre className="mono max-h-[26rem] overflow-auto rounded-lg border border-line bg-ink p-3 text-xs whitespace-pre-wrap">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export default function App() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [state, setState] = useState<ProjectState | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [requirement, setRequirement] = useState(DEFAULT_REQ);
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
    const es = new EventSource(projectEventsUrl(id));
    esRef.current = es;
    es.onmessage = (e) => {
      if (e.data === "{}") return;
      try {
        const ev = JSON.parse(e.data) as LiveEvent;
        setEvents((prev) => [...prev.slice(-200), ev]);
      } catch {
        /* ignore malformed */
      }
    };
    pollRef.current = setInterval(() => {
      void getProject(id).then(setState).catch(() => {});
    }, 2500);
  }, [stopLive]);

  const select = useCallback(
    (id: string) => {
      setSelected(id);
      setEvents([]);
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
    setEvents([]);
    startLive(selected);
  }, [selected, startLive]);

  const running = selected && ["queued", "running", "planning", "coding", "testing", "debugging", "reviewing"].includes(state?.status ?? "");

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ice">Agentic Dev Assistant</h1>
          <p className="text-xs text-faint">
            Autonomous plan → code → test → debug → review pipeline ·{" "}
            <span className="mono">
              {health ? `provider=${health.provider} · memory=${health.memory_backend}` : "checking backend..."}
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
          placeholder="Describe the software you want generated, tested, and reviewed..."
        />
        <div className="mt-3 flex items-center justify-between">
          <div className="text-[11px] text-faint">
            Without an OpenAI key the built-in mock provider runs the full loop end-to-end (free).
          </div>
          <button
            onClick={() => void submit()}
            disabled={busy}
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
                  Workflow in progress — stage updates streaming live below.
                </div>
              )}

              {/* live feed */}
              <Panel title="Live Stage Feed" badge={<span className="text-xs text-faint">{events.length} events</span>}>
                <div className="max-h-44 space-y-1 overflow-y-auto">
                  {events.length === 0 && <p className="text-xs text-faint">Waiting for events...</p>}
                  {events.map((ev, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="mono mt-0.5 shrink-0 rounded bg-panel-2 px-1.5 py-0.5 text-[10px] text-brand">
                        {ev.stage}
                      </span>
                      <span className="text-ice">{ev.message}</span>
                      <span className="mono ml-auto shrink-0 text-[10px] text-faint">
                        {new Date(ev.ts).toLocaleTimeString()}
                      </span>
                    </div>
                  ))}
                </div>
              </Panel>

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
      return (
        <Panel title="Architecture Plan">
          {state.architecture && Object.keys(state.architecture).length ? (
            <JsonBlock data={state.architecture} />
          ) : (
            <p className="text-sm text-faint">Architecture pending...</p>
          )}
        </Panel>
      );
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
    case "Debug":
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
    case "Logs":
      return (
        <Panel title="Agent Execution Logs">
          <pre className="mono max-h-96 overflow-auto rounded-lg border border-line bg-ink p-3 text-xs whitespace-pre-wrap text-faint">
            {(state.logs ?? []).join("\n") || "No logs yet."}
          </pre>
        </Panel>
      );
  }
}