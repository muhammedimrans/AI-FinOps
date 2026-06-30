import { motion, AnimatePresence } from "framer-motion";
import { NavLink, useLocation } from "react-router-dom";
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
  ChevronLeft,
  ChevronRight,
  Zap,
  Activity,
} from "lucide-react";
import { cn } from "../lib/utils";
import { useUIStore } from "../stores/ui";

interface NavItem {
  to: string;
  icon: React.ElementType;
  label: string;
  group?: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard",              icon: LayoutDashboard, label: "Overview",        group: "Analytics" },
  { to: "/dashboard/analytics",    icon: TrendingUp,      label: "Cost Analytics",  group: "Analytics" },
  { to: "/dashboard/providers",    icon: Cpu,             label: "Providers",       group: "Analytics" },
  { to: "/dashboard/models",       icon: Boxes,           label: "Models",          group: "Analytics" },
  { to: "/dashboard/projects",     icon: FolderOpen,      label: "Projects",        group: "Analytics" },
  { to: "/dashboard/organization", icon: Building2,       label: "Organization",    group: "Analytics" },
  { to: "/users",                  icon: Users,           label: "Users",           group: "Admin" },
  { to: "/rbac",                   icon: ShieldCheck,     label: "RBAC",            group: "Admin" },
  { to: "/api-keys",               icon: Key,             label: "API Keys",        group: "Admin" },
  { to: "/connections",            icon: PlugZap,         label: "Connections",     group: "Admin" },
  { to: "/audit-logs",             icon: ScrollText,      label: "Audit Logs",      group: "Admin" },
  { to: "/settings",               icon: Settings,        label: "Settings",        group: "System" },
];

const GROUPS = ["Analytics", "Admin", "System"];

export default function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useUIStore();
  const location = useLocation();

  return (
    <motion.aside
      animate={{ width: sidebarCollapsed ? 64 : 240 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      className="relative flex flex-col bg-app-card border-r border-border-subtle h-full overflow-hidden flex-shrink-0"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-4 h-[60px] border-b border-border-subtle flex-shrink-0">
        <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center flex-shrink-0 shadow-glow">
          <Zap size={16} className="text-white" />
        </div>
        <AnimatePresence>
          {!sidebarCollapsed && (
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="flex flex-col min-w-0"
            >
              <span className="text-sm font-semibold text-tx-primary leading-tight truncate">
                AI FinOps
              </span>
              <span className="text-[10px] text-tx-muted leading-tight">
                Cost Intelligence
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 overflow-y-auto overflow-x-hidden">
        {GROUPS.map((group) => {
          const items = NAV_ITEMS.filter((n) => n.group === group);
          return (
            <div key={group} className="mb-1">
              <AnimatePresence>
                {!sidebarCollapsed && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="px-4 pb-1 pt-3 text-[10px] font-semibold text-tx-muted uppercase tracking-widest"
                  >
                    {group}
                  </motion.p>
                )}
              </AnimatePresence>
              {items.map((item) => (
                <SidebarItem
                  key={item.to}
                  item={item}
                  collapsed={sidebarCollapsed}
                  active={
                    item.to === "/dashboard"
                      ? location.pathname === "/dashboard"
                      : location.pathname.startsWith(item.to)
                  }
                />
              ))}
            </div>
          );
        })}
      </nav>

      {/* User section */}
      <div className="border-t border-border-subtle p-3 flex-shrink-0">
        <div
          className={cn(
            "flex items-center gap-3 rounded-lg px-2 py-2 cursor-pointer",
            "hover:bg-app-hover transition-colors duration-200",
          )}
        >
          <div className="w-7 h-7 rounded-full bg-gradient-primary flex items-center justify-center flex-shrink-0">
            <span className="text-[11px] font-semibold text-white">MI</span>
          </div>
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="min-w-0"
              >
                <p className="text-xs font-medium text-tx-primary truncate">Mohammed Imran</p>
                <p className="text-[10px] text-tx-muted truncate">Platform Admin</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={toggleSidebar}
        className={cn(
          "absolute top-[72px] -right-3 w-6 h-6 rounded-full",
          "bg-app-card border border-border flex items-center justify-center",
          "text-tx-muted hover:text-tx-primary hover:bg-app-hover",
          "transition-all duration-200 z-10 shadow-card",
        )}
        aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {sidebarCollapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </motion.aside>
  );
}

function SidebarItem({
  item,
  collapsed,
  active,
}: {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
}) {
  const Icon = item.icon;

  return (
    <NavLink
      to={item.to}
      title={collapsed ? item.label : undefined}
      className={cn(
        "nav-item mx-2 my-0.5",
        active && "active",
        collapsed && "justify-center px-2",
      )}
    >
      <Icon size={16} className="flex-shrink-0" />
      <AnimatePresence>
        {!collapsed && (
          <motion.span
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -6 }}
            transition={{ duration: 0.15 }}
            className="text-sm truncate"
          >
            {item.label}
          </motion.span>
        )}
      </AnimatePresence>
      {active && (
        <motion.div
          layoutId="nav-indicator"
          className="absolute left-0 w-0.5 h-5 bg-primary rounded-r-full"
        />
      )}
    </NavLink>
  );
}
