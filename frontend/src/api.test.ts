import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "./api";


function mockFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}


afterEach(() => {
  vi.unstubAllGlobals();
});


describe("ApiClient response and mutation contracts", () => {
  it("accepts an empty 204 password-change response", async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));
    const api = new ApiClient("token");

    await expect(
      api.changePassword("current-password", "replacement-password"),
    ).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/me/password",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          current_password: "current-password",
          new_password: "replacement-password",
        }),
      }),
    );
  });

  it("sends the bounded cancellation route and parses its task response", async () => {
    const payload = {
      id: 17,
      conversation_id: 4,
      status: "cancelled",
      stage: "cancelled",
    };
    const fetchMock = mockFetch(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const api = new ApiClient("token");

    await expect(api.cancelTask(4, 17)).resolves.toMatchObject(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/conversations/4/tasks/17/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("loads review drafts through the company-scoped review queue", async () => {
    const payload = [{
      id: 3,
      task_id: 17,
      task_question: "华东销售为何下降",
      status: "pending",
      reason_code: "causal_hypothesis_requires_human_review",
      report_draft: { executive_summary: "需要人工核验。" },
      draft_error: null,
      created_at: "2026-07-29T00:00:00Z",
    }];
    const fetchMock = mockFetch(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const api = new ApiClient("token");

    await expect(api.reviewRequests()).resolves.toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/review-requests",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it("accepts an empty 204 owner reset response", async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));
    const api = new ApiClient("token");

    await expect(
      api.resetMemberPassword(8, "replacement-password"),
    ).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/company/members/8/reset-password",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ new_password: "replacement-password" }),
      }),
    );
  });

  it("preserves the HTTP status and translated detail on failures", async () => {
    mockFetch(
      new Response(JSON.stringify({ detail: "analysis permission required" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const api = new ApiClient("token");

    await expect(api.documents()).rejects.toEqual(
      new ApiError(403, "当前用户没有发起经营分析的权限。"),
    );
  });
});
