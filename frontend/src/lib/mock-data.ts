import type {
  OverviewKPIs,
  TimeSeriesResponse,
  ProvidersResponse,
  ModelsResponse,
  ProjectsResponse,
  OrganizationResponse,
  KPIsResponse,
  UsageEventsResponse,
  TimeSeriesPoint,
} from "../types/api";
import { toISODate, subtractDays } from "./utils";

// ── Seeded RNG ────────────────────────────────────────────────────────────────

function seededRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

const rng = seededRandom(42);
const rand = (min: number, max: number) => min + rng() * (max - min);
const randInt = (min: number, max: number) => Math.floor(rand(min, max));

// ── Providers config ──────────────────────────────────────────────────────────

const PROVIDERS = [
  { id: "openai",    name: "OpenAI",    share: 0.42 },
  { id: "anthropic", name: "Anthropic", share: 0.28 },
  { id: "google",    name: "Google",    share: 0.18 },
  { id: "azure",     name: "Azure",     share: 0.12 },
];

const MODELS = [
  { id: "gpt-4o",            provider: "openai",    costPer1kIn: 0.005,  costPer1kOut: 0.015 },
  { id: "gpt-4-turbo",       provider: "openai",    costPer1kIn: 0.01,   costPer1kOut: 0.03  },
  { id: "gpt-3.5-turbo",     provider: "openai",    costPer1kIn: 0.0005, costPer1kOut: 0.0015 },
  { id: "claude-3-5-sonnet", provider: "anthropic", costPer1kIn: 0.003,  costPer1kOut: 0.015 },
  { id: "claude-3-opus",     provider: "anthropic", costPer1kIn: 0.015,  costPer1kOut: 0.075 },
  { id: "claude-3-haiku",    provider: "anthropic", costPer1kIn: 0.00025,costPer1kOut: 0.00125 },
  { id: "gemini-pro",        provider: "google",    costPer1kIn: 0.00025,costPer1kOut: 0.0005 },
  { id: "gemini-ultra",      provider: "google",    costPer1kIn: 0.0125, costPer1kOut: 0.0375 },
  { id: "azure-gpt-4",       provider: "azure",     costPer1kIn: 0.03,   costPer1kOut: 0.06  },
  { id: "azure-gpt-35",      provider: "azure",     costPer1kIn: 0.001,  costPer1kOut: 0.002 },
];

const PROJECTS = [
  { id: "p-001", name: "AI Assistant",       team: "Platform",  budget: 8000  },
  { id: "p-002", name: "Customer Support Bot",team: "CX",       budget: 5000  },
  { id: "p-003", name: "Code Reviewer",      team: "DevTools",  budget: 3500  },
  { id: "p-004", name: "Document Parser",    team: "Data",      budget: 2000  },
  { id: "p-005", name: "Search Enhancer",    team: "Search",    budget: 4500  },
  { id: "p-006", name: "Analytics Engine",   team: "Analytics", budget: 6000  },
];

const DEPARTMENTS = [
  { id: "d-001", name: "Engineering",   teams: 4, projects: 8,  budget: 25000 },
  { id: "d-002", name: "Product",       teams: 2, projects: 5,  budget: 12000 },
  { id: "d-003", name: "Customer CX",   teams: 3, projects: 6,  budget: 18000 },
  { id: "d-004", name: "Data & Analytics", teams: 2, projects: 4, budget: 15000 },
  { id: "d-005", name: "Research",      teams: 1, projects: 3,  budget: 8000  },
];

// ── 90-day time series ────────────────────────────────────────────────────────

