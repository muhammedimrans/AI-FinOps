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
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="text-center max-w-sm"
      >
        <div className="relative mx-auto mb-5 w-16 h-16">
          <div className="absolute inset-0 bg-brand/20 rounded-full blur-xl" />
          <div className="relative w-16 h-16 rounded-2xl bg-brand-subtle flex items-center justify-center animate-float">
            <Construction size={28} className="text-brand" />
          </div>
        </div>
        <h2 className="text-h3 text-tx-primary mb-2">{title}</h2>
        <p className="text-sm text-tx-muted leading-relaxed">
          {description ?? "This page is under construction. Backend APIs are ready — UI coming soon."}
        </p>
        <div className="mt-6 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-subtle text-brand text-xs font-medium">
          <span className="relative flex w-1.5 h-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-75" />
            <span className="relative inline-flex rounded-full w-1.5 h-1.5 bg-brand" />
          </span>
          Backend APIs Ready
        </div>
      </motion.div>
    </div>
  );
}
