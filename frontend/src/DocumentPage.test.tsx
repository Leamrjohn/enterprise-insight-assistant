// @vitest-environment jsdom

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DocumentPage } from "./App";
import type { ApiClient } from "./api";
import type { CurrentUser, DocumentItem } from "./types";


const owner: CurrentUser = {
  id: 7,
  name: "测试所有者",
  username: "test-owner",
  role: "owner",
  is_active: true,
  created_at: "2026-07-29T00:00:00Z",
  company_id: 3,
  company_name: "测试公司",
  membership_status: "approved",
};

const createdDocument: DocumentItem = {
  id: 19,
  company_id: 3,
  uploaded_by_user_id: 7,
  name: "华东回访纪要",
  content: "华东重点客户续约率下降。",
  source: "经营例会",
  status: "pending",
  error_message: null,
  min_view_role: "any",
  file_type: null,
  file_size: null,
  created_at: "2026-07-29T00:00:00Z",
  updated_at: "2026-07-29T00:00:00Z",
};


describe("DocumentPage", () => {
  it("keeps the form reference valid across an async create and refreshes the list", async () => {
    const user = userEvent.setup();
    const createDocument = vi.fn().mockResolvedValue(createdDocument);
    const refreshDocuments = vi.fn().mockResolvedValue(undefined);
    const api = { createDocument } as unknown as ApiClient;

    render(
      <DocumentPage
        api={api}
        user={owner}
        documents={[]}
        refreshDocuments={refreshDocuments}
      />,
    );

    await user.click(screen.getByRole("button", { name: "录入文本" }));
    expect(document.querySelector('input[type="file"]')).toBeNull();
    expect(screen.queryByRole("button", { name: "上传并解析" })).toBeNull();
    await user.type(screen.getByLabelText("资料名称"), "华东回访纪要");
    await user.clear(screen.getByLabelText("来源"));
    await user.type(screen.getByLabelText("来源"), "经营例会");
    await user.type(
      screen.getByLabelText("正文"),
      "华东重点客户续约率下降。",
    );
    await user.click(screen.getByRole("button", { name: "保存资料草稿" }));

    await waitFor(() => expect(refreshDocuments).toHaveBeenCalledOnce());
    expect(createDocument).toHaveBeenCalledWith({
      name: "华东回访纪要",
      source: "经营例会",
      content: "华东重点客户续约率下降。",
      min_view_role: "any",
    });
    expect(
      screen.queryByRole("button", { name: "保存资料草稿" }),
    ).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
