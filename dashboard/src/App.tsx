import { useEffect, useMemo, useState } from "react";
import {
  api,
  type Live,
  type ModelId,
  type PortfolioResult,
  type Research,
  type RuleId,
} from "./api";
import { Blind } from "./Blind";
import { FrontierChart, GrowthChart, type Line } from "./charts";
import { fmtDate, num, pct, short } from "./format";

type Tab = "blind" | "desk" | "live" | "how";

const RULES: { id: RuleId; label: string; sub: string }[] = [
  { id: "R0", label: "Random search", sub: "best of 5,000 random weights" },
  { id: "R1", label: "Equal weight", sub: "1/N" },
  { id: "R2", label: "Inverse volatility", sub: "1 / σ" },
  { id: "R3", label: "Minimum variance", sub: "shrunk Σ, 10% cap" },
  { id: "R4", label: "Equal risk", sub: "risk parity" },
  { id: "R5", label: "Maximum Sharpe", sub: "shrunk Σ, 10% cap" },
];
const ruleLabel = (id: string) =>
  RULES.find((r) => r.id === id)?.label ?? (id === "STX40" ? "Satrix 40" : id);
const MODELS: ModelId[] = ["fhs", "historical", "normal", "ewma"];
const ORIGINAL_DEFAULT = ["NPN.JO", "BTI.JO", "SOL.JO"];

