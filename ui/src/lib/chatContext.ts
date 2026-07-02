export type ChatToolContext = "db" | "df";

export function routeContext(pathname: string): Record<string, string> {
  const wf = pathname.match(/\/workflows\/([^/?]+)/);
  if (wf) return { workflow_id: decodeURIComponent(wf[1]) };
  const camp = pathname.match(/\/campaigns\/([^/?]+)/);
  if (camp) return { campaign_id: decodeURIComponent(camp[1]) };
  const dash = pathname.match(/\/dashboards\/([^/?]+)/);
  if (dash) return { dashboard_id: decodeURIComponent(dash[1]) };
  return {};
}

export function chatContext(pathname: string, toolContext: ChatToolContext = "db"): Record<string, string> {
  return { ...routeContext(pathname), tool_context: toolContext };
}
