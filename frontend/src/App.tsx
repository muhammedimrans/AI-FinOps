import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";

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
          <Route index element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Overview /></Suspense></ErrorBoundary>} />
          <Route path="analytics"    element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Analytics /></Suspense></ErrorBoundary>} />
          <Route path="providers"    element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Providers /></Suspense></ErrorBoundary>} />
          <Route path="models"       element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Models /></Suspense></ErrorBoundary>} />
          <Route path="projects"     element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Projects /></Suspense></ErrorBoundary>} />
          <Route path="organization" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Organization /></Suspense></ErrorBoundary>} />
        </Route>
        <Route path="/users"       element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Placeholder title="Users" /></Suspense></ErrorBoundary>} />
        <Route path="/rbac"        element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Placeholder title="RBAC" description="Role-based access control management. Backend auth & RBAC (EP-05) is fully implemented." /></Suspense></ErrorBoundary>} />
        <Route path="/api-keys"    element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Placeholder title="API Keys" /></Suspense></ErrorBoundary>} />
        <Route path="/connections" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Placeholder title="Provider Connections" description="Configure and manage AI provider API keys and connections." /></Suspense></ErrorBoundary>} />
        <Route path="/audit-logs"  element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Placeholder title="Audit Logs" /></Suspense></ErrorBoundary>} />
        <Route path="/settings"    element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Settings /></Suspense></ErrorBoundary>} />
      </Route>
    </Routes>
  );
}