function generateDailyData(days = 90) {
  const today = new Date();
  const points: Array<{
    date: string;
    totalCost: number;
    totalRequests: number;
    totalTokens: number;
    byProvider: Record<string, number>;
  }> = [];

  // Trend: slight growth over 90 days
  for (let i = days - 1; i >= 0; i--) {
    const date = toISODate(subtractDays(today, i));
    const dayOfWeek = new Date(date).getDay();
    const weekendFactor = dayOfWeek === 0 || dayOfWeek === 6 ? 0.55 : 1;
    const growthFactor = 1 + (days - i) * 0.003;
    const noise = 0.8 + rng() * 0.4;

    const baseDailyCost = 450 * weekendFactor * growthFactor * noise;
    const byProvider: Record<string, number> = {};
    let total = 0;

    for (const p of PROVIDERS) {
      const pCost = baseDailyCost * p.share * (0.85 + rng() * 0.3);
      byProvider[p.id] = pCost;
      total += pCost;
    }

    points.push({
      date,
      totalCost: total,
      totalRequests: randInt(8000, 25000) * weekendFactor,
      totalTokens: randInt(5_000_000, 15_000_000) * weekendFactor,
      byProvider,
    });
  }
  return points;
}

const DAILY_DATA = generateDailyData(90);

// ── Overview KPIs ─────────────────────────────────────────────────────────────

export function getMockOverview(startDate: string, endDate: string): OverviewKPIs {
  const filtered = DAILY_DATA.filter((d) => d.date >= startDate && d.date <= endDate);
  const prev = DAILY_DATA.filter((d) => {
    const start = new Date(startDate);
    const end = new Date(endDate);
    const diff = end.getTime() - start.getTime();
    const prevStart = toISODate(new Date(start.getTime() - diff));
    return d.date >= prevStart && d.date < startDate;
  });

  const total = filtered.reduce((s, d) => s + d.totalCost, 0);
  const prevTotal = prev.reduce((s, d) => s + d.totalCost, 0);
  const totalRequests = filtered.reduce((s, d) => s + d.totalRequests, 0);
  const prevRequests = prev.reduce((s, d) => s + d.totalRequests, 0);
  const totalTokens = filtered.reduce((s, d) => s + d.totalTokens, 0);
  const prevTokens = prev.reduce((s, d) => s + d.totalTokens, 0);

  const pct = (a: number, b: number) => (b > 0 ? ((a - b) / b) * 100 : 0);

  return {
    total_cost: total.toFixed(4),
    total_requests: totalRequests,
    active_models: 10,
    active_providers: 4,
    total_input_tokens: Math.round(totalTokens * 0.7),
    total_output_tokens: Math.round(totalTokens * 0.3),
    avg_cost_per_request: totalRequests > 0 ? (total / totalRequests).toFixed(6) : "0",
    cost_trend_pct: parseFloat(pct(total, prevTotal).toFixed(1)),
    request_trend_pct: parseFloat(pct(totalRequests, prevRequests).toFixed(1)),
    token_trend_pct: parseFloat(pct(totalTokens, prevTokens).toFixed(1)),
    currency: "USD",
    period_start: startDate,
    period_end: endDate,
  };
}

// ── Time Series ───────────────────────────────────────────────────────────────

