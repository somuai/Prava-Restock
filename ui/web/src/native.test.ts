import { describe, expect, it } from "vitest";

import { approvalRunId } from "./native";


describe("native approval links", () => {
  it("extracts only Restock approval callback run ids", () => {
    expect(approvalRunId("restock://approval?run_id=run-123")).toBe("run-123");
    expect(approvalRunId("https://example.test/approval?run_id=run-123")).toBeNull();
    expect(approvalRunId("restock://settings?run_id=run-123")).toBeNull();
  });
});
