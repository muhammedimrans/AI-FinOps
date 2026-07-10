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
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  icon: LucideIcon;
  label: string;
  group: string;
  keywords?: string;
}

// Shared between Sidebar (navigation) and CommandPalette (quick jump / search).
export const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard",              icon: LayoutDashboard, label: "Overview",       group: "Analytics" },
  { to: "/dashboard/analytics",    icon: TrendingUp,      label: "Cost Analytics", group: "Analytics", keywords: "spend trend chart" },
  { to: "/dashboard/providers",    icon: Cpu,             label: "Providers",      group: "Analytics", keywords: "openai anthropic google azure" },
  { to: "/dashboard/models",       icon: Boxes,           label: "Models",         group: "Analytics", keywords: "gpt claude gemini" },
  { to: "/dashboard/projects",     icon: FolderOpen,      label: "Projects",       group: "Analytics", keywords: "budget team" },
  { to: "/dashboard/budgets",      icon: Wallet,          label: "Budgets",        group: "Analytics", keywords: "spend alerts thresholds forecast" },
  { to: "/dashboard/alerts",       icon: Bell,            label: "Alert Center",   group: "Analytics", keywords: "notifications severity history" },
  { to: "/dashboard/organization", icon: Building2,       label: "Organization",   group: "Analytics", keywords: "team members" },
  { to: "/dashboard/pricing",      icon: Receipt,         label: "Pricing",        group: "Analytics", keywords: "cost calculator catalog rates" },
  { to: "/users",                  icon: Users,           label: "Users",          group: "Admin" },
  { to: "/rbac",                   icon: ShieldCheck,     label: "RBAC",           group: "Admin", keywords: "roles permissions access" },
  { to: "/api-keys",               icon: Key,             label: "API Keys",       group: "Admin", keywords: "credentials secrets" },
  { to: "/connections",            icon: PlugZap,         label: "Connections",    group: "Admin", keywords: "provider integration" },
  { to: "/audit-logs",             icon: ScrollText,      label: "Audit Logs",     group: "Admin", keywords: "history activity" },
  { to: "/settings",               icon: Settings,        label: "Settings",       group: "System", keywords: "preferences profile" },
  { to: "/support",                icon: LifeBuoy,        label: "Support",        group: "System", keywords: "help faq contact docs" },
];

export const NAV_GROUPS = ["Analytics", "Admin", "System"];

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  return item.to === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(item.to);
}

// Where the header/title label should differ from the (shorter) sidebar label.
const ROUTE_LABEL_OVERRIDES: Record<string, string> = {
  "/connections": "Provider Connections",
};

/** Human-readable label for a route, shared by the header breadcrumb and document title. */
export function routeLabel(pathname: string): string | null {
  const override = ROUTE_LABEL_OVERRIDES[pathname];
  if (override) return override;
  return NAV_ITEMS.find((n) => n.to === pathname)?.label ?? null;
}
