import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Boxes,
  Building2,
  Cpu,
  Database,
  Fingerprint,
  Gauge,
  GitBranch,
  KeyRound,
  Layers,
  Lock,
  Radar,
  Shield,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  Wallet,
  Webhook,
  Zap,
} from "lucide-react";
import { SiteLayout } from "@/components/site/SiteLayout";
import { useScrollReveal } from "@/hooks/use-scroll-reveal";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const Route = createFileRoute("/")({
  component: Landing,
});

if (typeof window !== "undefined") {
  gsap.registerPlugin(ScrollTrigger);
}

/* -------------------------------------------------------------------------- */
/* Data                                                                        */
/* -------------------------------------------------------------------------- */

const providers = [
  "OpenAI",
  "Anthropic",
  "Google Gemini",
  "Azure OpenAI",
  "OpenRouter",
  "Grok",
  "Ollama",
];

const spendData = [
  { d: "Mon", openai: 320, anthropic: 210, google: 140 },
  { d: "Tue", openai: 410, anthropic: 260, google: 180 },
  { d: "Wed", openai: 380, anthropic: 290, google: 220 },
  { d: "Thu", openai: 520, anthropic: 340, google: 260 },
  { d: "Fri", openai: 610, anthropic: 380, google: 310 },
  { d: "Sat", openai: 470, anthropic: 300, google: 240 },
  { d: "Sun", openai: 690, anthropic: 420, google: 330 },
];

const modelData = [
  { m: "gpt-4o", v: 2840 },
  { m: "claude-3.5", v: 2120 },
  { m: "gemini-1.5", v: 1450 },
  { m: "llama-3-70b", v: 890 },
  { m: "grok-2", v: 640 },
];

const pieData = [
  { name: "OpenAI", value: 42 },
  { name: "Anthropic", value: 28 },
  { name: "Google", value: 18 },
  { name: "Other", value: 12 },
];
const pieColors = ["#14D9D3", "#7AF7E8", "#3ea8b8", "#1f5b64"];

const pillars = [
  {
    icon: Wallet,
    title: "One ledger for every AI dollar",
    desc: "Normalize spend across OpenAI, Anthropic, Google, Azure, OpenRouter, Grok, and Ollama into a single, correlated view.",
  },
  {
    icon: Activity,
    title: "Live, out-of-band by design",
    desc: "Streaming metrics over WebSocket with a polling fallback — collected via provider APIs and SDKs, never in your request path.",
  },
  {
    icon: Target,
    title: "Budgets that stay ahead of spend",
    desc: "Org, project, provider, and model budgets with configurable thresholds and trend-based forecasts on your dashboard.",
  },
];

const features = [
  {
    icon: Wallet,
    title: "Unified AI Spend",
    desc: "One ledger across every provider, model, project, and team.",
  },
  {
    icon: BarChart3,
    title: "Usage Analytics",
    desc: "Token, request, and cost breakdowns down to the endpoint.",
  },
  {
    icon: Activity,
    title: "Live Monitoring",
    desc: "Streaming metrics with sub-second update latency.",
  },
  {
    icon: KeyRound,
    title: "API Keys",
    desc: "Rotate, scope, and revoke provider keys from one vault.",
  },
  {
    icon: Building2,
    title: "Organizations",
    desc: "Multi-tenant workspaces with clean isolation boundaries.",
  },
  { icon: Layers, title: "Projects", desc: "Segment spend by product, environment, or customer." },
  {
    icon: Bell,
    title: "Alerts",
    desc: "Budget and anomaly alerts in your in-app notification center. Email, Slack, and webhooks coming soon.",
  },
  {
    icon: Target,
    title: "Budget Tracking",
    desc: "Org, project, provider, and model-level budgets with configurable thresholds.",
  },
  {
    icon: TrendingUp,
    title: "Forecasting",
    desc: "Trend-based spend projections right on your dashboard.",
  },
  {
    icon: Sparkles,
    title: "Cost Optimization",
    desc: "Spot your highest-cost models and providers at a glance — model routing and prompt insights are on the roadmap.",
  },
  {
    icon: GitBranch,
    title: "Provider Comparison",
    desc: "Side-by-side spend and usage across every connected provider.",
  },
  {
    icon: Cpu,
    title: "Model Comparison",
    desc: "Compare cost and token usage across every model you use.",
  },
  {
    icon: Gauge,
    title: "Real-time Dashboard",
    desc: "Live KPIs and charts, streamed over WebSocket with a polling fallback.",
  },
  {
    icon: Boxes,
    title: "SDKs",
    desc: "Python and JavaScript/TypeScript today — more languages coming soon.",
  },
  {
    icon: Webhook,
    title: "Webhooks",
    desc: "Coming soon — push cost events to Slack, email, and your own endpoints.",
  },
  {
    icon: ShieldCheck,
    title: "RBAC",
    desc: "Owner, Admin, Member, and Viewer roles with a full audit trail. SSO is on the roadmap.",
  },
];