export function App({ embedded }: { embedded: boolean }) {
  const [research, setResearch] = useState<Research | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>(
    () => (new URLSearchParams(location.search).get("tab") as Tab) || "blind",
  );

  useEffect(() => {
    api.research().then(setResearch, (e) => setError(String(e)));
    const loadLive = () =>
      api.live().then(setLive, () => setTimeout(loadLive, 15000));
    loadLive();
  }, []);

  if (error)
    return <div className="preview loading">Could not load: {error}</div>;
  if (!research)
    return (
      <div className="preview loading">
        Waking the server; the first load can take half a minute…
      </div>
    );

  return (
    <div className="preview">
      <header className="head">
        <div>
          <p className="eyebrow">JSE portfolio risk</p>
          <h1 className="serif">
            Set a portfolio <em>without hindsight</em>
          </h1>
        </div>
        <div className="status">
          <span>
            <i className={`dot${live ? "" : " stale"}`} />
            {live
              ? `Live prices to ${fmtDate(live.date[live.date.length - 1] ?? research.data_end)}`
              : "Loading live prices"}
          </span>
          <span>Rules fixed {fmtDate(research.freeze)}</span>
          <span>Last rebalance {fmtDate(research.latest_rebalance)}</span>
        </div>
      </header>

      <nav className="tabs" role="tablist">
        {(
          [
            ["blind", "The blind month"],
            ["desk", "Risk desk today"],
            ["live", "Live record"],
            ["how", "How it works"],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "blind" && <Blind />}
      {tab === "desk" && <Build research={research} />}
      {tab === "live" && <LiveRecord research={research} live={live} />}
      {tab === "how" && <How research={research} />}

      <p className="footer-note">
        Prices from Yahoo Finance, fetched when you use the page and not stored.
        Shares still listed in 2024 only, so firms that later delisted are
        missing. Research output, not investment advice.
        {embedded
          ? ""
          : " Source: github.com/Sbusiso-Mdingi/jse-risk-management."}
      </p>
    </div>
  );
}

function LiveRecord({
  research,
  live,
}: {
  research: Research;
  live: Live | null;
}) {
  const [rule, setRule] = useState<RuleId>("R1");
  const keys = [...RULES.map((r) => r.id), "STX40"] as (RuleId | "STX40")[];
  const lines: Line[] = live
    ? keys.map((k) => ({
        key: k,
        label: ruleLabel(k),
        values: live.growth[k],
        tone: k === rule ? "main" : k === "STX40" ? "bench" : "other",
      }))
    : [];
  const end = (k: RuleId | "STX40") =>
    live ? (live.growth[k][live.growth[k].length - 1] ?? 1) - 1 : 0;
  const order = [...keys].sort((a, b) => end(b) - end(a));
  const bk = research.books[rule][research.books[rule].length - 1];
  const top = Object.entries(bk.weights)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);
  return (
    <>
      <p className="lede">
        On {fmtDate(research.freeze)} each rule&apos;s code was frozen. Since
        then every rule rebalances at each month end on the prices it can see,
        and its portfolio is priced after every JSE close, so the record cannot
        be edited after the fact. A few weeks is far too short to say anything
        about skill.
      </p>
      <div className="controls">
        <div className="control wide">
          <span className="label">Highlight</span>
          <Segmented
            className="rule-switch"
            options={RULES}
            value={rule}
            onChange={setRule}
          />
        </div>
      </div>
      <section className="panel split live-split">
        <div>
          <div className="panel-head">
            <h2 className="serif">
              Since <em>{fmtDate(research.freeze)}</em>
            </h2>
          </div>
          {live && live.date.length > 1 ? (
            <GrowthChart
              dates={live.date}
              lines={lines}
              label="Growth of one rand since the rules were fixed"
            />
          ) : (
            <div className="loading">Loading live prices…</div>
          )}
        </div>
        <div>
          <ol className="ranking">
            {order.map((k, i) => (
              <li
                key={k}
                className={
                  k === rule ? "me" : k === "STX40" ? "bench" : undefined
                }
              >
                <span className="mono">{i + 1}</span>
                <span>{ruleLabel(k)}</span>
                <b className={end(k) < 0 ? "neg" : undefined}>
                  {live ? pct(end(k), 2) : "…"}
                </b>
              </li>
            ))}
          </ol>
          <p className="note">
            {ruleLabel(rule)} has held {Object.keys(bk.weights).length} shares
            since {fmtDate(bk.date)}. Largest:{" "}
            {top.map(([t, x]) => `${short(t)} ${pct(x, 1)}`).join(", ")}.
          </p>
        </div>
      </section>
    </>
  );
}

function How({ research }: { research: Research }) {
  const n = research.all_tickers.length;
  return (
    <section className="panel">
      <ul className="method">
        <li>
          <strong>The shares</strong>
          At every month end, the 40 most traded of the {n} JSE tickers the 2024
          version of this app offered, by median traded value over the previous
          three months, among shares with two years of prices. Total returns,
          with dividends.
        </li>
        <li>
          <strong>The six rules</strong>
          Random search keeps the best of 5,000 random portfolios by past return
          over volatility, as the 2024 app did. Equal weight holds 1/40 of each.
          Inverse volatility weights by 1/σ. Minimum variance and maximum Sharpe
          use a Ledoit-Wolf shrunk covariance matrix with at most 10% in any
          share. Equal risk gives every holding the same share of the
          portfolio&apos;s variance.
        </li>
        <li>
          <strong>Without hindsight</strong>
          Every weight is set from prices up to a month-end close and held,
          drifting, to the next one. The blind month does the same for your own
          weights.
        </li>
        <li>
          <strong>The loss forecast</strong>A GJR-GARCH(1,1) with Student t
          errors on the portfolio&apos;s last 1,000 daily returns, refitted at
          the month end and updated each day. The 99% value at risk is the loss
          that should be beaten about one day in a hundred; expected shortfall
          is the average loss on those days. The risk desk also shows historical
          simulation, a normal model and EWMA beside it.
        </li>
        <li>
          <strong>Costs</strong>
          In the live record the rules pay 0.10% a side and 0.25% securities
          transfer tax on purchases at each rebalance. The blind month compares
          portfolios before costs.
        </li>
        <li>
          <strong>Data</strong>
          Prices from Yahoo Finance and the T-bill rate from FRED, fetched at
          run time and not stored. Results generated{" "}
          {fmtDate(research.generated)}.
        </li>
      </ul>
    </section>
  );
}

function Metric({
  value,
  label,
  sub,
  neg,
}: {
  value: string;
  label: string;
  sub?: string;
  neg?: boolean;
}) {
  return (
    <div className="metric">
      <div className={`value${neg ? " neg" : ""}`}>{value}</div>
      <div className="label">{label}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
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
        <button
          key={String(o.id)}
          aria-pressed={o.id === value}
          onClick={() => onChange(o.id)}
        >
          {o.label}
          {o.sub && <span>{o.sub}</span>}
        </button>
      ))}
    </div>
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
                <td className="num">
                  {s.proxied_weight ? pct(s.proxied_weight, 0) : "none"}
                </td>
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

