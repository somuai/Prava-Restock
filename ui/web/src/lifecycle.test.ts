import { describe, expect, it } from "vitest";

import { resolveProductLifecycle } from "./App";
import type { WorkflowRun } from "./api";

const itemId = "item-coffee";
const run = (state: string, updatedAt = "2026-07-29T12:00:00Z"): WorkflowRun => ({
  run_id: `run-${state}`,
  item_id: itemId,
  state,
  updated_at: updatedAt,
});

describe("living pantry lifecycle", () => {
  it("materialises an item while its workflow is active", () => {
    expect(resolveProductLifecycle({
      base: "tracking",
      itemId,
      workflows: [run("notified")],
      hasPendingNotification: false,
    })).toBe("attention");
  });

  it("moves a completed purchase off the shelf into the completed Activity cycle", () => {
    expect(resolveProductLifecycle({
      base: "attention",
      itemId,
      workflows: [run("completed")],
      hasPendingNotification: false,
    })).toBe("restocked");
  });

  it("returns rejected and expired runs to quiet tracking", () => {
    for (const state of ["rejected", "expired"]) {
      expect(resolveProductLifecycle({
        base: "attention",
        itemId,
        workflows: [run(state)],
        hasPendingNotification: false,
      })).toBe("tracking");
    }
  });

  it("keeps an item actionable when a pending notification exists", () => {
    expect(resolveProductLifecycle({
      base: "tracking",
      itemId,
      workflows: [],
      hasPendingNotification: true,
    })).toBe("attention");
  });

  it("uses the newest workflow state", () => {
    expect(resolveProductLifecycle({
      base: "attention",
      itemId,
      workflows: [
        run("completed", "2026-07-29T10:00:00Z"),
        run("quoted", "2026-07-29T12:00:00Z"),
      ],
      hasPendingNotification: false,
    })).toBe("attention");
  });
});
