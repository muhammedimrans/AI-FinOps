import { motion } from "framer-motion";
import { PackageOpen, AlertCircle } from "lucide-react";
import { cn } from "../utils";

interface EmptyStateProps {
  icon?: React.ElementType;
  title?: string;
  description?: string;
  action?: React.ReactNode;
  type?: "empty" | "error";
}

export default function EmptyState({
  icon: Icon,
  title = "No data",
  description = "There is nothing to display here yet.",
  action,
  type = "empty",
}: EmptyStateProps) {
  const DefaultIcon = type === "error" ? AlertCircle : PackageOpen;
  const Ico = Icon ?? DefaultIcon;
  const isError = type === "error";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="flex flex-col items-center justify-center py-16 px-6 text-center"
    >
      <div className="relative mb-5">
        <div
          className={cn(
            "absolute inset-0 rounded-full blur-xl opacity-50",
            isError ? "bg-danger/30" : "bg-brand/20",
          )}
        />
        <div
          className={cn(
            "relative w-14 h-14 rounded-2xl flex items-center justify-center animate-float",
            isError ? "bg-danger-dim" : "bg-brand-subtle",
          )}
        >
          <Ico size={24} className={isError ? "text-danger" : "text-brand"} />
        </div>
      </div>
      <p className="text-sm font-semibold text-tx-primary mb-1">{title}</p>
      <p className="text-xs text-tx-muted max-w-xs leading-relaxed">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </motion.div>
  );
}