const steps = [
  {
    icon: Database,
    title: "Connect AI Providers",
    desc: "API key or OAuth. OpenAI, Anthropic, Google, Azure, OpenRouter, Grok, and Ollama.",
  },
  {
    icon: Activity,
    title: "Collect Usage",
    desc: "Manual or automatic background sync normalizes tokens, requests, and cost.",
  },
  {
    icon: BarChart3,
    title: "Analyze Costs",
    desc: "Slice by team, project, model, or provider in real time.",
  },
  {
    icon: Sparkles,
    title: "Spot Waste",
    desc: "See your highest-cost models and providers at a glance.",
  },
  {
    icon: TrendingUp,
    title: "Forecast & Budget",
    desc: "Track spend against configurable budgets, with more automation on the way.",
  },
];

const faqs = [
  {
    q: "Which AI providers do you support?",
    a: "OpenAI, Anthropic, Google Gemini, Azure OpenAI, OpenRouter, Grok, and Ollama today, with more providers on the way.",
  },
  {
    q: "How fast is setup?",
    a: "A few minutes. Connect a provider, drop in our Python or JavaScript SDK, and usage starts flowing in.",
  },
  {
    q: "Does Costorah sit in the request path?",
    a: "No. We collect usage out-of-band via provider APIs and optional client SDKs, so there's no added latency to your requests.",
  },
  {
    q: "Can I set budgets and alerts?",
    a: "Yes. Organization, project, provider, and model-level budgets with configurable thresholds are available today, shown in your in-app notification center. Email, Slack, and webhook delivery are coming soon.",
  },
  {
    q: "How do you handle sensitive data?",
    a: "We store usage metadata — tokens, cost, model, timestamps. Prompts and completions are never collected.",
  },
  {
    q: "Do you offer SSO and RBAC?",
    a: "Role-based access control (Owner/Admin/Member/Viewer) is available today. SSO is on our roadmap.",
  },
  {
    q: "What SDKs are available?",
    a: "Python and JavaScript/TypeScript SDKs are available today. Additional language SDKs are coming soon.",
  },
  {
    q: "Do you have a free tier?",
    a: "Yes. The Free plan is free forever, with no credit card required.",
  },
];

const pricing = [
  {
    name: "Starter",
    price: "$0",
    period: "forever",
    desc: "For solo builders and side projects.",
    features: ["Up to 1M tokens/mo", "3 providers", "7-day retention", "Community support"],
    cta: "Start free",
  },
  {
    name: "Team",
    price: "Coming soon",
    period: "",
    desc: "For growing teams shipping AI products.",
    features: [
      "Everything in Free",
      "Higher usage limits",
      "Longer data retention",
      "Priority support",
    ],
    cta: "Join the waitlist",
    highlight: true,
  },
  {
    name: "Enterprise",
    price: "Coming soon",
    period: "",
    desc: "For regulated and high-scale organizations.",
    features: [
      "Everything in Team",
      "SSO & advanced RBAC",
      "Custom retention",
      "Dedicated support",
    ],
    cta: "Contact sales",
  },
];

/* -------------------------------------------------------------------------- */
/* Page                                                                        */
/* -------------------------------------------------------------------------- */

function Landing() {
  return (
    <SiteLayout>
      <Hero />
      <Marquee />
      <Metrics />
      <ProductShowcase />
      <Features />
      <HowItWorks />
      <Developers />
      <Security />
      <Pricing />
      <FAQ />
      <FinalCTA />
    </SiteLayout>
  );
}

/* -------------------------------------------------------------------------- */
/* Primitives                                                                  */
/* -------------------------------------------------------------------------- */

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 eyebrow">
      <span className="size-1.5 rounded-full bg-[#14D9D3] shadow-[0_0_8px_#14D9D3]" />
      {children}
    </span>
  );
}

