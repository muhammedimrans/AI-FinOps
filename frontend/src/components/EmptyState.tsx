import { PackageOpen, AlertCircle } from "lucide-react";

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

  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="w-12 h-12 rounded-xl bg-app-muted flex items-center justify-center mb-4">
        <Ico size={22} className={type === "error" ? "text-danger" : "text-tx-muted"} />
      </div>
      <p className="text-sm font-medium text-tx-primary mb-1">{title}</p>
      <p className="text-xs text-tx-muted max-w-xs leading-relaxed">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
