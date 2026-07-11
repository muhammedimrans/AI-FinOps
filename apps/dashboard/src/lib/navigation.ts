import {
  LayoutDashboard,
  TrendingUp,
  Cpu,
  Boxes,
  FolderOpen,
  Building2,
  Receipt,
  Users,
  ShieldCheck,
  Key,
  PlugZap,
  ScrollText,
  Settings,
  LifeBuoy,
  Wallet,
  Bell,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  icon: LucideIcon;
  label: string;
  group: string;
  keywords?: string;
  // EP-25.1 — hidden entirely for a personal (single-user) workspace: these
  // are all collaboration/organization-management features that only make
  // sense once more than one person can belong to the workspace, which a
  // personal org (is_personal=true) never allows by construction.
  businessOnly?: boolean;
  // EP-25.2 — label to show instead when the current workspace is
  // personal, for the handful of items whose default label carries
  // organization/team framing a single-user account shouldn't see.
  personalLabel?: string;
}

// Shared between Sidebar (navigation) and CommandPalette (quick jump / search).
export const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard",              icon: LayoutDashboard, label: "Overview",       group: "Analytics" },
  { to: "/playground",             icon: Sparkles,        label: "AI Playground",  group: "Analytics", keywords: "chat compare test prompt studio" },
  { to: "/dashboard/analytics",    icon: TrendingUp,      label: "Cost Analytics", group: "Analytics", keywords: "spend trend chart" },
  { to: "/dashboard/providers",    icon: Cpu,             label: "Providers",      group: "Analytics", keywords: "openai anthropic google azure" },
  { to: "/dashboard/models",       icon: Boxes,           label: "Models",         group: "Analytics", keywords: "gpt claude gemini" },
  { to: "/dashboard/projects",     icon: FolderOpen,      label: "Projects",       group: "Analytics", keywords: "budget team" },
  { to: "/dashboard/budgets",      icon: Wallet,          label: "Budgets",        group: "Analytics", keywords: "spend alerts thresholds forecast" },
  { to: "/dashboard/alerts",       icon: Bell,            label: "Alert Center",   group: "Analytics", keywords: "notifications severity history" },
  { to: "/dashboard/organization", icon: Building2,       label: "Organization",   group: "Analytics", keywords: "team members", businessOnly: true },
  { to: "/dashboard/pricing",      icon: Receipt,         label: "Pricing",        group: "Analytics", keywords: "cost calculator catalog rates" },
  { to: "/users",                  icon: Users,           label: "Members",        group: "Admin", keywords: "users invite team invitations", businessOnly: true },
  { to: "/rbac",                   icon: ShieldCheck,     label: "RBAC",           group: "Admin", keywords: "roles permissions access", businessOnly: true },
  { to: "/api-keys",               icon: Key,             label: "API Keys",       group: "Admin", keywords: "credentials secrets", personalLabel: "My API Keys" },
  { to: "/connections",            icon: PlugZap,         label: "Connections",    group: "Admin", keywords: "provider integration" },
  { to: "/audit-logs",             icon: ScrollText,      label: "Audit Logs",     group: "Admin", keywords: "history activity" },
  { to: "/settings",               icon: Settings,        label: "Settings",       group: "System", keywords: "preferences profile" },
  { to: "/support",                icon: LifeBuoy,        label: "Support",        group: "System", keywords: "help faq contact docs" },
];

export const NAV_GROUPS = ["Analytics", "Admin", "System"];

/** NAV_ITEMS filtered (and relabeled) for the current workspace type
 * (EP-25.1 filtering, EP-25.2 relabeling). */
export function visibleNavItems(isPersonal: boolean): NavItem[] {
  const items = isPersonal ? NAV_ITEMS.filter((item) => !item.businessOnly) : NAV_ITEMS;
  if (!isPersonal) return items;
  return items.map((item) => (item.personalLabel ? { ...item, label: item.personalLabel } : item));
}

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  return item.to === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(item.to);
}

// Where the header/title label should differ from the (shorter) sidebar label.
const ROUTE_LABEL_OVERRIDES: Record<string, string> = {
  "/connections": "Provider Connections",
};

/** Human-readable label for a route, shared by the header breadcrumb and
 * document title. `isPersonal` (EP-25.3) applies the same relabeling
 * `visibleNavItems` uses, so the breadcrumb never disagrees with the
 * sidebar/command-palette label for the page currently being viewed. */
export function routeLabel(pathname: string, isPersonal = false): string | null {
  const override = ROUTE_LABEL_OVERRIDES[pathname];
  if (override) return override;
  const item = NAV_ITEMS.find((n) => n.to === pathname);
  if (!item) return null;
  return isPersonal && item.personalLabel ? item.personalLabel : item.label;
}
