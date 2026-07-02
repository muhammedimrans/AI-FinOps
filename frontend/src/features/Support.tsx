import { useState } from "react";
import { motion } from "framer-motion";
import { BookOpen, LifeBuoy, MessageCircle, Search, Send, ChevronRight } from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import { cn } from "../utils";
import { toast } from "../stores/toast";

const FAQS = [
  {
    q: "How is cost calculated?",
    a: "We ingest usage from every connected provider in real time, apply the current published pricing, and aggregate by project, model, and organization.",
  },
  {
    q: "Can I set budgets per project?",
    a: "Yes. Each project has a budget with utilization tracked on the dashboard; alert notifications are planned for a future release.",
  },
  {
    q: "Which providers are supported?",
    a: "OpenAI, Anthropic, Google Gemini, Azure OpenAI, AWS Bedrock, and Cohere today — with more integrations on the way.",
  },
  { q: "How often is data refreshed?", a: "Usage streams continuously; dashboard totals reconcile on every request." },
  { q: "Is my data encrypted?", a: "Yes. All data is encrypted at rest and in transit." },
];

const CONTACT_CARDS = [
  { icon: BookOpen, title: "Documentation", desc: "Guides, references, and integrations" },
  { icon: MessageCircle, title: "Live chat", desc: "Planned for a future release" },
  { icon: LifeBuoy, title: "Enterprise support", desc: "Available with enterprise plans" },
];

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-xl border border-border-subtle bg-app-bg overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
        aria-expanded={open}
      >
        <span className="text-sm font-medium text-tx-primary">{q}</span>
        <ChevronRight
          size={14}
          className={cn("text-tx-muted flex-shrink-0 transition-transform duration-base", open && "rotate-90")}
        />
      </button>
      {open && <p className="px-4 pb-3.5 text-sm text-tx-muted leading-relaxed">{a}</p>}
    </li>
  );
}

export default function Support() {
  const [search, setSearch] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const filtered = FAQS.filter((f) => f.q.toLowerCase().includes(search.toLowerCase()));

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!subject.trim() || !message.trim()) {
      toast.warning("Missing details", "Please fill in both a subject and a message.");
      return;
    }
    // No support-ticket backend exists yet — never pretend a message was sent.
    toast.info(
      "Support inbox coming soon",
      "Direct ticketing isn't wired up yet — please reach us through your account manager.",
    );
  }

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader title="Support" description="Docs, FAQs, and a direct line to the Costorah team." />

      {/* Contact channel cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {CONTACT_CARDS.map((c, i) => (
          <motion.div
            key={c.title}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            whileHover={{ y: -3, transition: { duration: 0.2, ease: "easeOut" } }}
            className="glass-card rounded-card-lg border border-border-subtle p-5 cursor-pointer transition-shadow duration-base hover:shadow-elevated"
          >
            <div className="w-10 h-10 rounded-xl bg-brand-subtle text-brand flex items-center justify-center">
              <c.icon size={18} />
            </div>
            <p className="mt-3 text-sm font-semibold text-tx-primary">{c.title}</p>
            <p className="mt-0.5 text-xs text-tx-muted">{c.desc}</p>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <Section
          title="Frequently asked"
          actions={
            <div className="relative w-full sm:w-56">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-tx-muted" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search…"
                className="w-full bg-app-bg border border-border-subtle rounded-lg pl-8 pr-3 py-1.5 text-xs text-tx-primary placeholder:text-tx-muted focus:border-brand focus:outline-none transition-colors"
              />
            </div>
          }
        >
          <ul className="space-y-2">
            {filtered.map((f) => (
              <FaqItem key={f.q} q={f.q} a={f.a} />
            ))}
            {filtered.length === 0 && (
              <li className="rounded-xl border border-dashed border-border-subtle p-8 text-center text-sm text-tx-muted">
                No results. Try different keywords.
              </li>
            )}
          </ul>
        </Section>

        <Section
          title="Contact us"
          description="Ticketing launches in a future release — reach us via your account manager for now."
          actions={
            <span className="badge bg-warning-dim text-warning text-[10px] uppercase tracking-wide">
              Coming soon
            </span>
          }
        >
          <form className="space-y-3" onSubmit={handleSubmit}>
            <div>
              <label className="text-xs text-tx-muted block mb-1.5">Subject</label>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="How can we help?"
                className="w-full bg-app-bg border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-primary placeholder:text-tx-muted focus:outline-none focus:border-brand transition-colors"
              />
            </div>
            <div>
              <label className="text-xs text-tx-muted block mb-1.5">Message</label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={5}
                placeholder="Describe the issue…"
                className="w-full bg-app-bg border border-border-subtle rounded-lg p-3 text-sm text-tx-primary placeholder:text-tx-muted focus:outline-none focus:border-brand transition-colors resize-none"
              />
            </div>
            <button type="submit" className="btn-primary w-full h-10 text-sm">
              <Send size={14} /> Send message
            </button>
          </form>
        </Section>
      </div>
    </div>
  );
}
