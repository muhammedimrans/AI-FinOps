import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Compass, ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-full flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="glass-card rounded-card-xl border border-border-subtle p-10 max-w-md w-full text-center"
      >
        <div className="relative w-14 h-14 mx-auto mb-5">
          <div className="absolute inset-0 bg-brand/20 blur-xl rounded-full animate-glow-pulse" />
          <div className="relative w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center animate-float">
            <Compass size={24} className="text-brand" />
          </div>
        </div>
        <p className="text-xs font-semibold tracking-widest text-tx-muted uppercase mb-1">Error 404</p>
        <h1 className="text-h4 font-bold text-tx-primary mb-2">Page not found</h1>
        <p className="text-sm text-tx-muted mb-6 leading-relaxed">
          The page you&apos;re looking for doesn&apos;t exist or may have moved.
        </p>
        <Link
          to="/dashboard"
          className="btn-primary inline-flex w-fit mx-auto"
        >
          <ArrowLeft size={14} />
          Back to dashboard
        </Link>
      </motion.div>
    </div>
  );
}
