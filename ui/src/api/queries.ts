/** TanStack Query hooks for Flowcept API resources. */

import { useQuery } from "@tanstack/react-query";
import { apiGet, apiGetText, apiPost } from "./client";
import type {
  AgentSummary,
  BlobObjectDoc,
  Campaign,
  ListResponse,
  QueryRequest,
  Task,
  TaskSummary,
  Workflow,
} from "./types";

export function useInfo() {
  return useQuery({
    queryKey: ["info"],
    queryFn: () =>
      apiGet<{
        service: string;
        version: string;
        workflow_dashboard: Record<string, unknown>[];
        campaign_dashboard: Record<string, unknown>[];
      }>("/info"),
    staleTime: Infinity,
  });
}

export function useCampaigns() {
  return useQuery({
    queryKey: ["campaigns"],
    queryFn: () => apiGet<ListResponse<Campaign>>("/campaigns"),
  });
}

export function useCampaign(campaignId: string) {
  return useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () =>
      apiGet<{ campaign: Campaign; workflows: Workflow[]; task_summary: TaskSummary }>(`/campaigns/${campaignId}`),
  });
}

export function useWorkflows(params: { campaign_id?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ["workflows", params],
    queryFn: () => apiGet<ListResponse<Workflow>>("/workflows", { limit: 200, ...params }),
  });
}

export function useWorkflow(workflowId: string) {
  return useQuery({
    queryKey: ["workflow", workflowId],
    queryFn: () => apiGet<Workflow>(`/workflows/${workflowId}`),
  });
}

export function useTasksQuery(body: QueryRequest, enabled = true) {
  return useQuery({
    queryKey: ["tasks", body],
    queryFn: () => apiPost<ListResponse<Task>>("/tasks/query", body),
    enabled,
  });
}

export function useTask(taskId: string) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: () => apiGet<Task>(`/tasks/${taskId}`),
  });
}

export function useTaskSummary(params: { workflow_id?: string; campaign_id?: string; agent_id?: string }) {
  return useQuery({
    queryKey: ["taskSummary", params],
    queryFn: () => apiGet<TaskSummary>("/stats/tasks/summary", params),
  });
}

export function useObjects(params: { workflow_id?: string; type?: string } = {}) {
  const path = params.type === "ml_model" ? "/models" : params.type === "dataset" ? "/datasets" : "/objects";
  return useQuery({
    queryKey: ["objects", params],
    queryFn: () => apiGet<ListResponse<BlobObjectDoc>>(path, { workflow_id: params.workflow_id }),
  });
}

export function useObject(objectId: string) {
  return useQuery({
    queryKey: ["object", objectId],
    queryFn: () => apiGet<BlobObjectDoc>(`/objects/${objectId}`),
  });
}

export function useObjectHistory(objectId: string) {
  return useQuery({
    queryKey: ["objectHistory", objectId],
    queryFn: () => apiGet<ListResponse<BlobObjectDoc>>(`/objects/${objectId}/history`),
  });
}

export function useAgents() {
  return useQuery({
    queryKey: ["agents"],
    queryFn: () => apiGet<ListResponse<AgentSummary>>("/agents"),
  });
}

export function useWorkflowsWithTasks() {
  return useQuery({
    queryKey: ["workflowsWithTasks"],
    queryFn: async () => {
      const result = await apiPost<{ rows: Record<string, unknown>[]; count: number }>("/stats/chart_data", {
        data: {
          source: "tasks",
          group_by: "workflow_id",
          filter: { started_at: { $exists: true, $ne: null } },
          metrics: [{ field: "task_id", agg: "count" }],
          limit: 5000,
        },
      });
      return new Set(result.rows.map((r) => r["workflow_id"] as string));
    },
    staleTime: 30_000,
  });
}

export function useProvenanceCard(scope: "workflows" | "campaigns", id: string, enabled = true) {
  return useQuery({
    queryKey: ["provCard", scope, id],
    queryFn: () => apiGetText(`/${scope}/${id}/provenance_card`, { format: "markdown" }),
    enabled,
    staleTime: 60_000,
  });
}
