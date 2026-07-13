import { Suspense, useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import Sidebar from "./Sidebar";
import Header from "./Header";
import CommandPalette from "../components/CommandPalette";
import ToastContainer from "../components/ToastContainer";
import OnboardingModal from "../components/OnboardingModal";
import { routeLabel } from "../lib/navigation";
import { useOrgStore } from "../stores/org";
import { useRealtimeConnection } from "../realtime/hooks";
import { useRealtimeQueryBridge } from "../realtime/queryBridge";

/* EP-P2 — a representative skeleton that mirrors the real dashboard shape
   (page header → KPI row with the actual card anatomy → chart grid), so the
   route-load placeholder reads as the page settling in rather than grey
   blocks. Uses the same `.glass-card` surface as real content for continuity. */
function KpiCardSkeleton() {
  return (
    <div className="glass-card rounded-card-lg border p-5">
      <div className="flex items-center gap-2.5 mb-3.5">
        <div className="size-9 skeleton rounded-xl" />
        <div className="h-3 w-24 skeleton rounded" />
      </div>
      <div className="h-7 w-28 skeleton rounded mb-2.5" />
      <div className="flex items-end justify-between">
        <div className="h-3 w-20 skeleton rounded" />
        <div className="h-6 w-16 skeleton rounded" />
      </div>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="p-4 sm:p-6 flex flex-col gap-5 sm:gap-6 animate-fade-in">
      <div className="flex flex-col gap-2">
        <div className="h-7 w-56 skeleton rounded" />
        <div className="h-3.5 w-80 max-w-full skeleton rounded" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }, (_, i) => (
          <KpiCardSkeleton key={i} />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5">
        <div className="glass-card rounded-card-lg border h-72 lg:col-span-2 p-5">
          <div className="h-4 w-40 skeleton rounded mb-4" />
          <div className="h-[calc(100%-2rem)] skeleton rounded" />
        </div>
        <div className="glass-card rounded-card-lg border h-72 p-5">
          <div className="h-4 w-28 skeleton rounded mb-4" />
          <div className="h-[calc(100%-2rem)] skeleton rounded" />
        </div>
      </div>
    </div>
  );
}

export default function AppLayout() {
  const location = useLocation();
  const isPersonal = useOrgStore((s) => s.isPersonal);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);

  // Real-time connection + React Query bridge — mounted once here so every
  // page under this layout gets live updates without wiring anything itself.
  useRealtimeConnection();
  useRealtimeQueryBridge();

  // Close the mobile drawer, reset scroll, and sync the document title
  // whenever the route changes.
  useEffect(() => {
    setMobileNavOpen(false);
    mainRef.current?.scrollTo(0, 0);
    const label = routeLabel(location.pathname, isPersonal);
    document.title = label ? `${label} · Costorah` : "Costorah — AI Cost Intelligence";
  }, [location.pathname, isPersonal]);

  return (
    <div className="flex h-screen overflow-hidden bg-app-bg">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[200]
                   focus:px-4 focus:py-2 focus:rounded-lg focus:bg-brand focus:text-app-bg
                   focus:text-sm focus:font-semibold focus:shadow-elevated"
      >
        Skip to main content
      </a>
      <CommandPalette />
      <ToastContainer />
      <OnboardingModal />
      <Sidebar mobileOpen={mobileNavOpen} onCloseMobile={() => setMobileNavOpen(false)} />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header onMenuClick={() => setMobileNavOpen(true)} />
        <main ref={mainRef} id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto focus:outline-none">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="min-h-full"
          >
            <Suspense fallback={<PageSkeleton />}>
              <Outlet />
            </Suspense>
          </motion.div>
        </main>
      </div>
    </div>
  );
}
