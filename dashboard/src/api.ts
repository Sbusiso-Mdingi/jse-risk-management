export type Summary = { start: string; end: string; sessions: number; cagr: number | null; vol: number; sharpe: number | null; mdd: number };
export type Period = "design" | "validation" | "live";
export type RuleId = "R0" | "R1" | "R2" | "R3" | "R4" | "R5";
export type Rule = { label: string; window?: number; turnover_per_month?: number } & Partial<Record<Period, Summary>>;
export type Coverage = { exceedances: number; expected: number; p_value: number; p_cc: number; p_ind: number; clustered: number };
export type ModelTest = {
  var99: Coverage;
  var975: Coverage;
  traffic_light: { green: number; yellow: number; red: number; latest: number; latest_zone: string };
  es975_z2: number;
  mean_var99: number;
  passed: boolean;
};
export type ModelId = "historical" | "normal" | "ewma" | "fhs";
export type VarSeries = { date: string[]; r: number[]; tests: Record<ModelId, ModelTest> } & Record<ModelId, number[]>;
export type HistScenario = {
  key: string;
  label: string;
  start: string;
  end: string;
  index_return: number;
  portfolio_return: number;
  proxied: string[];
  proxied_weight: number;
  worst: { ticker: string; return: number; contribution: number }[];
};
export type HypoScenario = { key: string; label: string; var99_before?: number; var99_after?: number; portfolio_return?: number; rand_beta?: number };
export type Stress = { historical: HistScenario[]; hypothetical: HypoScenario[] };
export type Test = { id: string; claim: string; verdict: string; best?: string; detail: Record<string, unknown> };

export type Research = {
  generated: string;
  freeze: string;
  data_end: string;
  latest_rebalance: string;
  periods: Record<Period, [string, string]>;
  costs: { buy: number; sell: number };
  rules: Record<RuleId | "STX40", Rule>;
  tests: Test[];
  vs_stx40: Record<RuleId, { diff_annual: number; t_stat: number }>;
  curves: { date: string[] } & Record<RuleId | "STX40", number[]>;
  var: Record<"R1" | "R3" | "STX40", VarSeries>;
  var_labels: Record<ModelId, string>;
  stress: Record<RuleId, Stress>;
  books: Record<RuleId, { date: string; cost: number; weights: Record<string, number> }[]>;
  universe: { ticker: string; name: string }[];
  all_tickers: { ticker: string; name: string }[];
};

export type Live = { date: string[]; growth: Record<RuleId | "STX40", number[]>; freeze: string; missing: string[]; error: string | null };

export type Holding = { ticker: string; weight: number; risk: number; ret: number; vol: number };
export type PortfolioResult = {
  as_of: string;
  rule: RuleId;
  window: number;
  cap: number;
  rf: number;
  weights: Holding[];
  excluded: Record<string, string>;
  expected_return: number;
  vol: number;
  sharpe: number;
  frontier: { ret: number; vol: number }[];
  history_sessions: number;
  var: Partial<Record<ModelId, { var99: number; var975: number; es975: number }>>;
  stress: Stress;
  fetch_errors: Record<string, string>;
  error?: string;
};

const get = async <T,>(path: string): Promise<T> => {
  const r = await fetch(path);
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail ?? `${r.status} ${r.statusText}`);
  }
  return r.json();
};

export const api = {
  research: () => get<Research>("/api/research"),
  live: () => get<Live>("/api/live"),
  portfolio: (tickers: string[], rule: RuleId, window: number, cap: number) =>
    get<PortfolioResult>(
      `/api/portfolio?tickers=${encodeURIComponent(tickers.join(","))}&rule=${rule}&window=${window}&cap=${cap}`,
    ),
};
