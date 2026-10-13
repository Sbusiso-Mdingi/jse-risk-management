import { useEffect, useMemo, useState } from "react";
import { api, type Live, type ModelId, type PortfolioResult, type Research, type RuleId, type Summary } from "./api";
import { FrontierChart, GrowthChart, VarChart, type Line } from "./charts";
import { fmtDate, num, pct, short } from "./format";

type Tab = "backtest" | "risk" | "stress" | "build" | "method";
type PeriodKey = "design" | "validation" | "live" | "all";

const RULES: { id: RuleId; label: string; sub: string }[] = [
  { id: "R0", label: "Original app", sub: "best of 5,000 random weights" },
  { id: "R1", label: "Equal weight", sub: "1/N" },
  { id: "R2", label: "Inverse volatility", sub: "1 / σ" },
  { id: "R3", label: "Minimum variance", sub: "shrunk Σ, 10% cap" },
  { id: "R4", label: "Equal risk", sub: "risk parity" },
  { id: "R5", label: "Maximum Sharpe", sub: "shrunk Σ, 10% cap" },
];
const ruleLabel = (id: string) => RULES.find((r) => r.id === id)?.label ?? (id === "STX40" ? "Satrix 40" : id);
const MODELS: ModelId[] = ["fhs", "historical", "normal", "ewma"];
const VAR_PORTFOLIOS = [
  { id: "R1", label: "Equal weight" },
  { id: "R3", label: "Minimum variance" },
  { id: "STX40", label: "Satrix 40" },
] as const;
const ORIGINAL_DEFAULT = ["NPN.JO", "BTI.JO", "SOL.JO"];

