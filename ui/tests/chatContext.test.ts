import { describe, expect, it } from "vitest";
import { chatContext, routeContext } from "../src/lib/chatContext";

describe("chatContext", () => {
  it("defaults chat tool context to db", () => {
    expect(chatContext("/workflows/wf-1")).toEqual({ workflow_id: "wf-1", tool_context: "db" });
  });

  it("can request streaming in-memory queries with df context", () => {
    expect(chatContext("/campaigns/camp-1", "df")).toEqual({ campaign_id: "camp-1", tool_context: "df" });
  });

  it("keeps route context reusable without tool context", () => {
    expect(routeContext("/dashboards/main")).toEqual({ dashboard_id: "main" });
  });
});