function SectionHeading({
  eyebrow,
  title,
  desc,
  align = "center",
}: {
  eyebrow?: string;
  title: React.ReactNode;
  desc?: string;
  align?: "center" | "left";
}) {
  const revealRef = useScrollReveal<HTMLDivElement>({ selector: "[data-reveal]" });
  return (
    <div
      ref={revealRef}
      className={align === "center" ? "mx-auto max-w-2xl text-center" : "max-w-2xl"}
    >
      {eyebrow && (
        <div data-reveal>
          <Eyebrow>{eyebrow}</Eyebrow>
        </div>
      )}
      <h2 data-reveal className="mt-5 display-lg">
        {title}
      </h2>
      {desc && (
        <p
          data-reveal
          className={`mt-4 text-[0.975rem] leading-relaxed text-muted-foreground ${
            align === "center" ? "mx-auto max-w-xl" : "max-w-xl"
          }`}
        >
          {desc}
        </p>
      )}
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="size-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

const chartTooltip = {
  background: "rgba(8,12,20,0.95)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 12,
  fontSize: 12,
  boxShadow: "0 20px 40px -20px rgba(0,0,0,0.8)",
} as const;

/* -------------------------------------------------------------------------- */
/* Hero                                                                        */
/* -------------------------------------------------------------------------- */

function Hero() {
  const auroraRef = useRef<HTMLDivElement | null>(null);

  // Subtle scroll parallax on the aurora — a single scrubbed ScrollTrigger,
  // reverted on cleanup. Skipped entirely under reduced-motion.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const el = auroraRef.current;
    if (!el) return;
    const ctx = gsap.context(() => {
      gsap.to(el, {
        yPercent: 18,
        ease: "none",
        scrollTrigger: { trigger: el, start: "top top", end: "bottom top", scrub: 0.6 },
      });
    });
    return () => ctx.revert();
  }, []);

  return (
    <section className="relative overflow-hidden">
      <div ref={auroraRef} className="aurora" aria-hidden="true" />
      <div className="absolute inset-0 bg-grid opacity-50 [mask-image:radial-gradient(ellipse_70%_55%_at_50%_0%,black,transparent_75%)]" />

      <div className="relative mx-auto max-w-[80rem] px-6 pb-20 pt-16 md:pb-28 md:pt-24">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="mx-auto max-w-3xl text-center"
        >
          <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 backdrop-blur">
            <span className="relative flex size-1.5">
              <span className="absolute inset-0 animate-ping rounded-full bg-[#14D9D3] opacity-70" />
              <span className="relative size-1.5 rounded-full bg-[#14D9D3]" />
            </span>
            <span className="eyebrow">AI FinOps · Live</span>
          </div>

          <h1 className="mt-7 display-2xl">
            Understand every
            <br className="hidden sm:block" />{" "}
            <span className="text-gradient-brand">AI dollar</span>.
          </h1>

          <p className="mx-auto mt-6 max-w-xl text-base leading-relaxed text-muted-foreground md:text-lg">
            Monitor, optimize, and forecast AI spend across OpenAI, Anthropic, Google, Azure,
            OpenRouter, Grok, and Ollama — from one unified platform.
          </p>

          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              to="/signup"
              className="btn-brand group px-6 py-3 text-sm hover:scale-[1.02] hover:brightness-105 active:scale-[0.98]"
            >
              Start free
              <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
            </Link>
            <Link to="/contact" className="btn-ghost px-6 py-3 text-sm hover:bg-white/[0.06]">
              Book a demo
            </Link>
          </div>

          <div className="mt-7 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="size-3.5 text-[#14D9D3]" /> Encrypted credentials
            </span>
            <span className="flex items-center gap-1.5">
              <Lock className="size-3.5 text-[#14D9D3]" /> Zero-latency ingest
            </span>
            <span className="flex items-center gap-1.5">
              <Zap className="size-3.5 text-[#14D9D3]" /> 10-minute setup
            </span>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.75, delay: 0.15, ease: "easeOut" }}
          className="relative mx-auto mt-16 max-w-6xl"
        >
          <div className="pointer-events-none absolute -inset-x-8 -bottom-10 top-10 -z-10 rounded-[2.5rem] bg-[#14D9D3]/10 blur-3xl" />
          <HeroIllustration />
        </motion.div>
      </div>
    </section>
  );
}