export function getMockTimeSeries(
  startDate: string,
  endDate: string,
  granularity = "daily",
): TimeSeriesResponse {
  const filtered = DAILY_DATA.filter((d) => d.date >= startDate && d.date <= endDate);

  let points: TimeSeriesPoint[];

  if (granularity === "daily") {
    points = filtered.map((d) => ({
      date: d.date,
      total_cost: d.totalCost.toFixed(4),
      total_requests: Math.round(d.totalRequests),
      total_tokens: Math.round(d.totalTokens),
      provider_breakdown: Object.fromEntries(
        Object.entries(d.byProvider).map(([k, v]) => [k, v.toFixed(4)]),
      ),
    }));
  } else if (granularity === "weekly") {
    const weeks = new Map<string, typeof filtered>();
    for (const d of filtered) {
      const day = new Date(d.date);
      const monday = new Date(day);
      monday.setDate(day.getDate() - ((day.getDay() + 6) % 7));
      const key = toISODate(monday);
      if (!weeks.has(key)) weeks.set(key, []);
      weeks.get(key)!.push(d);
    }
    points = Array.from(weeks.entries()).map(([date, days]) => ({
      date,
      total_cost: days.reduce((s, d) => s + d.totalCost, 0).toFixed(4),
      total_requests: Math.round(days.reduce((s, d) => s + d.totalRequests, 0)),
      total_tokens: Math.round(days.reduce((s, d) => s + d.totalTokens, 0)),
      provider_breakdown: Object.fromEntries(
        PROVIDERS.map((p) => [
          p.id,
          days.reduce((s, d) => s + (d.byProvider[p.id] ?? 0), 0).toFixed(4),
        ]),
      ),
    }));
  } else {
    // monthly
    const months = new Map<string, typeof filtered>();
    for (const d of filtered) {
      const key = d.date.slice(0, 7) + "-01";
      if (!months.has(key)) months.set(key, []);
      months.get(key)!.push(d);
    }
    points = Array.from(months.entries()).map(([date, days]) => ({
      date,
      total_cost: days.reduce((s, d) => s + d.totalCost, 0).toFixed(4),
      total_requests: Math.round(days.reduce((s, d) => s + d.totalRequests, 0)),
      total_tokens: Math.round(days.reduce((s, d) => s + d.totalTokens, 0)),
      provider_breakdown: Object.fromEntries(
        PROVIDERS.map((p) => [
          p.id,
          days.reduce((s, d) => s + (d.byProvider[p.id] ?? 0), 0).toFixed(4),
        ]),
      ),
    }));
  }

  return { data: points, granularity: granularity as never, currency: "USD" };
}

// ── Providers ─────────────────────────────────────────────────────────────────

export function getMockProviders(startDate: string, endDate: string): ProvidersResponse {
  const filtered = DAILY_DATA.filter((d) => d.date >= startDate && d.date <= endDate);
  const totals = new Map<string, number>();
  for (const d of filtered) {
    for (const [pid, cost] of Object.entries(d.byProvider)) {
      totals.set(pid, (totals.get(pid) ?? 0) + cost);
    }
  }
  const grandTotal = Array.from(totals.values()).reduce((s, v) => s + v, 0);

  return {
    providers: PROVIDERS.map((p) => {
      const cost = totals.get(p.id) ?? 0;
      return {
        provider: p.id,
        total_cost: cost.toFixed(4),
        request_count: randInt(5000, 50000),
        model_count: MODELS.filter((m) => m.provider === p.id).length,
        input_tokens: randInt(2_000_000, 10_000_000),
        output_tokens: randInt(500_000, 3_000_000),
        cost_share_pct: parseFloat(((cost / grandTotal) * 100).toFixed(1)),
      };
    }),
    currency: "USD",
  };
}

// ── Models ────────────────────────────────────────────────────────────────────

export function getMockModels(startDate: string, endDate: string): ModelsResponse {
  const days = DAILY_DATA.filter((d) => d.date >= startDate && d.date <= endDate).length;
  return {
    models: MODELS.map((m) => {
      const requests = randInt(1000, 20000) * days / 30;
      const inputTokens = requests * randInt(500, 2000);
      const outputTokens = requests * randInt(100, 800);
      const cost = (inputTokens / 1000) * m.costPer1kIn + (outputTokens / 1000) * m.costPer1kOut;
      return {
        model_id: m.id,
        provider: m.provider,
        display_name: m.id,
        total_cost: cost.toFixed(4),
        request_count: Math.round(requests),
        input_tokens: Math.round(inputTokens),
        output_tokens: Math.round(outputTokens),
        avg_cost_per_request: (cost / requests).toFixed(6),
        cost_per_1k_tokens: (cost / ((inputTokens + outputTokens) / 1000)).toFixed(6),
      };
    }),
    currency: "USD",
  };
}

// ── Projects ──────────────────────────────────────────────────────────────────

