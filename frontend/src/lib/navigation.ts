import {
  LayoutDashboard,
  TrendingUp,
  Cpu,
  Boxes,
  FolderOpen,
  Building2,
  Users,
  ShieldCheck,
  Key,
  PlugZap,
  ScrollText,
  Settings,
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
  { to: "/dashboard/organization", icon: Building2,       label: "Organization",   group: "Analytics", keywords: "team members" },
  { to: "/users",                  icon: Users,           label: "Users",          group: "Admin" },
  { to: "/rbac",                   icon: ShieldCheck,     label: "RBAC",           group: "Admin", keywords: "roles permissions access" },
  { to: "/api-keys",               icon: Key,             label: "API Keys",       group: "Admin", keywords: "credentials secrets" },
  { to: "/connections",            icon: PlugZap,         label: "Connections",    group: "Admin", keywords: "provider integration" },
  { to: "/audit-logs",             icon: ScrollText,      label: "Audit Logs",     group: "Admin", keywords: "history activity" },
  { to: "/settings",               icon: Settings,        label: "Settings",       group: "System", keywords: "preferences profile" },
];

export const NAV_GROUPS = ["Analytics", "Admin", "System"];

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  return item.to === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(item.to);
}
