import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, ChevronsUpDown, LogOut, Building2, X } from "lucide-react";
import { cn } from "../utils";
import Avatar from "../components/Avatar";
import OrgLogo from "../components/OrgLogo";
import { useUIStore } from "../stores/ui";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import { NAV_ITEMS, NAV_GROUPS, isNavItemActive, type NavItem } from "../lib/navigation";
import { CostorahMark } from "../components/CostorahLogo";

interface SidebarProps {
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export default function Sidebar({ mobileOpen = false, onCloseMobile }: SidebarProps) {
  const { sidebarCollapsed, toggleSidebar } = useUIStore();
  const location = useLocation();

  useEffect(() => {
    if (!mobileOpen) return undefined;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCloseMobile?.();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen, onCloseMobile]);

  return (
    <>
      {/* Desktop — persistent, collapsible */}
      <motion.aside
        animate={{ width: sidebarCollapsed ? 64 : 240 }}
        transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
        className="hidden lg:flex relative flex-col bg-app-card border-r border-border-subtle h-full overflow-hidden flex-shrink-0"
      >
        <SidebarBody collapsed={sidebarCollapsed} location={location} />

        <button
          onClick={toggleSidebar}
          className={cn(
            "absolute top-[72px] -right-3 w-6 h-6 rounded-full",
            "bg-app-card border border-border flex items-center justify-center",
            "text-tx-muted hover:text-brand hover:border-brand/40 hover:bg-app-hover",
            "transition-all duration-base z-10 shadow-card",
          )}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
        </button>
      </motion.aside>

      {/* Mobile — off-canvas drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <div className="lg:hidden fixed inset-0 z-50">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 bg-black/60"
              onClick={onCloseMobile}
              aria-hidden="true"
            />
            <motion.aside
              role="dialog"
              aria-modal="true"
              aria-label="Navigation"
              initial={{ x: -272 }}
              animate={{ x: 0 }}
              exit={{ x: -272 }}
              transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
              className="absolute inset-y-0 left-0 w-64 flex flex-col bg-app-card border-r border-border-subtle overflow-hidden"
            >
              <button
                onClick={onCloseMobile}
                aria-label="Close navigation"
                className="absolute top-4 right-3 w-7 h-7 rounded-lg flex items-center justify-center
                           text-tx-muted hover:text-tx-primary hover:bg-app-hover transition-colors duration-fast"
              >
                <X size={15} />
              </button>
              <SidebarBody collapsed={false} location={location} {...(onCloseMobile ? { onNavigate: onCloseMobile } : {})} />
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}

function SidebarBody({
  collapsed,
  location,
  onNavigate,
}: {
  collapsed: boolean;
  location: ReturnType<typeof useLocation>;
  onNavigate?: () => void;
}) {
  return (
    <>
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4 h-[60px] border-b border-border-subtle flex-shrink-0">
        <CostorahMark className="w-8 h-8 flex-shrink-0" />
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="flex flex-col min-w-0"
            >
              <span className="font-display text-sm font-bold tracking-wide text-tx-primary leading-tight truncate">
                COSTORAH
              </span>
              <span className="text-[10px] text-tx-muted leading-tight">
                AI Cost Intelligence
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 overflow-y-auto overflow-x-hidden">
        {NAV_GROUPS.map((group) => {
          const items = NAV_ITEMS.filter((n) => n.group === group);
          return (
            <div key={group} className="mb-1">
              <AnimatePresence>
                {!collapsed && (
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
                  collapsed={collapsed}
                  active={isNavItemActive(item, location.pathname)}
                  {...(onNavigate ? { onNavigate } : {})}
                />
              ))}
            </div>
          );
        })}
      </nav>

      <UserMenu collapsed={collapsed} />
    </>
  );
}

function SidebarItem({
  item,
  collapsed,
  active,
  onNavigate,
}: {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;

  return (
    <NavLink
      to={item.to}
      onClick={onNavigate}
      title={collapsed ? item.label : undefined}
      className={cn(
        "nav-item mx-2 my-0.5 relative",
        active ? "text-brand font-medium" : undefined,
        collapsed && "justify-center px-2",
      )}
    >
      {active && (
        <motion.div
          layoutId="nav-indicator"
          className="absolute inset-0 rounded-lg bg-brand-subtle shadow-glow-brand"
          transition={{ type: "spring", stiffness: 380, damping: 32 }}
        />
      )}
      <Icon size={16} className="relative z-10 flex-shrink-0" />
      <AnimatePresence>
        {!collapsed && (
          <motion.span
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -6 }}
            transition={{ duration: 0.15 }}
            className="relative z-10 text-sm truncate"
          >
            {item.label}
          </motion.span>
        )}
      </AnimatePresence>
    </NavLink>
  );
}

function UserMenu({ collapsed }: { collapsed: boolean }) {
  const { user, clearAuth } = useAuthStore();
  const { organizationName, clearOrganization } = useOrgStore();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const name = user?.display_name ?? "Account";
  const email = user?.email ?? "";

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", onClickOutside);
      document.addEventListener("keydown", onKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function handleSignOut() {
    setOpen(false);
    clearAuth();
    clearOrganization();
    navigate("/login", { replace: true });
  }

  function handleSwitchOrg() {
    setOpen(false);
    clearOrganization();
  }

  return (
    <div ref={ref} className="relative border-t border-border-subtle p-3 flex-shrink-0">
      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            aria-label="Account menu"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.12 }}
            className="absolute bottom-full left-3 right-3 mb-2 bg-app-card border border-border-subtle
                       rounded-lg shadow-elevated overflow-hidden z-20"
          >
            {organizationName && (
              <div className="flex items-center gap-2.5 px-3 py-2 border-b border-border-subtle">
                <OrgLogo size={24} />
                <div className="min-w-0">
                  <p className="text-[10px] text-tx-muted uppercase tracking-wide">Organization</p>
                  <p className="text-xs font-medium text-tx-primary truncate">{organizationName}</p>
                </div>
              </div>
            )}
            <button
              role="menuitem"
              onClick={handleSwitchOrg}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 text-xs text-tx-secondary
                         hover:bg-app-hover hover:text-tx-primary transition-colors duration-fast"
            >
              <Building2 size={14} />
              Switch organization
            </button>
            <button
              role="menuitem"
              onClick={handleSignOut}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 text-xs text-danger
                         hover:bg-danger-dim transition-colors duration-fast"
            >
              <LogOut size={14} />
              Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${name}`}
        className={cn(
          "w-full flex items-center gap-3 rounded-lg px-2 py-2",
          "hover:bg-app-hover transition-colors duration-base",
        )}
      >
        <Avatar name={name} size={28} />
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="min-w-0 flex-1 flex items-center justify-between gap-1"
            >
              <div className="min-w-0 text-left">
                <p className="text-xs font-medium text-tx-primary truncate">{name}</p>
                <p className="text-[10px] text-tx-muted truncate">{email}</p>
              </div>
              <ChevronsUpDown size={12} className="text-tx-muted flex-shrink-0" />
            </motion.div>
          )}
        </AnimatePresence>
      </button>
    </div>
  );
}
