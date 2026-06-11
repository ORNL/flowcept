/** App shell: 3-panel resizable layout (sidebar | main+chat | agent). */

import { lazy, Suspense, useEffect } from "react";
import { Outlet, createRootRoute, Link } from "@tanstack/react-router";
import {
  Group,
  Panel,
  Separator,
  useDefaultLayout,
  usePanelCallbackRef,
  type PanelImperativeHandle,
} from "react-resizable-panels";
import { Activity, Bot, Boxes, ChevronsLeft, ChevronsRight, FolderKanban, Github, LayoutDashboard, MousePointerClick, Workflow } from "lucide-react";
import { useInfo } from "../api/queries";
import { useInspectorStore } from "../stores/inspectorStore";

const ChatPanel = lazy(() =>
  import("../components/chat/ChatPanel").then((m) => ({ default: m.ChatPanel })),
);

export const Route = createRootRoute({ component: AppShell });

const NAV = [
  { to: "/", label: "Overview", icon: Activity },
  { to: "/campaigns", label: "Campaigns", icon: FolderKanban },
  { to: "/workflows", label: "Workflows", icon: Workflow },
  { to: "/objects", label: "Artifacts", icon: Boxes },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/dashboards", label: "Dashboard configs", icon: LayoutDashboard },
] as const;

function AppShell() {
  const { data: info } = useInfo();
  const [leftHandle, leftRef] = usePanelCallbackRef();
  const [rightHandle, rightRef] = usePanelCallbackRef();
  const [chatHandle, chatRef] = usePanelCallbackRef();
  const hLayout = useDefaultLayout({ id: "flowcept-shell-h" });
  const vLayout = useDefaultLayout({ id: "flowcept-shell-v" });
  const inspectorEntity = useInspectorStore((s) => s.entity);

  useEffect(() => {
    if (rightHandle && hLayout.defaultLayout === undefined) {
      rightHandle.collapse();
    }
  }, [rightHandle, hLayout.defaultLayout]);

  useEffect(() => {
    if (inspectorEntity && rightHandle?.isCollapsed()) {
      rightHandle.expand();
    }
  }, [inspectorEntity, rightHandle]);

  return (
    <Group
      orientation="horizontal"
      className="h-full"
      defaultLayout={hLayout.defaultLayout}
      onLayoutChanged={hLayout.onLayoutChanged}
    >
      {/* Left: nav sidebar */}
      <Panel
        panelRef={leftRef}
        defaultSize={15}
        minSize={12}
        collapsible
        collapsedSize={0}
        className="flex flex-col border-r border-border bg-surface"
      >
        <div className="flex items-center px-4 py-4">
          <a href="https://flowcept.org/" target="_blank" rel="noreferrer" title="flowcept.org">
            <img src="/flowcept-logo.png" alt="Flowcept" className="h-10 w-auto" />
          </a>
        </div>
        <nav className="flex-1 space-y-0.5 px-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              activeOptions={{ exact: to === "/" }}
              className="text-fg-muted flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] hover:bg-surface-2 hover:text-fg"
              activeProps={{ className: "bg-accent-soft !text-fg" }}
            >
              <Icon size={15} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="space-y-2 border-t border-border px-2 py-3">
          <a href="/docs" target="_blank" rel="noreferrer" className="text-fg-muted hover:text-fg block px-2.5 text-[11px]">
            API docs ↗
          </a>
          <div className="flex items-center gap-3 px-2.5 pt-1">
            <a href="https://github.com/ORNL/flowcept" target="_blank" rel="noreferrer" title="GitHub"
               className="text-fg-muted hover:text-fg flex items-center gap-1">
              <Github size={13} />
              <span className="text-[11px]">GitHub</span>
            </a>
            <a
              href="https://flowcept.readthedocs.io/en/latest"
              target="_blank"
              rel="noreferrer"
              className="text-fg-muted hover:text-fg text-[11px]"
            >
              Docs ↗
            </a>
            {info?.version && (
              <span className="text-fg-muted ml-auto text-[10px]">v{info.version}</span>
            )}
          </div>
          <button
            onClick={() => leftHandle?.collapse()}
            className="text-fg-muted hover:text-fg flex w-full items-center gap-1.5 px-2.5 py-1 text-[11px]"
            title="Collapse sidebar"
          >
            <ChevronsLeft size={13} /> Collapse
          </button>
        </div>
      </Panel>

      {/* Vertical resize handle between left and center, with right-panel toggle */}
      <Separator className="bg-border hover:bg-accent/60 transition-colors w-px relative flex items-center justify-center">
        <button
          onClick={() => {
            if (rightHandle?.isCollapsed()) {
              rightHandle.expand();
            } else {
              rightHandle?.collapse();
            }
          }}
          className="absolute right-[-10px] top-1/2 -translate-y-1/2 z-10 flex h-6 w-5 items-center justify-center rounded-r border border-border bg-surface text-fg-muted hover:text-fg text-[10px]"
          title="Toggle inspector panel"
        >
          <ChevronsRight size={11} />
        </button>
      </Separator>

      {/* Center: main content + chat */}
      <Panel minSize={30} className="flex flex-col min-w-0">
        <Group
          orientation="vertical"
          className="flex-1 h-full"
          defaultLayout={vLayout.defaultLayout}
          onLayoutChanged={vLayout.onLayoutChanged}
        >
          <Panel minSize={30} className="min-h-0 overflow-y-auto">
            <Outlet />
          </Panel>
          <Separator className="bg-border hover:bg-accent/60 transition-colors h-px" />
          <Panel
            panelRef={chatRef}
            defaultSize={20}
            minSize={6}
            collapsible
            collapsedSize={5}
          >
            <Suspense fallback={null}>
              <ChatPanel panelHandle={chatHandle} />
            </Suspense>
          </Panel>
        </Group>
      </Panel>

      {/* Vertical resize handle between center and right */}
      <Separator className="bg-border hover:bg-accent/60 transition-colors w-px" />

      {/* Right: inspector panel */}
      <Panel
        panelRef={rightRef}
        defaultSize={20}
        minSize={15}
        collapsible
        collapsedSize={0}
        className="flex flex-col border-l border-border bg-surface"
      >
        <div className="border-b border-border px-4 py-2 flex items-center justify-between">
          <span className="text-sm font-medium">Inspector</span>
          {inspectorEntity && (
            <button onClick={() => useInspectorStore.getState().clear()} className="text-fg-muted hover:text-fg text-xs">✕</button>
          )}
        </div>
        {inspectorEntity ? (
          <div className="flex-1 overflow-y-auto p-3 space-y-2 text-xs">
            <div className="text-fg-muted font-medium uppercase tracking-wide text-[10px]">
              {inspectorEntity.kind === "object" ? "Artifact" : "Entity"}
            </div>
            {inspectorEntity.kind === "object" && (
              <div className="space-y-1.5">
                {Object.entries(inspectorEntity.data)
                  .filter(([, v]) => v !== null && v !== undefined && v !== "")
                  .map(([k, v]) => (
                    <div key={k} className="flex flex-col gap-0.5">
                      <span className="text-fg-muted text-[10px]">{k}</span>
                      <span className="font-mono text-[11px] break-all">
                        {typeof v === "object" ? JSON.stringify(v, null, 1) : String(v)}
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center flex-1 text-fg-muted text-xs gap-2 p-4 text-center">
            <MousePointerClick size={22} className="text-accent/60" />
            <span>Click on an entity (workflow, campaign, or activity) to inspect it here.</span>
          </div>
        )}
      </Panel>
    </Group>
  );
}

export type { PanelImperativeHandle };