function Metric({ value, label, sub, neg }: { value: string; label: string; sub?: string; neg?: boolean }) {
  return (
    <div className="metric">
      <div className={`value${neg ? " neg" : ""}`}>{value}</div>
      <div className="label">{label}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

function Verdict({ text }: { text: string }) {
  const tone = text.startsWith("Failed") ? "fail" : text.includes("noise") ? "noise" : "pass";
  return <span className={`verdict ${tone}`}>{text}</span>;
}

function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  className,
}: {
  options: { id: T; label: string; sub?: string }[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
}) {
  return (
    <div className={`segmented ${className ?? ""}`}>
      {options.map((o) => (
        <button key={String(o.id)} aria-pressed={o.id === value} onClick={() => onChange(o.id)}>
          {o.label}
          {o.sub && <span>{o.sub}</span>}
        </button>
      ))}
    </div>
  );
}

export function App({ embedded }: { embedded: boolean }) {
  const [research, setResearch] = useState<Research | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(location.search).get("tab") as Tab) || "backtest");

  useEffect(() => {
    api.research().then(setResearch, (e) => setError(String(e)));
    const loadLive = () => api.live().then(setLive, () => setTimeout(loadLive, 15000));
    loadLive();
  }, []);

  if (error) return <div className="preview loading">Could not load the research results: {error}</div>;
  if (!research) return <div className="preview loading">Loading results…</div>;

  return (
    <div className="preview">
      <header className="head">
        <div>
          <p className="eyebrow">Live preview · JSE portfolio risk</p>
          <h1 className="serif">
            Six ways to weight JSE shares, <em>tested out of sample</em>
          </h1>
          <p className="lede">
            A rebuild of my 2024 portfolio optimisation app. The original chose the best of 5,000 random weightings and scored it on the same data
            it was chosen on. Here every rule sets its weights at a month end and is judged on the month that follows, after trading costs and
            transfer tax. The rules, tests and pass marks were written down before any result was seen.
          </p>
        </div>
        <div className="status">
          <span>
            <i className={`dot${live ? "" : " stale"}`} />
            {live ? `Live prices to ${fmtDate(live.date[live.date.length - 1] ?? research.data_end)}` : "Loading live prices"}
          </span>
          <span>Frozen {fmtDate(research.freeze)}</span>
          <span>Last rebalance {fmtDate(research.latest_rebalance)}</span>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {(
          [
            ["backtest", "Backtest"],
            ["risk", "Risk models"],
            ["stress", "Stress tests"],
            ["build", "Build a portfolio"],
            ["method", "Method"],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </nav>

      {tab === "backtest" && <Backtest research={research} live={live} />}
      {tab === "risk" && <RiskModels research={research} />}
      {tab === "stress" && <StressTab research={research} />}
      {tab === "build" && <Build research={research} />}
      {tab === "method" && <Method research={research} />}

      <p className="footer-note">
        Backtests on Yahoo Finance prices of shares still listed in 2024, so delisted firms are missing and absolute returns are biased upwards.
        Research output, not investment advice.{embedded ? "" : " Source: github.com/Sbusiso-Mdingi/jse-risk-management."}
      </p>
    </div>
  );
}

function rebase(dates: string[], values: number[], a: string, b: string) {
  const idx = dates.map((d, i) => [d, i] as const).filter(([d]) => d >= a && d <= b).map(([, i]) => i);
  if (!idx.length) return { dates: [] as string[], values: [] as number[] };
  const i0 = Math.max(0, idx[0] - 1);
  const base = values[i0];
  return { dates: idx.map((i) => dates[i]), values: idx.map((i) => values[i] / base) };
}

function Backtest({ research, live }: { research: Research; live: Live | null }) {
  const [rule, setRule] = useState<RuleId>("R0");
  const [period, setPeriod] = useState<PeriodKey>("validation");
  const P = research.periods;

  const chart = useMemo(() => {
    const keys = [...RULES.map((r) => r.id), "STX40"] as (RuleId | "STX40")[];
    if (period === "live") {
      if (!live) return null;
      return {
        dates: live.date,
        lines: keys.map((k) => ({
          key: k,
          label: ruleLabel(k),
          values: live.growth[k],
          tone: k === rule ? "main" : k === "STX40" ? "bench" : "other",
        })) as Line[],
      };
    }
    const [a, b] = period === "all" ? ["2009-01-06", "2100-01-01"] : P[period];
    let dates: string[] = [];
    const lines = keys.map((k) => {
      const r = rebase(research.curves.date, research.curves[k], a, b);
      dates = r.dates;
      return { key: k, label: ruleLabel(k), values: r.values, tone: k === rule ? "main" : k === "STX40" ? "bench" : "other" } as Line;
    });
    return { dates, lines };
  }, [research, live, rule, period, P]);

  const stats = (k: RuleId | "STX40"): Summary | null => {
    if (period === "all" || period === "live") {
      if (period === "live") {
        if (!live) return null;
        const g = live.growth[k];
        return g.length ? { start: live.date[0], end: live.date[live.date.length - 1], sessions: g.length, cagr: g[g.length - 1] - 1, vol: NaN, sharpe: null, mdd: Math.min(0, ...g.map((v, i) => v / Math.max(...g.slice(0, i + 1), 1) - 1)) } : null;
      }
      return null;
    }
    return research.rules[k][period] ?? null;
  };
  const s = stats(rule);
  const b = stats("STX40");
  const turnover = research.rules[rule].turnover_per_month;
  const periodLabel: Record<PeriodKey, string> = {
    design: "Design 2008 to 2016",
    validation: "Validation 2017 to Sep 2026",
    live: "Live since 1 Oct 2026",
    all: "Whole record",
  };

  return (
    <>
      <div className="controls">
        <div className="control wide">
          <span className="label">Rule</span>
          <Segmented className="rule-switch" options={RULES} value={rule} onChange={setRule} />
        </div>
        <div className="control wide">
          <span className="label">Period</span>
          <Segmented
            options={(["validation", "design", "live", "all"] as PeriodKey[]).map((p) => ({ id: p, label: periodLabel[p] }))}
            value={period}
            onChange={setPeriod}
          />
        </div>
      </div>

      {period === "live" ? (
        <div className="metrics">
          <Metric value={s ? pct(s.cagr, 2) : "…"} label="Return since freeze" sub="not annualised" neg={(s?.cagr ?? 0) < 0} />
          <Metric value={b ? pct(b.cagr, 2) : "…"} label="Satrix 40" sub="same days" neg={(b?.cagr ?? 0) < 0} />
          <Metric value={s ? String(s.sessions) : "…"} label="Sessions" sub="too few to judge" />
          <Metric value={s ? pct(s.mdd, 1) : "…"} label="Max drawdown" neg />
        </div>
      ) : period === "all" ? (
        <div className="metrics">
          <Metric value={pct(research.rules[rule].validation?.cagr)} label="Validation CAGR" />
          <Metric value={pct(research.rules[rule].design?.cagr)} label="Design CAGR" />
          <Metric value={num(research.rules[rule].validation?.sharpe)} label="Validation Sharpe" />
          <Metric value={num(research.rules.STX40.validation?.sharpe)} label="Satrix 40 Sharpe" sub="validation" />
        </div>
      ) : (
        s && (
          <div className="metrics">
            <Metric value={pct(s.cagr)} label="CAGR, after costs" neg={(s.cagr ?? 0) < 0} />
            <Metric value={pct(s.vol)} label="Volatility" />
            <Metric value={num(s.sharpe)} label="Sharpe" sub={b ? `Satrix 40: ${num(b.sharpe)}` : undefined} neg={(s.sharpe ?? 0) < 0} />
            <Metric value={pct(s.mdd)} label="Max drawdown" neg />
            <Metric value={turnover != null ? pct(turnover, 0) : "n/a"} label="Turnover a month" sub="one way" />
          </div>
        )
      )}

      <section className="panel">
        <div className="panel-head">
          <h2 className="serif">
            Growth of one rand <em>{period === "live" ? "since the freeze" : "out of sample"}</em>
          </h2>
          <div className="legend">
            <span style={{ color: "var(--primary)" }}>
              <i />
              {ruleLabel(rule)}
            </span>
            <span style={{ color: "#b58b3c" }}>
              <i />
              Satrix 40 ETF
            </span>
            <span style={{ color: "var(--border-strong)" }}>
              <i />
              Other rules
            </span>
          </div>
        </div>
        {chart && chart.dates.length > 1 ? (
          <GrowthChart dates={chart.dates} lines={chart.lines} label="Growth of one rand under each rule" />
        ) : (
          <div className="loading">{period === "live" ? "Loading live prices…" : "No data"}</div>
        )}
        {period === "live" && (
          <p className="note">
            Weights set at the {fmtDate(research.freeze)} close, priced daily from live data, with each rule rebalanced at later month ends by
            the same frozen code. A few weeks says nothing about skill; this panel is here so the record cannot be edited after the fact.
          </p>
        )}
        {period === "all" && <p className="note">From January 2009, when the Satrix 40 series starts.</p>}
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2 className="serif">
            The three <em>pre-registered</em> tests
          </h2>
          <span className="eyebrow">Validation, 2017 to Sep 2026</span>
        </div>
        <Tests research={research} />
      </section>

      {period !== "live" && period !== "all" && (
        <section className="panel">
          <div className="panel-head">
            <h2 className="serif">Every rule, {period === "design" ? "design 2008 to 2016" : "validation 2017 to Sep 2026"}</h2>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Rule</th>
                  <th className="num">CAGR</th>
                  <th className="num">Volatility</th>
                  <th className="num">Sharpe</th>
                  <th className="num">Max drawdown</th>
                  <th className="num">Window</th>
                  <th className="num">Sharpe vs Satrix 40 (t)</th>
                </tr>
              </thead>
              <tbody>
                {[...RULES.map((r) => r.id), "STX40" as const].map((k) => {
                  const v = research.rules[k][period];
                  const t = k === "STX40" ? null : research.vs_stx40[k as RuleId];
                  return (
                    <tr key={k} className={k === rule ? "final" : undefined}>
                      <td>{ruleLabel(k)}</td>
                      <td className="num">{pct(v?.cagr)}</td>
                      <td className="num">{pct(v?.vol)}</td>
                      <td className="num">{num(v?.sharpe)}</td>
                      <td className="num">{pct(v?.mdd)}</td>
                      <td className="num">{research.rules[k].window ? (k === "R0" ? "156 weeks" : `${research.rules[k].window} days`) : ""}</td>
                      <td className="num">{t && period === "validation" ? `${num(t.diff_annual)} (${num(t.t_stat, 1)})` : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="note">
            Costs: {pct(research.costs.sell, 2)} a side for brokerage and spread, plus 0.25% securities transfer tax on purchases. The estimation
            window (one or two years) was chosen per rule on the design period only. Sharpe ratios use the 91-day T-bill.
          </p>
        </section>
      )}
    </>
  );
}

function Tests({ research }: { research: Research }) {
  const R = research.rules;
  const v = (k: RuleId | "STX40") => R[k].validation!;
  const p2 = research.tests[1].detail as Record<string, { t_stat: number }>;
  const p3 = research.tests[2].detail as { t_stat: number };
  const best = research.tests[1].best as RuleId;
  const text: Record<string, string> = {
    P1: `Minimum variance ran at ${pct(v("R3").vol)} volatility, against ${pct(v("R1").vol)} for equal weight and ${pct(v("STX40").vol)} for the Satrix 40. Lower risk did not mean better returns: it made ${pct(v("R3").cagr)} a year with a Sharpe ratio of ${num(v("R3").sharpe)}, significantly worse than equal weight (t = ${num(p2.R3.t_stat, 1)}).`,
    P2: `${ruleLabel(best)} had the best Sharpe ratio, ${num(v(best).sharpe)} against ${num(v("R1").sharpe)} for equal weight, but the gap is well within noise (t = ${num(p2[best].t_stat, 1)}). Equal risk contribution trailed equal weight (t = ${num(p2.R4.t_stat, 1)}). No rule beat simply holding the Satrix 40 (Sharpe ${num(v("STX40").sharpe)}).`,
    P3: `The original app's method made ${pct(v("R0").cagr)} a year with a Sharpe ratio of ${num(v("R0").sharpe)}, below equal weight (t = ${num(p3.t_stat, 1)}). Picking the best of 5,000 random portfolios mostly picks the luckiest past means, and those do not repeat.`,
  };
  return (
    <ul className="tests">
      {research.tests.map((t) => (
        <li key={t.id}>
          <div className="test-head">
            <span className="mono">{t.id}</span>
            <strong>{t.claim}</strong>
            <Verdict text={t.verdict} />
          </div>
          <p>{text[t.id]}</p>
        </li>
      ))}
    </ul>
  );
}

function RiskModels({ research }: { research: Research }) {
  const [port, setPort] = useState<"R1" | "R3" | "STX40">("R1");
  const [model, setModel] = useState<ModelId>("fhs");
  const s = research.var[port];
  const t = s.tests;
  return (
    <>
      <div className="controls">
        <div className="control wide">
          <span className="label">Portfolio</span>
          <Segmented options={VAR_PORTFOLIOS.map((p) => ({ id: p.id, label: p.label }))} value={port} onChange={setPort} />
        </div>
        <div className="control wide">
          <span className="label">Model</span>
          <Segmented options={MODELS.map((m) => ({ id: m, label: research.var_labels[m] }))} value={model} onChange={setModel} />
        </div>
      </div>
      <div className="metrics">
        <Metric value={`${t[model].var99.exceedances}`} label="Days beyond 99% VaR" sub={`${num(t[model].var99.expected, 0)} expected`} />
        <Metric value={num(t[model].var99.p_cc, 3)} label="Christoffersen p, 99%" sub="below 0.05 rejects" neg={t[model].var99.p_cc < 0.05} />
        <Metric value={num(t[model].es975_z2)} label="ES test Z2" sub="below −0.70 rejects" neg={t[model].es975_z2 < -0.7} />
        <Metric value={pct(t[model].traffic_light.red, 0)} label="Years in Basel red" sub="rolling 250 days" neg={t[model].traffic_light.red > 0} />
      </div>
      <section className="panel">
        <div className="panel-head">
          <h2 className="serif">
            Daily return against the <em>forecast</em> 99% loss
          </h2>
          <div className="legend">
            <span style={{ color: "var(--primary)" }}>
              <i />
              −VaR, set the evening before
            </span>
            <span style={{ color: "var(--negative)" }}>
              <i />
              Exceedance
            </span>
          </div>
        </div>
        <VarChart dates={s.date} r={s.r} v={s[model]} />
      </section>
      <section className="panel">
        <div className="panel-head">
          <h2 className="serif">Backtests, validation 2017 to Sep 2026</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th className="num">99% days (expected)</th>
                <th className="num">Kupiec p</th>
                <th className="num">Christoffersen p</th>
                <th className="num">97.5% days (expected)</th>
                <th className="num">Christoffersen p</th>
                <th className="num">ES Z2</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {MODELS.map((m) => (
                <tr key={m} className={m === model ? "final" : undefined}>
                  <td>{research.var_labels[m]}</td>
                  <td className="num">
                    {t[m].var99.exceedances} ({num(t[m].var99.expected, 0)})
                  </td>
                  <td className="num">{num(t[m].var99.p_value, 3)}</td>
                  <td className="num">{num(t[m].var99.p_cc, 3)}</td>
                  <td className="num">
                    {t[m].var975.exceedances} ({num(t[m].var975.expected, 0)})
                  </td>
                  <td className="num">{num(t[m].var975.p_cc, 3)}</td>
                  <td className="num">{num(t[m].es975_z2)}</td>
                  <td>
                    <Verdict text={t[m].passed ? "Passed" : "Failed"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="note">
          A model passes if neither conditional coverage test (99% and 97.5%) rejects at 5% and the Acerbi and Szekely Z2 statistic for 97.5%
          expected shortfall is above −0.70. Every forecast uses only returns up to the previous close; the GJR-GARCH model is refitted at each
          month end on the last 1,000 sessions. The normal and EWMA models assume thin tails and see too many large losses; plain historical
          simulation reacts too slowly when volatility jumps, so its misses cluster.
        </p>
      </section>
    </>
  );
}

function StressTable({ stress }: { stress: PortfolioResult["stress"] }) {
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Historical scenario</th>
              <th>Window (Top 40 peak to trough)</th>
              <th className="num">Top 40</th>
              <th className="num">Portfolio</th>
              <th>Biggest drags</th>
              <th className="num">Proxied weight</th>
            </tr>
          </thead>
          <tbody>
            {stress.historical.map((s) => (
              <tr key={s.key}>
                <td>{s.label}</td>
                <td className="mono">
                  {fmtDate(s.start)} to {fmtDate(s.end)}
                </td>
                <td className="num">{pct(s.index_return)}</td>
                <td className="num">{pct(s.portfolio_return)}</td>
                <td className="mono small">
                  {s.worst
                    .slice(0, 3)
                    .map((w) => `${short(w.ticker)} ${pct(w.return, 0)}`)
                    .join(", ")}
                </td>
                <td className="num">{s.proxied_weight ? pct(s.proxied_weight, 0) : "none"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-wrap" style={{ marginTop: 22 }}>
        <table>
          <thead>
            <tr>
              <th>Hypothetical scenario</th>
              <th className="num">Effect</th>
            </tr>
          </thead>
          <tbody>
            {stress.hypothetical.map((s) => (
              <tr key={s.key}>
                <td>{s.label}</td>
                <td className="num">
                  {s.var99_after != null
                    ? `1-day 99% VaR ${pct(s.var99_before, 1)} → ${pct(s.var99_after, 1)}`
                    : `${pct(s.portfolio_return)}${s.rand_beta != null ? ` (rand beta ${num(s.rand_beta)})` : ""}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function StressTab({ research }: { research: Research }) {
  const [rule, setRule] = useState<RuleId>("R0");
  const bk = research.books[rule][research.books[rule].length - 1];
  const top = Object.entries(bk.weights)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  return (
    <>
      <div className="controls">
        <div className="control wide">
          <span className="label">Portfolio at the {fmtDate(research.latest_rebalance)} rebalance</span>
          <Segmented className="rule-switch" options={RULES} value={rule} onChange={setRule} />
        </div>
      </div>
      <p className="note">
        {Object.keys(bk.weights).length} holdings. Largest: {top.map(([t, w]) => `${short(t)} ${pct(w, 1)}`).join(", ")}.
      </p>
      <section className="panel">
        <StressTable stress={research.stress[rule]} />
        <p className="note">
          Each holding takes its own price move over the window. A share without prices then (listed later, or relisted, such as Richemont in
          2023) takes its beta to the Top 40 times the index move; the proxied weight column shows how much of the portfolio that covers. The
          rand scenario uses each share's beta to USD/ZAR on two years of weekly returns. Illustrations, not tests, and flattered by survivorship:
          shares that collapsed in these episodes and later delisted are not in the universe.
        </p>
      </section>
    </>
  );
}

function Build({ research }: { research: Research }) {
  const [selected, setSelected] = useState<string[]>(research.universe.map((u) => u.ticker));
  const [query, setQuery] = useState("");
  const [rule, setRule] = useState<RuleId>("R3");
  const [window, setWindow] = useState(252);
  const [cap, setCap] = useState(0.1);
  const [result, setResult] = useState<PortfolioResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const names = useMemo(() => Object.fromEntries(research.all_tickers.map((t) => [t.ticker, t.name])), [research]);
  const matches = query.trim()
    ? research.all_tickers
        .filter((t) => !selected.includes(t.ticker) && `${t.ticker} ${t.name}`.toLowerCase().includes(query.trim().toLowerCase()))
        .slice(0, 8)
    : [];

  const run = () => {
    setLoading(true);
    setErr(null);
    api
      .portfolio(selected, rule, window, cap)
      .then((r) => (r.error ? setErr(r.error) : setResult(r)), (e) => setErr(String(e.message ?? e)))
      .finally(() => setLoading(false));
  };
  useEffect(run, []); // eslint-disable-line react-hooks/exhaustive-deps

  const assets = result?.weights.map((w) => ({ ticker: w.ticker, ret: w.ret, vol: w.vol, weight: w.weight })) ?? [];
  const sorted = [...(result?.weights ?? [])].sort((a, b) => b.weight - a.weight);
  const fhs = result?.var.fhs;

  return (
    <>
      <div className="controls">
        <div className="control wide">
          <span className="label">
            Shares <output>{selected.length} of up to 40</output>
          </span>
          <div className="chips">
            {selected.map((t) => (
              <button key={t} className="chip" title={names[t]} onClick={() => setSelected(selected.filter((x) => x !== t))}>
                {short(t)} ×
              </button>
            ))}
          </div>
          <div className="picker">
            <input
              type="search"
              placeholder="Add a share: name or ticker"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={selected.length >= 40}
            />
            {matches.length > 0 && (
              <ul className="suggest">
                {matches.map((m) => (
                  <li key={m.ticker}>
                    <button
                      onClick={() => {
                        setSelected([...selected, m.ticker]);
                        setQuery("");
                      }}
                    >
                      <span className="mono">{short(m.ticker)}</span> {m.name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="presets">
            <button className="reset" onClick={() => setSelected(research.universe.map((u) => u.ticker))}>
              40 most traded at {fmtDate(research.latest_rebalance, { month: "short", year: "numeric" })}
            </button>
            <button className="reset" onClick={() => setSelected(ORIGINAL_DEFAULT)}>
              The original app's default
            </button>
            <button className="reset" onClick={() => setSelected([])}>
              Clear
            </button>
          </div>
        </div>
        <div className="control wide">
          <span className="label">Rule</span>
          <Segmented className="rule-switch" options={RULES} value={rule} onChange={setRule} />
        </div>
        <div className="control">
          <span className="label">Estimation window</span>
          <Segmented options={[{ id: 252, label: "1 year" }, { id: 504, label: "2 years" }]} value={window} onChange={setWindow} />
        </div>
        <div className="control">
          <span className="label">Max weight (R3, R5)</span>
          <Segmented
            options={[0.1, 0.2, 0.35, 1].map((c) => ({ id: c, label: c === 1 ? "None" : pct(c, 0) }))}
            value={cap}
            onChange={setCap}
          />
        </div>
        <div className="control">
          <span className="label">&nbsp;</span>
          <button className="run" onClick={run} disabled={loading || selected.length < 2}>
            {loading ? "Fetching prices…" : "Run on live prices"}
          </button>
        </div>
      </div>

      {err && <p className="note error">{err}</p>}
      {result && (
        <>
          <div className="metrics">
            <Metric value={pct(result.vol)} label="Volatility" sub="annual, forecast" />
            <Metric value={fhs ? pct(fhs.var99, 2) : "n/a"} label="1-day 99% VaR" sub="filtered historical" />
            <Metric value={fhs ? pct(fhs.es975, 2) : "n/a"} label="1-day 97.5% ES" sub="filtered historical" />
            <Metric value={pct(result.expected_return)} label="Past mean return" sub="in sample, not a forecast" />
            <Metric value={String(sorted.filter((w) => w.weight > 0.005).length)} label="Holdings over 0.5%" />
          </div>
          <p className="note">
            Weights from the {result.window} sessions to {fmtDate(result.as_of)}. The filtered historical VaR is the model that held up out of sample (see
            Risk models); the mean return is only what these shares did in the window, which the backtest shows is a poor guide to the next month.
            {Object.keys(result.excluded).length > 0 &&
              ` Left out: ${Object.entries(result.excluded)
                .map(([t, why]) => `${short(t)} (${why})`)
                .join("; ")}.`}
          </p>
          <section className="panel split">
            <div>
              <div className="panel-head">
                <h2 className="serif">
                  Weights and <em>risk</em> shares
                </h2>
              </div>
              <div className="bars">
                {sorted
                  .filter((w) => w.weight > 0.001)
                  .map((w) => (
                    <div key={w.ticker} className="bar-row" title={names[w.ticker]}>
                      <span className="mono">{short(w.ticker)}</span>
                      <span className="bar">
                        <i style={{ width: `${(w.weight / sorted[0].weight) * 100}%` }} />
                        <b style={{ width: `${(Math.max(0, w.risk) / sorted[0].weight) * 100}%` }} />
                      </span>
                      <span className="mono num">{pct(w.weight, 1)}</span>
                      <span className="mono num muted">{pct(w.risk, 1)}</span>
                    </div>
                  ))}
              </div>
              <p className="note">Bar: weight. Line: share of portfolio variance.</p>
            </div>
            <div>
              <div className="panel-head">
                <h2 className="serif">Value at risk by model</h2>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th className="num">99% VaR</th>
                    <th className="num">97.5% VaR</th>
                    <th className="num">97.5% ES</th>
                  </tr>
                </thead>
                <tbody>
                  {MODELS.filter((m) => result.var[m]).map((m) => (
                    <tr key={m} className={m === "fhs" ? "final" : undefined}>
                      <td>{research.var_labels[m]}</td>
                      <td className="num">{pct(result.var[m]!.var99, 2)}</td>
                      <td className="num">{pct(result.var[m]!.var975, 2)}</td>
                      <td className="num">{pct(result.var[m]!.es975, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="note">
                One-day losses as a share of the portfolio, from {result.history_sessions} sessions of these weights applied to past returns.
              </p>
            </div>
          </section>
          <section className="panel">
            <div className="panel-head">
              <h2 className="serif">
                Efficient frontier, <em>in sample</em>
              </h2>
            </div>
            <FrontierChart frontier={result.frontier} assets={assets} portfolio={{ ret: result.expected_return, vol: result.vol }} rf={result.rf} />
            <p className="note">
              Long only, shrunk covariance, the same weight cap. The frontier uses past mean returns, so it is a description of the window, not
              a menu of future outcomes.
            </p>
          </section>
          <section className="panel">
            <div className="panel-head">
              <h2 className="serif">Stress tests</h2>
            </div>
            <StressTable stress={result.stress} />
          </section>
        </>
      )}
    </>
  );
}

function Method({ research }: { research: Research }) {
  const n = research.all_tickers.length;
  return (
    <section className="panel">
      <ul className="method">
        <li>
          <strong>Universe</strong>
          The {n} JSE tickers from the original app that Yahoo Finance still serves. At each month end, the 40 with the highest median traded
          value over the previous three months, among those with two years of history.
        </li>
        <li>
          <strong>Rules</strong>
          Long only, rebalanced monthly, weights drift between rebalances. Minimum variance and maximum Sharpe use Ledoit-Wolf shrinkage and a 10%
          cap; equal risk contribution solves Spinu's convex problem. The original method is reproduced as written: weekly returns, 5,000
          uniform draws, no risk-free rate.
        </li>
        <li>
          <strong>Costs</strong>
          0.10% a side for brokerage and spread, plus 0.25% securities transfer tax on purchases, charged on every rebalance.
        </li>
        <li>
          <strong>Protocol</strong>
          Design 2008 to 2016 for choices and debugging; validation 2017 to September 2026, run once; live from 1 October 2026 on frozen rules.
          The Sharpe ratio test is Ledoit and Wolf (2008) with a HAC variance.
        </li>
        <li>
          <strong>Risk models</strong>
          Historical simulation, normal and EWMA on 250 days, and filtered historical simulation on a GJR-GARCH(1,1) with Student t errors.
          Kupiec, Christoffersen and Basel traffic-light tests for VaR; Acerbi and Szekely Z2 for expected shortfall.
        </li>
        <li>
          <strong>What changed from 2024</strong>
          The app scored its weights on the data that chose them, compounded log returns as if they were simple, compared a weekly return with
          an annual target, defined expected shortfall against that target rather than the VaR tail, and used ad hoc volatility and correlation
          shocks. Each of these is replaced above.
        </li>
        <li>
          <strong>Limits</strong>
          Survivorship bias (only firms listed in 2024), Yahoo histories that start at relistings, no market impact, no dividend tax. The live
          record is too short to say anything yet.
        </li>
        <li>
          <strong>Data</strong>
          Prices from Yahoo Finance and the T-bill rate from FRED are downloaded at run time and not redistributed. Rebalanced on{" "}
          {fmtDate(research.latest_rebalance)}; results generated {fmtDate(research.generated)}.
        </li>
      </ul>
    </section>
  );
}
