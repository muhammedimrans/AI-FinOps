import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "motion/react";
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
  BarChart3,
  Bell,
  Boxes,
  Building2,
  ChevronDown,
  Cpu,
  Database,
  Fingerprint,
  Gauge,
  GitBranch,
  KeyRound,
  Layers,
  LineChart as LineIcon,
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

export const Route = createFileRoute("/")({
  component: Landing,
});

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
      <SocialProof />
      <LiveDashboard />
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
/* Sections                                                                    */
/* -------------------------------------------------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="absolute inset-0 bg-grid opacity-40 [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" />
      <div className="absolute inset-0" style={{ background: "var(--gradient-hero)" }} />
      <div className="relative mx-auto max-w-7xl px-6 pb-24 pt-20 md:pb-32 md:pt-28">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="mx-auto max-w-3xl text-center"
        >
          <div className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-muted-foreground">
            <Sparkles className="h-3 w-3 text-[#14D9D3]" />
            AI FinOps, redefined
          </div>
          <h1 className="font-display text-5xl font-semibold tracking-tight md:text-7xl">
            Understand Every <span className="text-gradient-brand">AI Dollar</span>.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base text-muted-foreground md:text-lg">
            Monitor OpenAI, Anthropic, Google, Azure OpenAI, Grok, OpenRouter, Ollama, and every AI
            provider from one unified platform.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              to="/signup"
              className="inline-flex items-center justify-center gap-2 rounded-full bg-gradient-brand px-6 py-3 text-sm font-medium text-primary-foreground shadow-[0_10px_40px_-10px_rgba(20,217,211,0.6)] transition-transform hover:scale-[1.02]"
            >
              Start Free <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="/contact"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-6 py-3 text-sm font-medium text-foreground hover:bg-white/[0.06]"
            >
              Book Demo
            </Link>
          </div>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-[#14D9D3]" /> Encrypted credentials
            </span>
            <span className="flex items-center gap-1.5">
              <Lock className="h-3.5 w-3.5 text-[#14D9D3]" /> Zero-latency ingest
            </span>
            <span className="flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5 text-[#14D9D3]" /> 10-minute setup
            </span>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.15, ease: "easeOut" }}
          className="relative mx-auto mt-16 max-w-6xl"
        >
          <HeroIllustration />
        </motion.div>
      </div>
    </section>
  );
}

function HeroIllustration() {
  return (
    <div className="relative rounded-3xl border border-white/10 bg-[#0C1117]/80 p-4 shadow-[0_40px_120px_-40px_rgba(20,217,211,0.35)] backdrop-blur md:p-6">
      <div className="flex items-center gap-2 border-b border-white/5 px-2 pb-3">
        <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
        <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
        <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
        <span className="ml-3 text-xs text-muted-foreground">app.costorah.com</span>
        <span className="ml-auto text-[10px] uppercase tracking-widest text-[#14D9D3]">Live</span>
      </div>
      <div className="grid gap-4 pt-4 md:grid-cols-3">
        <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
          <div className="text-xs text-muted-foreground">This month</div>
          <div className="mt-2 font-display text-3xl font-semibold">$48,392</div>
          <div className="mt-1 text-xs text-[#14D9D3]">↓ 18% vs last month</div>
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
                <Tooltip
                  contentStyle={{
                    background: "#0C1117",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                />
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

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function SocialProof() {
  return (
    <section className="border-y border-white/5 bg-white/[0.01] py-14">
      <div className="mx-auto max-w-7xl px-6">
        <div className="text-center text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Trusted AI Infrastructure
        </div>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-8 gap-y-4">
          {providers.map((p) => (
            <span
              key={p}
              className="rounded-full border border-white/10 bg-white/[0.02] px-4 py-1.5 text-sm text-foreground/70"
            >
              {p}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function LiveDashboard() {
  return (
    <section className="relative py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Live dashboard"
          title="See your AI economy in real time."
          desc="Every provider, every model, every project — normalized, correlated, and streamed live."
        />
        <div className="mt-14 grid gap-4 lg:grid-cols-6">
          <StatCard icon={Wallet} label="Spend today" value="$3,284" trend="+4.2%" />
          <StatCard icon={Activity} label="Requests" value="1.2M" trend="+11%" />
          <StatCard icon={Cpu} label="Tokens" value="284M" trend="+6%" />
          <StatCard icon={Gauge} label="Avg latency" value="612ms" trend="-8%" positive />
          <StatCard icon={Radar} label="Anomalies" value="3" trend="live" positive />
          <StatCard icon={Users} label="Active users" value="94" trend="+2" />

          <div className="rounded-2xl border border-white/10 bg-[#0C1117] p-5 lg:col-span-4">
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
                  <Tooltip
                    contentStyle={{
                      background: "#0C1117",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 12,
                      fontSize: 12,
                    }}
                  />
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

          <div className="rounded-2xl border border-white/10 bg-[#0C1117] p-5 lg:col-span-2">
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
                  <Tooltip
                    contentStyle={{
                      background: "#0C1117",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 12,
                      fontSize: 12,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 space-y-1.5">
              {pieData.map((p, i) => (
                <div key={p.name} className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: pieColors[i] }} />
                    {p.name}
                  </span>
                  <span className="text-muted-foreground">{p.value}%</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-[#0C1117] p-5 lg:col-span-3">
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
                  <Tooltip
                    contentStyle={{
                      background: "#0C1117",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 12,
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="v" fill="#14D9D3" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-[#0C1117] p-5 lg:col-span-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-muted-foreground">Live activity</div>
                <div className="mt-1 font-display text-lg font-semibold">Streaming events</div>
              </div>
              <span className="flex items-center gap-2 text-xs text-[#14D9D3]">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inset-0 animate-ping rounded-full bg-[#14D9D3] opacity-60" />
                  <span className="relative h-2 w-2 rounded-full bg-[#14D9D3]" />
                </span>
                Live
              </span>
            </div>
            <div className="mt-4 space-y-2">
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
                    <span>{r.t}</span>
                    <span className="text-foreground">{r.c}</span>
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
    <div className="rounded-2xl border border-white/10 bg-[#0C1117] p-5">
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">{label}</div>
        <Icon className="h-4 w-4 text-[#14D9D3]" />
      </div>
      <div className="mt-2 font-display text-2xl font-semibold">{value}</div>
      <div className={`mt-1 text-xs ${positive ? "text-[#14D9D3]" : "text-muted-foreground"}`}>
        {trend}
      </div>
    </div>
  );
}

function Features() {
  return (
    <section className="relative border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Platform"
          title="Every capability a modern AI team needs."
          desc="From ingestion to forecasting — one focused platform for FinOps, platform, and finance teams."
        />
        <div className="mt-14 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.35, delay: (i % 4) * 0.05 }}
              className="group relative overflow-hidden rounded-2xl border border-white/10 bg-[#0C1117] p-5 transition-colors hover:border-[#14D9D3]/30"
            >
              <div
                className="absolute inset-0 opacity-0 transition-opacity group-hover:opacity-100"
                style={{
                  background:
                    "radial-gradient(600px circle at var(--x,50%) var(--y,50%), rgba(20,217,211,0.06), transparent 40%)",
                }}
              />
              <div className="relative">
                <div className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-[#14D9D3]/10 text-[#14D9D3]">
                  <f.icon className="h-4.5 w-4.5" />
                </div>
                <div className="mt-4 font-display text-base font-semibold">{f.title}</div>
                <div className="mt-1 text-sm text-muted-foreground">{f.desc}</div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section className="relative border-t border-white/5 py-24 md:py-32">
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{ background: "var(--gradient-mesh)" }}
      />
      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="How it works"
          title="Five steps to AI cost clarity."
          desc="From first connection to automated forecasts — Costorah is designed to fit into the workflow you already have."
        />
        <div className="mt-14 grid gap-5 md:grid-cols-5">
          {steps.map((s, i) => (
            <div
              key={s.title}
              className="relative rounded-2xl border border-white/10 bg-[#0C1117] p-6"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-brand font-display text-sm font-semibold text-primary-foreground">
                  {i + 1}
                </div>
                <s.icon className="h-4 w-4 text-[#14D9D3]" />
              </div>
              <div className="mt-4 font-display text-base font-semibold">{s.title}</div>
              <div className="mt-1 text-sm text-muted-foreground">{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Developers() {
  return (
    <section className="border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-muted-foreground">
              <LineIcon className="h-3 w-3 text-[#14D9D3]" /> Built for developers
            </div>
            <h2 className="mt-5 font-display text-4xl font-semibold tracking-tight md:text-5xl">
              Ship in minutes. <br />
              <span className="text-gradient-brand">Instrument once.</span>
            </h2>
            <p className="mt-5 max-w-lg text-muted-foreground">
              Python and JavaScript/TypeScript SDKs, a clean REST API, and a CLI. Track every AI
              call with a single line of code — or ingest server-side with zero client changes.
            </p>
            <div className="mt-8 grid grid-cols-2 gap-2 text-sm">
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
                  className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-[#14D9D3]" />
                  {x}
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-4">
            <CodeBlock
              lang="python"
              title="track.py"
              code={`from costorah import Costorah

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
)`}
            />
            <CodeBlock
              lang="typescript"
              title="track.ts"
              code={`import { Costorah } from "costorah";

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
});`}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function CodeBlock({ lang, title, code }: { lang: string; title: string; code: string }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#0C1117]">
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-2 text-xs">
        <div className="flex items-center gap-2 text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-white/10" />
          <span className="h-2 w-2 rounded-full bg-white/10" />
          <span className="h-2 w-2 rounded-full bg-white/10" />
          <span className="ml-2 font-mono">{title}</span>
        </div>
        <span className="rounded-md bg-[#14D9D3]/10 px-2 py-0.5 font-mono text-[10px] uppercase text-[#14D9D3]">
          {lang}
        </span>
      </div>
      <pre className="overflow-x-auto p-5 font-mono text-[12.5px] leading-relaxed text-foreground/85">
        <code>{code}</code>
      </pre>
    </div>
  );
}

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
  return (
    <section className="border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Security"
          title="Enterprise-grade from day one."
          desc="Designed with the controls that regulated industries require — and audited to prove it."
        />
        <div className="mt-14 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((s) => (
            <div key={s.title} className="rounded-2xl border border-white/10 bg-[#0C1117] p-5">
              <s.icon className="h-5 w-5 text-[#14D9D3]" />
              <div className="mt-3 font-display text-base font-semibold">{s.title}</div>
              <div className="mt-1 text-sm text-muted-foreground">{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Pricing() {
  return (
    <section className="border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Pricing"
          title="Simple pricing that scales with you."
          desc="Start free today. Team and Enterprise plans with billing are coming soon."
        />
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {pricing.map((p) => (
            <div
              key={p.name}
              className={`relative flex flex-col rounded-2xl border p-6 ${
                p.highlight
                  ? "border-[#14D9D3]/40 bg-gradient-to-b from-[#14D9D3]/10 to-transparent shadow-[0_0_60px_-20px_rgba(20,217,211,0.5)]"
                  : "border-white/10 bg-[#0C1117]"
              }`}
            >
              {p.highlight && (
                <span className="absolute -top-2.5 right-6 rounded-full bg-gradient-brand px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary-foreground">
                  Popular
                </span>
              )}
              <div className="font-display text-lg font-semibold">{p.name}</div>
              <div className="mt-1 text-sm text-muted-foreground">{p.desc}</div>
              <div className="mt-6 flex items-baseline gap-1">
                <span className="font-display text-4xl font-semibold">{p.price}</span>
                {p.period && <span className="text-sm text-muted-foreground">{p.period}</span>}
              </div>
              <ul className="mt-6 flex-1 space-y-2.5 text-sm">
                {p.features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#14D9D3]" />
                    <span className="text-foreground/85">{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                to={p.name === "Starter" ? "/signup" : "/contact"}
                className={`mt-8 inline-flex items-center justify-center rounded-full px-4 py-2.5 text-sm font-medium ${
                  p.highlight
                    ? "bg-gradient-brand text-primary-foreground"
                    : "border border-white/10 bg-white/[0.03] text-foreground hover:bg-white/[0.06]"
                }`}
              >
                {p.cta}
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FAQ() {
  return (
    <section className="border-t border-white/5 py-24 md:py-32">
      <div className="mx-auto max-w-4xl px-6">
        <SectionHeader eyebrow="FAQ" title="Everything you might ask." />
        <div className="mt-14 divide-y divide-white/5 rounded-2xl border border-white/10 bg-[#0C1117]">
          {faqs.map((f) => (
            <details
              key={f.q}
              className="group px-6 py-5 [&_summary::-webkit-details-marker]:hidden"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
                <span className="font-display text-base font-medium">{f.q}</span>
                <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
              </summary>
              <p className="mt-3 text-sm text-muted-foreground">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCTA() {
  return (
    <section className="relative overflow-hidden border-t border-white/5 py-24 md:py-32">
      <div className="absolute inset-0" style={{ background: "var(--gradient-hero)" }} />
      <div className="relative mx-auto max-w-4xl px-6 text-center">
        <h2 className="font-display text-4xl font-semibold tracking-tight md:text-6xl">
          Start monitoring AI costs <span className="text-gradient-brand">today</span>.
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-muted-foreground">
          Free forever for individuals and small teams. No credit card required.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            to="/signup"
            className="inline-flex items-center justify-center gap-2 rounded-full bg-gradient-brand px-6 py-3 text-sm font-medium text-primary-foreground shadow-[0_10px_40px_-10px_rgba(20,217,211,0.6)]"
          >
            Start Free <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/contact"
            className="inline-flex items-center justify-center rounded-full border border-white/10 bg-white/[0.03] px-6 py-3 text-sm font-medium hover:bg-white/[0.06]"
          >
            Contact Sales
          </Link>
        </div>
      </div>
    </section>
  );
}

function SectionHeader({
  eyebrow,
  title,
  desc,
}: {
  eyebrow?: string;
  title: string;
  desc?: string;
}) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      {eyebrow && (
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-[#14D9D3]" />
          {eyebrow}
        </div>
      )}
      <h2 className="mt-5 font-display text-3xl font-semibold tracking-tight md:text-5xl">
        {title}
      </h2>
      {desc && <p className="mx-auto mt-4 max-w-xl text-muted-foreground">{desc}</p>}
    </div>
  );
}