function Build({ research }: { research: Research }) {
  const [selected, setSelected] = useState<string[]>(
    research.universe.map((u) => u.ticker),
  );
  const [query, setQuery] = useState("");
  const [rule, setRule] = useState<RuleId>("R3");
  const [window, setWindow] = useState(252);
  const [cap, setCap] = useState(0.1);
  const [result, setResult] = useState<PortfolioResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const names = useMemo(
    () =>
      Object.fromEntries(research.all_tickers.map((t) => [t.ticker, t.name])),
    [research],
  );
  const matches = query.trim()
    ? research.all_tickers
        .filter(
          (t) =>
            !selected.includes(t.ticker) &&
            `${t.ticker} ${t.name}`
              .toLowerCase()
              .includes(query.trim().toLowerCase()),
        )
        .slice(0, 8)
    : [];

  const run = () => {
    setLoading(true);
    setErr(null);
    api
      .portfolio(selected, rule, window, cap)
      .then(
        (r) => (r.error ? setErr(r.error) : setResult(r)),
        (e) => setErr(String(e.message ?? e)),
      )
      .finally(() => setLoading(false));
  };
  useEffect(run, []); // eslint-disable-line react-hooks/exhaustive-deps

  const assets =
    result?.weights.map((w) => ({
      ticker: w.ticker,
      ret: w.ret,
      vol: w.vol,
      weight: w.weight,
    })) ?? [];
  const sorted = [...(result?.weights ?? [])].sort(
    (a, b) => b.weight - a.weight,
  );
  const fhs = result?.var.fhs;

  return (
    <>
      <p className="lede">
        Today, on live prices: choose shares and a rule, and see the weights it
        sets, the loss each risk model forecasts for tomorrow, and what the
        portfolio would have lost in four past shocks.
      </p>
      <div className="controls">
        <div className="control wide">
          <span className="label">
            Shares <output>{selected.length} of up to 40</output>
          </span>
          <div className="chips">
            {selected.map((t) => (
              <button
                key={t}
                className="chip"
                title={names[t]}
                onClick={() => setSelected(selected.filter((x) => x !== t))}
              >
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
            <button
              className="reset"
              onClick={() =>
                setSelected(research.universe.map((u) => u.ticker))
              }
            >
              40 most traded at{" "}
              {fmtDate(research.latest_rebalance, {
                month: "short",
                year: "numeric",
              })}
            </button>
            <button
              className="reset"
              onClick={() => setSelected(ORIGINAL_DEFAULT)}
            >
              The 2024 version's default
            </button>
            <button className="reset" onClick={() => setSelected([])}>
              Clear
            </button>
          </div>
        </div>
        <div className="control wide">
          <span className="label">Rule</span>
          <Segmented
            className="rule-switch"
            options={RULES}
            value={rule}
            onChange={setRule}
          />
        </div>
        <div className="control">
          <span className="label">Estimation window</span>
          <Segmented
            options={[
              { id: 252, label: "1 year" },
              { id: 504, label: "2 years" },
            ]}
            value={window}
            onChange={setWindow}
          />
        </div>
        <div className="control">
          <span className="label">Max weight (min variance, max Sharpe)</span>
          <Segmented
            options={[0.1, 0.2, 0.35, 1].map((c) => ({
              id: c,
              label: c === 1 ? "None" : pct(c, 0),
            }))}
            value={cap}
            onChange={setCap}
          />
        </div>
        <div className="control">
          <span className="label">&nbsp;</span>
          <button
            className="run"
            onClick={run}
            disabled={loading || selected.length < 2}
          >
            {loading ? "Fetching prices…" : "Run on live prices"}
          </button>
        </div>
      </div>

      {err && <p className="note error">{err}</p>}
      {result && (
        <>
          <div className="metrics">
            <Metric
              value={pct(result.vol)}
              label="Volatility"
              sub="annual, forecast"
            />
            <Metric
              value={fhs ? pct(fhs.var99, 2) : "n/a"}
              label="1-day 99% VaR"
              sub="filtered historical"
            />
            <Metric
              value={fhs ? pct(fhs.es975, 2) : "n/a"}
              label="1-day 97.5% ES"
              sub="filtered historical"
            />
            <Metric
              value={pct(result.expected_return)}
              label="Past mean return"
              sub="in sample, not a forecast"
            />
            <Metric
              value={String(sorted.filter((w) => w.weight > 0.005).length)}
              label="Holdings over 0.5%"
            />
          </div>
          <p className="note">
            Weights from the {result.window} sessions to {fmtDate(result.as_of)}
            . Filtered historical is the GARCH model the blind month uses; the
            mean return is only what these shares did in the window, not a
            forecast.
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
                    <div
                      key={w.ticker}
                      className="bar-row"
                      title={names[w.ticker]}
                    >
                      <span className="mono">{short(w.ticker)}</span>
                      <span className="bar">
                        <i
                          style={{
                            width: `${(w.weight / sorted[0].weight) * 100}%`,
                          }}
                        />
                        <b
                          style={{
                            width: `${(Math.max(0, w.risk) / sorted[0].weight) * 100}%`,
                          }}
                        />
                      </span>
                      <span className="mono num">{pct(w.weight, 1)}</span>
                      <span className="mono num muted">{pct(w.risk, 1)}</span>
                    </div>
                  ))}
              </div>
              <p className="note">
                Bar: weight. Line: share of portfolio variance.
              </p>
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
                One-day losses as a share of the portfolio, from{" "}
                {result.history_sessions} sessions of these weights applied to
                past returns.
              </p>
            </div>
          </section>
          <section className="panel">
            <div className="panel-head">
              <h2 className="serif">
                Efficient frontier, <em>in sample</em>
              </h2>
            </div>
            <FrontierChart
              frontier={result.frontier}
              assets={assets}
              portfolio={{ ret: result.expected_return, vol: result.vol }}
              rf={result.rf}
            />
            <p className="note">
              Long only, shrunk covariance, the same weight cap. The frontier
              uses past mean returns, so it is a description of the window, not
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
