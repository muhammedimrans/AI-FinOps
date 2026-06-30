import { Suspense, useEffect } from "react";
import { Outlet } from "react-router-dom";
import { motion } from "framer-motion";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { useUIStore } from "../stores/ui";
import { cn } from "../lib/utils";

function PageSkeleton() {
  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div className="h-8 w-48 skeleton rounded" />
      <div className="grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-28 skeleton rounded-card" />
        ))}
      </div>
      <div className="h-72 skeleton rounded-card" />
    </div>
  );
}

export default function AppLayout() {
  const { theme } = useUIStore();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <div className={cn("flex h-screen overflow-hidden bg-app-bg", theme)}>
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto">
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
