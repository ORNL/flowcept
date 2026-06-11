/** App shell: sidebar navigation + page outlet + chat panel. */

import { lazy, Suspense } from "react";
import { Outlet, createRootRoute, Link } from "@tanstack/react-router";
import { Activity, Bot, Boxes, FolderKanban, LayoutDashboard, MessageSquare, Network, Workflow } from "lucide-react";
import { useChatStore } from "../stores/chatStore";

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
  { to: "/dashboards", label: "Dashboards", icon: LayoutDashboard },
] as const;

function AppShell() {
  const { open: chatOpen, toggle: toggleChat } = useChatStore();
  return (
    <div className="flex h-full">
      <aside className="flex w-52 shrink-0 flex-col border-r border-border bg-surface">
        <div className="flex items-center gap-2 px-4 py-4">
          <Network size={20} className="text-accent" />
          <span className="text-base font-semibold tracking-tight">Flowcept</span>
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
          <button
            onClick={toggleChat}
            className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] ${
              chatOpen ? "bg-accent-soft" : "text-fg-muted hover:bg-surface-2 hover:text-fg"
            }`}
          >
            <MessageSquare size={15} />
            Chat
          </button>
          <a href="/docs" target="_blank" rel="noreferrer" className="text-fg-muted hover:text-fg block px-2.5 text-[11px]">
            API docs ↗
          </a>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
      {chatOpen && (
        <Suspense fallback={null}>
          <ChatPanel />
        </Suspense>
      )}
    </div>
  );
}
