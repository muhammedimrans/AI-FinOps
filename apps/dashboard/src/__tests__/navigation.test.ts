import { describe, it, expect } from "vitest";
import { NAV_ITEMS, visibleNavItems } from "../lib/navigation";

describe("visibleNavItems — EP-25.1", () => {
  it("returns every nav item for a business workspace", () => {
    const items = visibleNavItems(false);
    expect(items).toHaveLength(NAV_ITEMS.length);
  });

  it("hides Members, RBAC, and Organization for a personal workspace", () => {
    const items = visibleNavItems(true);
    const paths = items.map((i) => i.to);
    expect(paths).not.toContain("/users");
    expect(paths).not.toContain("/rbac");
    expect(paths).not.toContain("/dashboard/organization");
  });

  it("keeps non-collaboration items visible for a personal workspace", () => {
    const items = visibleNavItems(true);
    const paths = items.map((i) => i.to);
    expect(paths).toContain("/dashboard");
    expect(paths).toContain("/dashboard/budgets");
    expect(paths).toContain("/connections");
    expect(paths).toContain("/api-keys");
    expect(paths).toContain("/settings");
  });
});
