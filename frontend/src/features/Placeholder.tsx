import { motion } from "framer-motion";
import { Construction } from "lucide-react";

interface PlaceholderProps {
  title: string;
  description?: string;
}

export default function Placeholder({ title, description }: PlaceholderProps) {
  return (
    <div className="p-6 flex items-center justify-center min-h-[60vh]">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="text-center max-w-sm"
      >
        <div className="w-16 h-16 rounded-2xl bg-primary-subtle flex items-center justify-center mx-auto mb-5">
          <Construction size={28} className="text-primary" />
        </div>
        <h2 className="text-h3 text-tx-primary mb-2">{title}</h2>
        <p className="text-sm text-tx-muted leading-relaxed">
          {description ?? "This page is under construction. Backend APIs are ready — UI coming soon."}
        </p>
        <div className="mt-6 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-subtle text-primary text-xs font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          Backend APIs Ready
        </div>
      </motion.div>
    </div>
  );
}