function HeroIllustration() {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-[#080C14]/85 p-4 shadow-[var(--shadow-float)] backdrop-blur md:p-6">
      <div className="flex items-center gap-2 border-b border-white/5 px-2 pb-3">
        <span className="size-2.5 rounded-full bg-white/10" />
        <span className="size-2.5 rounded-full bg-white/10" />
        <span className="size-2.5 rounded-full bg-white/10" />
        <span className="ml-3 font-mono text-xs text-muted-foreground">app.costorah.com</span>
        <span className="ml-auto flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-[#14D9D3]">
          <span className="size-1.5 rounded-full bg-[#14D9D3] shadow-[0_0_8px_#14D9D3]" /> Live
        </span>
      </div>
      <div className="grid gap-4 pt-4 md:grid-cols-3">
        <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
          <div className="text-xs text-muted-foreground">This month</div>
          <div className="mt-2 tnum font-display text-3xl font-semibold">$48,392</div>
          <div className="mt-1 flex items-center gap-1 text-xs text-[#14D9D3]">
            <TrendingUp className="size-3" /> 18% under budget
          </div>
          <div className="mt-4 h-16">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={spendData}>
                <defs>
                  <linearGradient id="hg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#14D9D3" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#14D9D3" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="openai"
                  stroke="#14D9D3"
                  strokeWidth={2}
                  fill="url(#hg)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5 md:col-span-2">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-muted-foreground">Spend by provider</div>
              <div className="mt-1 font-display text-lg font-semibold">7-day view</div>
            </div>
            <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
              <Legend color="#14D9D3" label="OpenAI" />
              <Legend color="#7AF7E8" label="Anthropic" />
              <Legend color="#3ea8b8" label="Google" />
            </div>
          </div>
          <div className="mt-3 h-40">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={spendData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#14D9D3" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#14D9D3" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="g2" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7AF7E8" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#7AF7E8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis
                  dataKey="d"
                  stroke="#6b7280"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis stroke="#6b7280" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={chartTooltip} />
                <Area
                  type="monotone"
                  dataKey="openai"
                  stroke="#14D9D3"
                  strokeWidth={2}
                  fill="url(#g1)"
                />
                <Area
                  type="monotone"
                  dataKey="anthropic"
                  stroke="#7AF7E8"
                  strokeWidth={2}
                  fill="url(#g2)"
                />
                <Area
                  type="monotone"
                  dataKey="google"
                  stroke="#3ea8b8"
                  strokeWidth={2}
                  fill="none"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Marquee                                                                     */
/* -------------------------------------------------------------------------- */

function Marquee() {
  return (
    <section className="border-y border-white/5 bg-white/[0.012] py-12">
      <div className="mx-auto max-w-[80rem] px-6">
        <p className="text-center eyebrow">Connect every major AI provider</p>
      </div>
      <div className="group relative mt-8 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]">
        <div className="marquee-track flex w-max items-center gap-4 group-hover:[animation-play-state:paused]">
          {[...providers, ...providers].map((p, i) => (
            <span
              key={`${p}-${i}`}
              className="flex items-center gap-2.5 whitespace-nowrap rounded-full border border-white/10 bg-white/[0.02] px-5 py-2 text-sm text-foreground/70"
            >
              <span className="size-1.5 rounded-full bg-[#14D9D3]/70" />
              {p}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Metrics — animated count-up strip                                           */
/* -------------------------------------------------------------------------- */

function AnimatedNumber({
  value,
  prefix = "",
  suffix = "",
  decimals = 0,
}: {
  value: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
}) {
  const ref = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const el = ref.current;
    if (!el) return;
    const format = (n: number) =>
      `${prefix}${n.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}${suffix}`;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      el.textContent = format(value);
      return;
    }

    const obj = { n: 0 };
    el.textContent = format(0);
    const ctx = gsap.context(() => {
      gsap.to(obj, {
        n: value,
        duration: 1.6,
        ease: "power2.out",
        scrollTrigger: { trigger: el, start: "top 90%", once: true },
        onUpdate: () => {
          el.textContent = format(obj.n);
        },
      });
    });
    return () => ctx.revert();
  }, [value, prefix, suffix, decimals]);

  return <span ref={ref} className="tnum" />;
}

function Metrics() {
  const stats = [
    { value: 7, suffix: "+", label: "AI providers, one ledger" },
    { value: 284, suffix: "M", label: "Tokens tracked / day, demo scale" },
    { value: 18, suffix: "%", label: "Typical spend visibility gain" },
    { value: 10, suffix: " min", label: "From connect to first insight" },
  ];
  return (
    <section className="border-b border-white/5 py-14">
      <div className="mx-auto grid max-w-[80rem] grid-cols-2 gap-x-6 gap-y-10 px-6 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="text-center lg:text-left">
            <div className="display-lg text-gradient-brand">
              <AnimatedNumber value={s.value} suffix={s.suffix} />
            </div>
            <div className="mt-2 text-sm text-muted-foreground">{s.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Product showcase — bento                                                    */
/* -------------------------------------------------------------------------- */

function ProductShowcase() {
  const gridRef = useScrollReveal<HTMLDivElement>({
    selector: "[data-reveal]",
    y: 22,
    stagger: 0.07,
  });

  return (
    <section className="relative py-24 md:py-32">
      <div className="mx-auto max-w-[80rem] px-6">
        <SectionHeading
          eyebrow="Live dashboard"
          title={<>See your AI economy in real time.</>}
          desc="Every provider, every model, every project — normalized, correlated, and streamed live."
        />

        <div ref={gridRef} className="mt-14 grid gap-4 lg:grid-cols-6">
          <StatCard icon={Wallet} label="Spend today" value="$3,284" trend="+4.2%" />
          <StatCard icon={Activity} label="Requests" value="1.2M" trend="+11%" />
          <StatCard icon={Cpu} label="Tokens" value="284M" trend="+6%" />
          <StatCard icon={Gauge} label="Avg latency" value="612ms" trend="-8%" positive />
          <StatCard icon={Radar} label="Anomalies" value="3" trend="live" positive />
          <StatCard icon={Users} label="Active users" value="94" trend="+2" />

          <div data-reveal className="panel p-5 lg:col-span-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-muted-foreground">Cost forecast</div>
                <div className="mt-1 font-display text-lg font-semibold">Next 30 days</div>
              </div>
              <span className="rounded-full bg-[#14D9D3]/10 px-2.5 py-1 text-xs text-[#14D9D3]">
                ± 4.1% confidence
              </span>
            </div>
            <div className="mt-4 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={spendData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="d"
                    stroke="#6b7280"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis stroke="#6b7280" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={chartTooltip} />
                  <Line
                    type="monotone"
                    dataKey="openai"
                    stroke="#14D9D3"
                    strokeWidth={2.5}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="anthropic"
                    stroke="#7AF7E8"
                    strokeWidth={2}
                    dot={false}
                    strokeDasharray="4 4"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div data-reveal className="panel p-5 lg:col-span-2">
            <div className="text-xs text-muted-foreground">Provider mix</div>
            <div className="mt-1 font-display text-lg font-semibold">This quarter</div>
            <div className="mt-2 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={3}
                    stroke="none"
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={pieColors[i]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={chartTooltip} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 flex flex-col gap-1.5">
              {pieData.map((p, i) => (
                <div key={p.name} className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-2">
                    <span className="size-2 rounded-full" style={{ background: pieColors[i] }} />
                    {p.name}
                  </span>
                  <span className="tnum text-muted-foreground">{p.value}%</span>
                </div>
              ))}
            </div>
          </div>

          <div data-reveal className="panel p-5 lg:col-span-3">
            <div className="text-xs text-muted-foreground">Top models by spend</div>
            <div className="mt-1 font-display text-lg font-semibold">Last 30 days</div>
            <div className="mt-4 h-60">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={modelData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis
                    dataKey="m"
                    stroke="#6b7280"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis stroke="#6b7280" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={chartTooltip} />
                  <Bar dataKey="v" fill="#14D9D3" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div data-reveal className="panel p-5 lg:col-span-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-muted-foreground">Live activity</div>
                <div className="mt-1 font-display text-lg font-semibold">Streaming events</div>
              </div>
              <span className="flex items-center gap-2 text-xs text-[#14D9D3]">
                <span className="relative flex size-2">
                  <span className="absolute inset-0 animate-ping rounded-full bg-[#14D9D3] opacity-60" />
                  <span className="relative size-2 rounded-full bg-[#14D9D3]" />
                </span>
                Live
              </span>
            </div>
            <div className="mt-4 flex flex-col gap-2">
              {[
                { p: "OpenAI", m: "gpt-4o", t: "18,240 tok", c: "$0.42" },
                { p: "Anthropic", m: "claude-3.5-sonnet", t: "9,120 tok", c: "$0.31" },
                { p: "Google", m: "gemini-1.5-pro", t: "24,880 tok", c: "$0.19" },
                { p: "Azure", m: "gpt-4o-mini", t: "62,300 tok", c: "$0.09" },
                { p: "OpenRouter", m: "llama-3-70b", t: "3,410 tok", c: "$0.02" },
              ].map((r, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2 text-sm"
                >
                  <div className="flex items-center gap-3">
                    <span className="rounded-md bg-[#14D9D3]/10 px-2 py-0.5 text-xs text-[#14D9D3]">
                      {r.p}
                    </span>
                    <span className="font-mono text-xs text-foreground/80">{r.m}</span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="tnum">{r.t}</span>
                    <span className="tnum text-foreground">{r.c}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  trend,
  positive,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  trend: string;
  positive?: boolean;
}) {
  return (
    <div data-reveal className="panel p-5">
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">{label}</div>
        <span className="flex size-7 items-center justify-center rounded-lg bg-[#14D9D3]/10 text-[#14D9D3]">
          <Icon className="size-3.5" />
        </span>
      </div>
      <div className="mt-2 tnum font-display text-2xl font-semibold">{value}</div>
      <div className={`mt-1 text-xs ${positive ? "text-[#14D9D3]" : "text-muted-foreground"}`}>
        {trend}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Features                                                                    */
/* -------------------------------------------------------------------------- */

function Features() {
  const pillarRef = useScrollReveal<HTMLDivElement>({
    selector: "[data-reveal]",
    y: 20,
    stagger: 0.08,
  });

  return (
    <section className="relative border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-[80rem] px-6">
        <SectionHeading
          eyebrow="Platform"
          title={<>Every capability a modern AI team needs.</>}
          desc="From ingestion to forecasting — one focused platform for FinOps, platform, and finance teams."
        />

        {/* Three value pillars — hierarchy above the full capability grid. */}
        <div ref={pillarRef} className="mt-14 grid gap-4 md:grid-cols-3">
          {pillars.map((p) => (
            <div
              key={p.title}
              data-reveal
              className="panel-glow group relative overflow-hidden p-7"
            >
              <div className="pointer-events-none absolute -right-10 -top-10 size-32 rounded-full bg-[#14D9D3]/10 blur-2xl transition-opacity duration-300 group-hover:opacity-100" />
              <span className="relative flex size-11 items-center justify-center rounded-xl bg-gradient-brand text-primary-foreground shadow-[0_8px_24px_-8px_rgba(20,217,211,0.7)]">
                <p.icon className="size-5" />
              </span>
              <h3 className="relative mt-5 font-display text-lg font-semibold">{p.title}</h3>
              <p className="relative mt-2 text-sm leading-relaxed text-muted-foreground">
                {p.desc}
              </p>
            </div>
          ))}
        </div>

        {/* Full capability grid. */}
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.4, delay: (i % 4) * 0.05 }}
              className="group relative overflow-hidden rounded-2xl border border-white/[0.08] bg-white/[0.015] p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-[#14D9D3]/30 hover:bg-white/[0.03]"
            >
              <div className="inline-flex size-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] text-[#14D9D3] transition-colors group-hover:border-[#14D9D3]/40 group-hover:bg-[#14D9D3]/10">
                <f.icon className="size-4.5" />
              </div>
              <div className="mt-4 font-display text-[0.95rem] font-semibold">{f.title}</div>
              <div className="mt-1 text-[0.8125rem] leading-relaxed text-muted-foreground">
                {f.desc}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* How it works                                                                */
/* -------------------------------------------------------------------------- */

function HowItWorks() {
  const stepsRef = useScrollReveal<HTMLDivElement>({
    selector: "[data-reveal]",
    y: 22,
    stagger: 0.08,
  });

  return (
    <section className="relative overflow-hidden border-t border-white/5 py-24 md:py-32">
      <div className="aurora opacity-40" aria-hidden="true" />
      <div className="relative mx-auto max-w-[80rem] px-6">
        <SectionHeading
          eyebrow="How it works"
          title={<>Five steps to AI cost clarity.</>}
          desc="From first connection to automated forecasts — Costorah fits into the workflow you already have."
        />
        <div ref={stepsRef} className="relative mt-16 grid gap-5 md:grid-cols-5">
          {/* Connecting rail behind the step cards on desktop. */}
          <div className="pointer-events-none absolute inset-x-[10%] top-[2.1rem] hidden h-px bg-gradient-to-r from-transparent via-[#14D9D3]/30 to-transparent md:block" />
          {steps.map((s, i) => (
            <div key={s.title} data-reveal className="relative panel p-6">
              <div className="flex items-center justify-between">
                <div className="flex size-9 items-center justify-center rounded-full bg-gradient-brand tnum font-display text-sm font-semibold text-primary-foreground shadow-[0_8px_20px_-8px_rgba(20,217,211,0.8)]">
                  {i + 1}
                </div>
                <s.icon className="size-4 text-[#14D9D3]" />
              </div>
              <div className="mt-5 font-display text-[0.95rem] font-semibold">{s.title}</div>
              <div className="mt-1.5 text-[0.8125rem] leading-relaxed text-muted-foreground">
                {s.desc}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Developers                                                                  */
/* -------------------------------------------------------------------------- */

const pythonCode = `from costorah import Costorah

client = Costorah(api_key="ck_live_...")

response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
)

client.track(
    provider="openai",
    model="gpt-4o",
    usage=response.usage,
    project="production",
)`;

const tsCode = `import { Costorah } from "costorah";

const client = new Costorah({ apiKey: process.env.COSTORAH_KEY! });

const res = await openai.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Hello" }],
});

await client.track({
  provider: "openai",
  model: "gpt-4o",
  usage: res.usage,
  project: "production",
});`;

function Developers() {
  const revealRef = useScrollReveal<HTMLDivElement>({
    selector: "[data-reveal]",
    y: 18,
    stagger: 0.06,
  });
  const codeRef = useScrollReveal<HTMLDivElement>({ selector: "[data-reveal]", y: 22, delay: 0.1 });

  return (
    <section className="border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-[80rem] px-6">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div ref={revealRef}>
            <div data-reveal>
              <Eyebrow>Built for developers</Eyebrow>
            </div>
            <h2 data-reveal className="mt-5 display-lg">
              Ship in minutes. <br />
              <span className="text-gradient-brand">Instrument once.</span>
            </h2>
            <p
              data-reveal
              className="mt-5 max-w-lg text-[0.975rem] leading-relaxed text-muted-foreground"
            >
              Python and JavaScript/TypeScript SDKs, a clean REST API, and a CLI. Track every AI
              call with a single line of code — or ingest server-side with zero client changes.
            </p>
            <div data-reveal className="mt-8 grid grid-cols-2 gap-2 text-sm">
              {[
                "Python SDK",
                "JavaScript / TypeScript SDK",
                "REST API",
                "CLI",
                "Realtime API",
                "More languages — coming soon",
              ].map((x) => (
                <div
                  key={x}
                  className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5 text-[0.8125rem]"
                >
                  <ArrowUpRight className="size-3.5 shrink-0 text-[#14D9D3]" />
                  {x}
                </div>
              ))}
            </div>
          </div>

          <div ref={codeRef} data-reveal>
            <Tabs defaultValue="python" className="w-full">
              <div className="flex items-center justify-between overflow-hidden rounded-t-2xl border border-b-0 border-white/10 bg-[#080C14] px-4 py-2.5">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <span className="size-2 rounded-full bg-white/10" />
                  <span className="size-2 rounded-full bg-white/10" />
                  <span className="size-2 rounded-full bg-white/10" />
                </div>
                <TabsList className="h-8 border border-white/10 bg-white/[0.03]">
                  <TabsTrigger
                    value="python"
                    className="text-xs data-[state=active]:bg-[#14D9D3]/15 data-[state=active]:text-[#14D9D3]"
                  >
                    Python
                  </TabsTrigger>
                  <TabsTrigger
                    value="ts"
                    className="text-xs data-[state=active]:bg-[#14D9D3]/15 data-[state=active]:text-[#14D9D3]"
                  >
                    TypeScript
                  </TabsTrigger>
                </TabsList>
              </div>
              <TabsContent value="python" className="mt-0">
                <CodeBody code={pythonCode} />
              </TabsContent>
              <TabsContent value="ts" className="mt-0">
                <CodeBody code={tsCode} />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </div>
    </section>
  );
}

function CodeBody({ code }: { code: string }) {
  return (
    <div className="overflow-hidden rounded-b-2xl border border-t-0 border-white/10 bg-[#080C14]">
      <pre className="overflow-x-auto p-5 font-mono text-[12.5px] leading-relaxed text-foreground/85">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Security                                                                    */
/* -------------------------------------------------------------------------- */

function Security() {
  const items = [
    { icon: Shield, title: "RBAC", desc: "Granular role-based access control." },
    { icon: Building2, title: "Org isolation", desc: "Hard tenant boundaries." },
    { icon: Fingerprint, title: "Audit logs", desc: "Every action, immutable." },
    {
      icon: KeyRound,
      title: "Encrypted keys",
      desc: "Provider credentials encrypted at rest, per-connection.",
    },
    {
      icon: ShieldCheck,
      title: "One account system",
      desc: "Single, unified auth across the whole product.",
    },
    {
      icon: Lock,
      title: "Least data by default",
      desc: "We store usage metadata, not prompts or completions.",
    },
    {
      icon: Radar,
      title: "Security-first development",
      desc: "Built with modern secure-coding practices.",
    },
    { icon: Zap, title: "TLS everywhere", desc: "Encrypted in transit, end to end." },
  ];
  const gridRef = useScrollReveal<HTMLDivElement>({
    selector: "[data-reveal]",
    y: 16,
    stagger: 0.05,
  });

  return (
    <section className="border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-[80rem] px-6">
        <SectionHeading
          eyebrow="Security"
          title={<>Enterprise-grade from day one.</>}
          desc="Designed with the controls that regulated industries require — prompts and completions are never collected."
        />
        <div ref={gridRef} className="mt-14 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((s) => (
            <div
              key={s.title}
              data-reveal
              className="group rounded-2xl border border-white/[0.08] bg-white/[0.015] p-5 transition-colors hover:border-[#14D9D3]/25 hover:bg-white/[0.03]"
            >
              <span className="flex size-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] text-[#14D9D3]">
                <s.icon className="size-4.5" />
              </span>
              <div className="mt-3.5 font-display text-[0.95rem] font-semibold">{s.title}</div>
              <div className="mt-1 text-[0.8125rem] leading-relaxed text-muted-foreground">
                {s.desc}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Pricing                                                                     */
/* -------------------------------------------------------------------------- */

function Pricing() {
  const cardsRef = useScrollReveal<HTMLDivElement>({
    selector: "[data-reveal]",
    y: 22,
    stagger: 0.08,
  });

  return (
    <section className="border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-[80rem] px-6">
        <SectionHeading
          eyebrow="Pricing"
          title={<>Simple pricing that scales with you.</>}
          desc="Start free today. Team and Enterprise plans with billing are coming soon."
        />
        <div ref={cardsRef} className="mt-14 grid items-start gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {pricing.map((p) => (
            <div
              key={p.name}
              data-reveal
              className={`relative flex flex-col rounded-3xl p-7 ${
                p.highlight
                  ? "panel-glow lg:-translate-y-3"
                  : "border border-white/[0.08] bg-white/[0.015]"
              }`}
            >
              {p.highlight && (
                <span className="absolute -top-3 left-7 rounded-full bg-gradient-brand px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-primary-foreground shadow-[0_8px_20px_-8px_rgba(20,217,211,0.8)]">
                  Most popular
                </span>
              )}
              <div className="font-display text-lg font-semibold">{p.name}</div>
              <div className="mt-1 text-sm text-muted-foreground">{p.desc}</div>
              <div className="mt-6 flex items-baseline gap-1.5">
                <span className="tnum display-lg">{p.price}</span>
                {p.period && <span className="text-sm text-muted-foreground">/ {p.period}</span>}
              </div>
              <ul className="mt-7 flex flex-1 flex-col gap-3 text-sm">
                {p.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5">
                    <span
                      className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full ${
                        p.highlight
                          ? "bg-[#14D9D3] text-[#060810]"
                          : "bg-[#14D9D3]/15 text-[#14D9D3]"
                      }`}
                    >
                      <svg viewBox="0 0 12 12" className="size-2.5" fill="none">
                        <path
                          d="M2.5 6.5 5 9l4.5-5.5"
                          stroke="currentColor"
                          strokeWidth="1.6"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </span>
                    <span className="text-foreground/85">{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                to={p.name === "Starter" ? "/signup" : "/contact"}
                className={`mt-8 inline-flex items-center justify-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium transition-all ${
                  p.highlight
                    ? "btn-brand hover:scale-[1.02] hover:brightness-105 active:scale-[0.98]"
                    : "btn-ghost hover:bg-white/[0.06]"
                }`}
              >
                {p.cta}
                {p.name === "Starter" && <ArrowRight className="size-4" />}
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* FAQ                                                                         */
/* -------------------------------------------------------------------------- */

function FAQ() {
  const listRef = useScrollReveal<HTMLDivElement>({ selector: "[data-reveal]", y: 12 });
  const [openItem, setOpenItem] = useState<string | undefined>(undefined);

  return (
    <section className="border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-3xl px-6">
        <SectionHeading eyebrow="FAQ" title={<>Everything you might ask.</>} />
        <div ref={listRef} data-reveal className="mt-14">
          <Accordion
            type="single"
            collapsible
            value={openItem}
            onValueChange={setOpenItem}
            className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.015]"
          >
            {faqs.map((f, i) => (
              <AccordionItem
                key={f.q}
                value={`item-${i}`}
                className="border-white/5 px-6 last:border-b-0"
              >
                <AccordionTrigger className="py-5 text-left font-display text-[0.975rem] font-medium hover:no-underline hover:text-[#14D9D3]">
                  {f.q}
                </AccordionTrigger>
                <AccordionContent className="pb-5 text-sm leading-relaxed text-muted-foreground">
                  {f.a}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* Final CTA                                                                   */
/* -------------------------------------------------------------------------- */

function FinalCTA() {
  const revealRef = useScrollReveal<HTMLDivElement>({ selector: "[data-reveal]", y: 18 });

  return (
    <section className="relative overflow-hidden border-t border-white/5 py-28 md:py-36">
      <div className="aurora" aria-hidden="true" />
      <div className="absolute inset-0 bg-grid opacity-30 [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,black,transparent_75%)]" />
      <div ref={revealRef} className="relative mx-auto max-w-3xl px-6 text-center">
        <h2 data-reveal className="display-xl">
          Start monitoring AI costs <span className="text-gradient-brand">today</span>.
        </h2>
        <p
          data-reveal
          className="mx-auto mt-5 max-w-xl text-[0.975rem] leading-relaxed text-muted-foreground"
        >
          Free forever for individuals and small teams. No credit card required.
        </p>
        <div
          data-reveal
          className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
        >
          <Link
            to="/signup"
            className="btn-brand group px-6 py-3 text-sm hover:scale-[1.02] hover:brightness-105 active:scale-[0.98]"
          >
            Start free
            <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" />
          </Link>
          <Link to="/contact" className="btn-ghost px-6 py-3 text-sm hover:bg-white/[0.06]">
            Contact sales
          </Link>
        </div>
      </div>
    </section>
  );
}
