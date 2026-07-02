import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./layouts/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import ProtectedRoute from "./components/ProtectedRoute";
import OrgSelector from "./components/OrgSelector";
import { useOrgStore } from "./stores/org";

const Login          = lazy(() => import("./features/Login"));
const ForgotPassword = lazy(() => import("./features/ForgotPassword"));
const ResetPassword  = lazy(() => import("./features/ResetPassword"));
const VerifyEmail    = lazy(() => import("./features/VerifyEmail"));
const Overview     = lazy(() => import("./features/Overview"));
const Analytics    = lazy(() => import("./features/Analytics"));
const Providers    = lazy(() => import("./features/Providers"));
const Models       = lazy(() => import("./features/Models"));
const Projects     = lazy(() => import("./features/Projects"));
const Organization = lazy(() => import("./features/Organization"));
const Settings     = lazy(() => import("./features/Settings"));
const Support      = lazy(() => import("./features/Support"));
const Connections  = lazy(() => import("./features/Connections"));
const Pricing      = lazy(() => import("./features/Pricing"));
const Users        = lazy(() => import("./features/Users"));
const RBAC         = lazy(() => import("./features/RBAC"));
const Placeholder  = lazy(() => import("./features/Placeholder"));
const NotFound     = lazy(() => import("./features/NotFound"));

function PageFallback() {
  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6 animate-fade-in">
      <div className="h-7 w-40 skeleton rounded" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }, (_, i) => <div key={i} className="h-28 skeleton rounded-card-lg" />)}
      </div>
      <div className="h-72 skeleton rounded-card-lg" />
    </div>
  );
}

function Page({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<PageFallback />}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}

// Guards the entire app shell: authenticated + organization context present.
function AuthGuard({ children }: { children: React.ReactNode }) {
  const { organizationId } = useOrgStore();
  if (!organizationId) return <OrgSelector />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route
        path="/login"
        element={
          <ErrorBoundary>
            <Suspense fallback={null}>
              <Login />
            </Suspense>
          </ErrorBoundary>
        }
      />

      {["/forgot-password", "/reset-password", "/verify-email"].map((path) => (
        <Route
          key={path}
          path={path}
          element={
            <ErrorBoundary>
              <Suspense fallback={null}>
                {path === "/forgot-password" ? <ForgotPassword /> : path === "/reset-password" ? <ResetPassword /> : <VerifyEmail />}
              </Suspense>
            </ErrorBoundary>
          }
        />
      ))}

      {/* Protected shell */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AuthGuard>
              <AppLayout />
            </AuthGuard>
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard">
          <Route index               element={<Page><Overview /></Page>} />
          <Route path="analytics"    element={<Page><Analytics /></Page>} />
          <Route path="providers"    element={<Page><Providers /></Page>} />
          <Route path="models"       element={<Page><Models /></Page>} />
          <Route path="projects"     element={<Page><Projects /></Page>} />
          <Route path="organization" element={<Page><Organization /></Page>} />
          <Route path="pricing"      element={<Page><Pricing /></Page>} />
        </Route>
        <Route path="users" element={<Page><Users /></Page>} />
        <Route path="rbac" element={<Page><RBAC /></Page>} />
        <Route path="api-keys" element={
          <Page><Placeholder
            title="API Keys"
            description="Issue and revoke programmatic API keys for ingesting usage. No API-key issuance endpoint exists yet — keys generated in Settings are local placeholders only."
            requiredEndpoints={[
              "GET    /v1/organizations/{org_id}/api-keys",
              "POST   /v1/organizations/{org_id}/api-keys",
              "DELETE /v1/organizations/{org_id}/api-keys/{id}",
            ]}
          /></Page>
        } />
        <Route path="connections" element={<Page><Connections /></Page>} />
        <Route path="audit-logs" element={
          <Page><Placeholder
            title="Audit Logs"
            description="Review a chronological record of sensitive actions (logins, role changes, key issuance). Structured audit logging exists server-side, but no queryable audit-log endpoint is exposed."
            requiredEndpoints={[
              "GET /v1/organizations/{org_id}/audit-logs",
            ]}
          /></Page>
        } />
        <Route path="settings"    element={<Page><Settings /></Page>} />
        <Route path="support"     element={<Page><Support /></Page>} />
        <Route path="*"           element={<Page><NotFound /></Page>} />
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