export function getMockProjects(): ProjectsResponse {
  return {
    projects: PROJECTS.map((p, i) => {
      const utilPct = 35 + i * 12 + randInt(-5, 15);
      const cost = (p.budget * utilPct) / 100;
      const trendData = Array.from({ length: 7 }, () =>
        (cost / 7 * (0.7 + rng() * 0.6)).toFixed(2),
      );
      return {
        project_id: p.id,
        project_name: p.name,
        team: p.team,
        total_cost: cost.toFixed(2),
        budget: p.budget.toFixed(2),
        budget_utilization_pct: Math.min(parseFloat(utilPct.toFixed(1)), 120),
        request_count: randInt(500, 8000),
        top_models: MODELS.slice(i % 3, (i % 3) + 2).map((m) => m.id),
        cost_trend: parseFloat((rand(-15, 25)).toFixed(1)),
        trend_data: trendData,
      };
    }),
    currency: "USD",
  };
}

// ── Organization ──────────────────────────────────────────────────────────────

export function getMockOrganization(): OrganizationResponse {
  let totalCost = 0;
  let totalBudget = 0;
  const departments = DEPARTMENTS.map((d) => {
    const utilPct = 40 + randInt(0, 55);
    const cost = (d.budget * utilPct) / 100;
    totalCost += cost;
    totalBudget += d.budget;
    return {
      department_id: d.id,
      department_name: d.name,
      total_cost: cost.toFixed(2),
      budget: d.budget.toFixed(2),
      budget_utilization_pct: parseFloat(utilPct.toFixed(1)),
      team_count: d.teams,
      project_count: d.projects,
      request_count: randInt(5000, 50000),
    };
  });
  return {
    departments,
    total_cost: totalCost.toFixed(2),
    total_budget: totalBudget.toFixed(2),
    currency: "USD",
  };
}

// ── KPIs ──────────────────────────────────────────────────────────────────────

export function getMockKPIs(): KPIsResponse {
  const today = toISODate(new Date());
  const start30 = toISODate(subtractDays(new Date(), 30));
  const overview = getMockOverview(start30, today);
  return {
    kpis: [
      {
        key: "total_cost_30d",
        label: "30-Day Spend",
        value: overview.total_cost,
        unit: "USD",
        trend_pct: overview.cost_trend_pct,
        trend_direction: overview.cost_trend_pct > 0 ? "up" : "down",
      },
      {
        key: "avg_cost_per_req",
        label: "Avg Cost / Request",
        value: overview.avg_cost_per_request,
        unit: "USD",
        trend_pct: -4.2,
        trend_direction: "down",
      },
      {
        key: "total_tokens",
        label: "Total Tokens",
        value: String(overview.total_input_tokens + overview.total_output_tokens),
        unit: "tokens",
        trend_pct: overview.token_trend_pct,
        trend_direction: overview.token_trend_pct > 0 ? "up" : "down",
      },
    ],
    currency: "USD",
    as_of: today,
  };
}

// ── Recent activity ───────────────────────────────────────────────────────────

const SAMPLE_ORGS = ["Acme Corp", "DataCo", "TechHub", "CloudOps"];
const SAMPLE_PROJECTS_NAMES = PROJECTS.map((p) => p.name);

export function getMockRecentActivity(limit = 20): UsageEventsResponse {
  const now = new Date();
  const events = Array.from({ length: limit }, (_, i) => {
    const model = MODELS[randInt(0, MODELS.length)] ?? MODELS[0]!;
    const inputTokens = randInt(200, 4000);
    const outputTokens = randInt(50, 1500);
    const cost =
      (inputTokens / 1000) * model.costPer1kIn +
      (outputTokens / 1000) * model.costPer1kOut;
    const ts = new Date(now.getTime() - i * randInt(30_000, 600_000));
    return {
      id: `evt-${String(i + 1).padStart(5, "0")}`,
      timestamp: ts.toISOString(),
      provider: model.provider,
      model_id: model.id,
      organization_name: SAMPLE_ORGS[randInt(0, SAMPLE_ORGS.length)] ?? "Unknown Org",
      project_name: SAMPLE_PROJECTS_NAMES[randInt(0, SAMPLE_PROJECTS_NAMES.length)] ?? "Unknown Project",
      input_tokens: inputTokens,
      output_tokens: outputTokens,
      total_tokens: inputTokens + outputTokens,
      cost: cost.toFixed(6),
      currency: "USD" as const,
    };
  });
  return { events, total: limit * 10, page: 1, page_size: limit };
}
