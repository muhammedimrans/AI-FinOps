import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";

const Overview     = lazy(() => import("./features/Overview"));
const Analytics    = lazy(() => import("./features/Analytics"));
const Providers    = lazy(() => import("./features/Providers"));
const Models       = lazy(() => import("./features/Models"));
const Projects     = lazy(() => import("./features/Projects"));
const Organization = lazy(() => import("./features/Organization"));
const Settings     = lazy(() => import("./features/Settings"));
const Placeholder  = lazy(() => import("./features/Placeholder"));

function PageFallback() {
  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div className="h-7 w-40 skeleton rounded" />
      <div className="grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => <div key={i} className="h-28 skeleton rounded-card" />)}
      </div>
      <div className="h-72 skeleton rounded-card" />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route element={<AppLayout />}>
        <Route path="/dashboard">
          <Route index element={<Suspense fallback={<PageFallback />}><Overview /></Suspense>} />
          <Route path="analytics"    element={<Suspense fallback={<PageFallback />}><Analytics /></Suspense>} />
          <Route path="providers"    element={<Suspense fallback={<PageFallback />}><Providers /></Suspense>} />
          <Route path="models"       element={<Suspense fallback={<PageFallback />}><Models /></Suspense>} />
          <Route path="projects"     element={<Suspense fallback={<PageFallback />}><Projects /></Suspense>} />
          <Route path="organization" element={<Suspense fallback={<PageFallback />}><Organization /></Suspense>} />
        </Route>
        <Route path="/users"       element={<Suspense fallback={<PageFallback />}><Placeholder title="Users" /></Suspense>} />
        <Route path="/rbac"        element={<Suspense fallback={<PageFallback />}><Placeholder title="RBAC" description="Role-based access control management. Backend auth & RBAC (EP-05) is fully implemented." /></Suspense>} />
        <Route path="/api-keys"    element={<Suspense fallback={<PageFallback />}><Placeholder title="API Keys" /></Suspense>} />
        <Route path="/connections" element={<Suspense fallback={<PageFallback />}><Placeholder title="Provider Connections" description="Configure and manage AI provider API keys and connections." /></Suspense>} />
        <Route path="/audit-logs"  element={<Suspense fallback={<PageFallback />}><Placeholder title="Audit Logs" /></Suspense>} />
        <Route path="/settings"    element={<Suspense fallback={<PageFallback />}><Settings /></Suspense>} />
      </Route>
    </Routes>
  );
}
