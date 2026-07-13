import { motion } from "framer-motion";
import { Construction, Server, Wrench } from "lucide-react";
import PageHeader from "../components/PageHeader";

interface PlaceholderProps {
  title: string;
  description?: string;
  /**
   * Exact backend endpoints this page needs before it can be built. Listing
   * them keeps the roadmap honest — no "coming soon" without saying what's
   * actually missing. Omit when the backing API already exists.
   */
  requiredEndpoints?: string[];
  /** "backend-missing" (default) or "ui-pending" when the API already exists. */
  status?: "backend-missing" | "ui-pending";
}

export default function Placeholder({
  title,
  description,
  requiredEndpoints,
  status = "backend-missing",
}: PlaceholderProps) {
  const backendReady = status === "ui-pending";

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-4 sm:gap-6">
      <PageHeader title={title} description={description} />

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="glass-card rounded-card-lg border border-border-subtle p-8 sm:p-10 text-center max-w-xl mx-auto"
      >
        <div className="relative mx-auto mb-5 w-14 h-14">
          <div className="absolute inset-0 bg-brand/20 rounded-full blur-xl" />
          <div className="relative w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center animate-float">
            {backendReady ? <Construction size={24} className="text-brand" /> : <Wrench size={24} className="text-brand" />}
          </div>
        </div>

        <h2 className="text-base font-semibold text-tx-primary mb-2">
          {backendReady ? "Interface coming soon" : "Not yet available"}
        </h2>
        <p className="text-sm text-tx-muted leading-relaxed max-w-md mx-auto">
          {description ??
            (backendReady
              ? "The backend for this feature is implemented — the interface is on the roadmap."
              : "This feature isn't operational yet. Building it requires backend endpoints that don't exist today.")}
        </p>

        {requiredEndpoints && requiredEndpoints.length > 0 && (
          <div className="mt-6 text-left inline-block">
            <p className="text-[11px] font-semibold text-tx-muted uppercase tracking-wide mb-2 flex items-center gap-1.5">
              <Server size={12} /> Backend endpoints required
            </p>
            <ul className="flex flex-col gap-1.5">
              {requiredEndpoints.map((ep) => (
                <li key={ep}>
                  <code className="text-xs font-mono bg-app-muted text-tx-secondary px-2 py-1 rounded-md">{ep}</code>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div
          className={
            "mt-7 inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium " +
            (backendReady ? "bg-success-dim text-success" : "bg-warning-dim text-warning")
          }
        >
          <span className="relative flex w-1.5 h-1.5">
            <span className={"animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 " + (backendReady ? "bg-success" : "bg-warning")} />
            <span className={"relative inline-flex rounded-full w-1.5 h-1.5 " + (backendReady ? "bg-success" : "bg-warning")} />
          </span>
          {backendReady ? "Backend ready · UI pending" : "Backend endpoints needed"}
        </div>
      </motion.div>
    </div>
  );
}
