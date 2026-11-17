import { useEffect, useMemo, useState } from "react";
import { api, type BlindMonth, type BlindPlay, type RuleId } from "./api";
import { GrowthChart, VarChart, type Line } from "./charts";
import { fmtDate, pct, short } from "./format";

/* The blind month: stand at a past month end knowing only prices to that close, set weights, get the
 * next day's loss forecast, then see the month that followed. */

type Preset = RuleId | "mine";
const PRESETS: { id: Preset; label: string }[] = [
  { id: "R1", label: "Equal weight" },
  { id: "R3", label: "Minimum variance" },
  { id: "R5", label: "Maximum Sharpe" },
  { id: "R2", label: "Inverse volatility" },
  { id: "R4", label: "Equal risk" },
  { id: "R0", label: "Random search" },
  { id: "mine", label: "My own" },
];
const NOTIONAL = 100_000;
const STORE = "jse-risk-blind-v1";

type Played = {
  date: string;
  you: number;
  stx: number;
  eq: number;
  hits: number;
  days: number;
};

const growth = (r: number[]) => {
  let g = 1;
  return r.map((x) => (g *= 1 + x));
};
const total = (r: number[]) => r.reduce((g, x) => g * (1 + x), 1) - 1;
const rand = (v: number) => `R${Math.round(v).toLocaleString("en-ZA")}`;
const monthName = (iso: string) =>
  fmtDate(iso, { month: "long", year: "numeric" });

function load(): Played[] {
  try {
    return JSON.parse(localStorage.getItem(STORE) ?? "[]");
  } catch {
    return [];
  }
}

export function Blind() {
  const [months, setMonths] = useState<{ date: string; next: string }[]>([]);
  const [date, setDate] = useState<string>("2020-02-28");
  const [month, setMonth] = useState<BlindMonth | null>(null);
  const [preset, setPreset] = useState<Preset>("R1");
  const [w, setW] = useState<Record<string, number>>({});
  const [play, setPlay] = useState<BlindPlay | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [played, setPlayed] = useState<Played[]>(load);

  useEffect(() => {
    api.blindMonths().then(
      (d) => setMonths(d.months),
      (e) => setErr(String(e.message ?? e)),
    );
  }, []);

  useEffect(() => {
    setMonth(null);
    setPlay(null);
    setRevealed(false);
    setErr(null);
    setBusy("Fetching prices to that close…");
    api
      .blindMonth(date)
      .then(
        (m) => {
          setMonth(m);
          setW((old) => {
            if (preset !== "mine")
              return Object.fromEntries(
                m.shares.map((s) => [s.ticker, s.w[preset]]),
              );
            const kept = Object.fromEntries(
              m.shares.map((s) => [s.ticker, old[s.ticker] ?? 0]),
            );
            return Object.values(kept).some((x) => x > 0)
              ? kept
              : Object.fromEntries(m.shares.map((s) => [s.ticker, s.w.R1]));
          });
        },
        (e) => setErr(String(e.message ?? e)),
      )
      .finally(() => setBusy(null));
  }, [date]); // eslint-disable-line react-hooks/exhaustive-deps

  const choose = (p: Preset) => {
    setPreset(p);
    setPlay(null);
    setRevealed(false);
    if (p !== "mine" && month)
      setW(Object.fromEntries(month.shares.map((s) => [s.ticker, s.w[p]])));
  };
  const edit = (t: string, pctValue: number) => {
    setPreset("mine");
    setPlay(null);
    setRevealed(false);
    setW({ ...w, [t]: Math.max(0, pctValue) / 100 });
  };

  const sum = Object.values(w).reduce((a, b) => a + b, 0);
  const held = month
    ? month.shares.filter((s) => (w[s.ticker] ?? 0) > 0).length
    : 0;
  const rows = useMemo(() => {
    if (!month) return [];
    const r = [...month.shares].sort(
      (a, b) =>
        (w[b.ticker] ?? 0) - (w[a.ticker] ?? 0) ||
        a.ticker.localeCompare(b.ticker),
    );
    return showAll ? r : r.slice(0, 10);
  }, [month, w, showAll]);

  const lockIn = () => {
    setBusy("Fitting the risk model to your portfolio…");
    setErr(null);
    api
      .blindPlay(date, w)
      .then(
        (p) => {
          setPlay(p);
          setRevealed(false);
        },
        (e) => setErr(String(e.message ?? e)),
      )
      .finally(() => setBusy(null));
  };

  const reveal = () => {
    if (!play) return;
    setRevealed(true);
    const rec: Played = {
      date: play.date,
      you: play.month_return,
      stx: total(play.stx40),
      eq: total(play.rules.R1),
      hits: play.hits.length,
      days: play.days.length,
    };
    const next = [...played.filter((x) => x.date !== rec.date), rec];
    setPlayed(next);
    localStorage.setItem(STORE, JSON.stringify(next));
  };

  const idx = months.findIndex((m) => m.date === date);
  const step = (d: number) => {
    const m = months[idx + d];
    if (m) setDate(m.date);
  };
  const random = () => {
    if (!months.length) return;
    setDate(months[Math.floor(Math.random() * months.length)]!.date);
  };

  const lines: Line[] = play
    ? [
        ...(Object.keys(play.rules) as RuleId[]).map((k) => ({
          key: k,
          label: play.labels[k],
          values: growth(play.rules[k]),
          tone: "other" as const,
        })),
        {
          key: "stx",
          label: "Satrix 40",
          values: growth(play.stx40),
          tone: "bench",
        },
        {
          key: "you",
          label: "Your portfolio",
          values: growth(play.you),
          tone: "main",
        },
      ]
    : [];
  const ranked = play
    ? [
        { k: "you", label: "Your portfolio", r: play.month_return },
        { k: "stx", label: "Satrix 40", r: total(play.stx40) },
        ...(Object.keys(play.rules) as RuleId[]).map((k) => ({
          k,
          label: play.labels[k],
          r: total(play.rules[k]),
        })),
      ].sort((a, b) => b.r - a.r)
    : [];
  const score = played.length
    ? {
        n: played.length,
        beatStx: played.filter((p) => p.you > p.stx).length,
        beatEq: played.filter((p) => p.you > p.eq).length,
        hits: played.reduce((a, p) => a + p.hits, 0),
        days: played.reduce((a, p) => a + p.days, 0),
        you: played.reduce((a, p) => a + p.you, 0) / played.length,
        stx: played.reduce((a, p) => a + p.stx, 0) / played.length,
      }
    : null;

  return (
    <div className="blind">
      <section className="blind-intro">
        <div>
          <p className="eyebrow">The blind month</p>
          <h2 className="serif">
            It is the close on{" "}
            <em>
              {fmtDate(date, {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </em>
            .
          </h2>
          <p className="lede">
            You know every price up to today and nothing after. Set a portfolio
            from that month&apos;s 40 most traded JSE shares, get
            tomorrow&apos;s loss forecast, then see{" "}
            {months[idx] ? monthName(months[idx]!.next) : "the next month"} play
            out against the six rules and the Satrix 40.
          </p>
        </div>
        <div className="when">
          <label className="label" htmlFor="month">
            Month end
          </label>
          <div className="when-row">
            <button
              onClick={() => step(-1)}
              disabled={idx <= 0}
              aria-label="Previous month"
            >
              ←
            </button>
            <select
              id="month"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            >
              {months.map((m) => (
                <option key={m.date} value={m.date}>
                  {fmtDate(m.date)}
                </option>
              ))}
            </select>
            <button
              onClick={() => step(1)}
              disabled={idx < 0 || idx >= months.length - 1}
              aria-label="Next month"
            >
              →
            </button>
          </div>
          <button className="reset" onClick={random}>
            Pick a month for me
          </button>
        </div>
      </section>

      <ol className="steps">
        <li className={`step${play ? " done" : ""}`}>
          <div className="step-head">
            <span className="step-n">1</span>
            <div>
              <h3>Set your weights</h3>
              <p className="muted">
                Start from a rule or set your own. Weights are scaled to add to
                100%.
              </p>
            </div>
          </div>
          <div className="presets-row segmented">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                aria-pressed={preset === p.id}
                onClick={() => choose(p.id)}
              >
                {p.label}
              </button>
            ))}
          </div>
          {month ? (
            <>
              <div className="table-wrap">
                <table className="weights-table">
                  <thead>
                    <tr>
                      <th>Share</th>
                      <th className="num">Past year</th>
                      <th className="num">Volatility</th>
                      <th className="num">Your weight</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => {
                      const x = w[s.ticker] ?? 0;
                      return (
                        <tr key={s.ticker}>
                          <td>
                            <span className="mono">{short(s.ticker)}</span>{" "}
                            <span className="muted small">{s.name}</span>
                          </td>
                          <td
                            className={`num${(s.ret1y ?? 0) < 0 ? " neg" : ""}`}
                          >
                            {s.ret1y == null ? "n/a" : pct(s.ret1y, 0)}
                          </td>
                          <td className="num">
                            {s.vol1y == null ? "n/a" : pct(s.vol1y, 0)}
                          </td>
                          <td className="num weight-cell">
                            <span className="wbar">
                              <i
                                style={{
                                  width: `${Math.min(100, (x / Math.max(sum, 1e-9)) * 500)}%`,
                                }}
                              />
                            </span>
                            <input
                              type="number"
                              min={0}
                              max={100}
                              step={0.5}
                              value={Number((x * 100).toFixed(1))}
                              onChange={(e) =>
                                edit(s.ticker, Number(e.target.value))
                              }
                              aria-label={`Weight in ${short(s.ticker)}, per cent`}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="step-foot">
                <button className="reset" onClick={() => setShowAll(!showAll)}>
                  {showAll
                    ? "Show the ten largest"
                    : `Show all ${month.shares.length} shares`}
                </button>
                <span className="muted small">
                  {held} holdings · total {pct(sum, 0)}
                  {Math.abs(sum - 1) > 0.005 && sum > 0
                    ? `, scaled to 100%`
                    : ""}
                </span>
                <button
                  className="run"
                  onClick={lockIn}
                  disabled={!!busy || sum <= 0}
                >
                  Lock in at this close
                </button>
              </div>
            </>
          ) : (
            <p className="loading">{err ?? busy ?? "Loading…"}</p>
          )}
        </li>

        <li
          className={`step${play ? "" : " waiting"}${revealed ? " done" : ""}`}
        >
          <div className="step-head">
            <span className="step-n">2</span>
            <div>
              <h3>Tomorrow&apos;s loss forecast</h3>
              <p className="muted">
                GJR-GARCH with Student t errors, fitted to your portfolio&apos;s
                last 1,000 sessions at this close.
              </p>
            </div>
          </div>
          {play ? (
            <div className="forecast">
              <div>
                <span className="big serif">
                  {rand(play.forecast.var99 * NOTIONAL)}
                </span>
                <span className="muted">
                  on {rand(NOTIONAL)}: a loss bigger than this should happen
                  about one day in a hundred ({pct(play.forecast.var99, 2)}).
                </span>
              </div>
              <div>
                <span className="big serif">
                  {rand(play.forecast.es99 * NOTIONAL)}
                </span>
                <span className="muted">
                  the average loss on those worst days (
                  {pct(play.forecast.es99, 2)}).
                </span>
              </div>
              {!revealed && (
                <button className="run" onClick={reveal}>
                  Show me {monthName(play.next)}
                </button>
              )}
            </div>
          ) : (
            <p className="muted small">
              {busy && month ? busy : "Lock in your weights first."}
            </p>
          )}
        </li>

        <li className={`step${revealed ? "" : " waiting"}`}>
          <div className="step-head">
            <span className="step-n">3</span>
            <div>
              <h3>{play ? monthName(play.next) : "The month after"}</h3>
              <p className="muted">
                Before trading costs, so a fresh portfolio and a rebalanced one
                compare alike.
              </p>
            </div>
          </div>
          {play && revealed ? (
            <>
              <div className="reveal">
                <div className="chart-box">
                  <p className="eyebrow">Growth of one rand</p>
                  <GrowthChart
                    dates={play.days}
                    lines={lines}
                    label="Your portfolio against the rules and the Satrix 40"
                  />
                  <p className="legend">
                    <span style={{ color: "var(--primary)" }}>
                      <i /> Your portfolio
                    </span>
                    <span style={{ color: "#b58b3c" }}>
                      <i /> Satrix 40
                    </span>
                    <span style={{ color: "var(--border-strong)" }}>
                      <i /> the six rules
                    </span>
                  </p>
                </div>
                <ol className="ranking">
                  {ranked.map((x, i) => (
                    <li
                      key={x.k}
                      className={
                        x.k === "you"
                          ? "me"
                          : x.k === "stx"
                            ? "bench"
                            : undefined
                      }
                    >
                      <span className="mono">{i + 1}</span>
                      <span>{x.label}</span>
                      <b className={x.r < 0 ? "neg" : undefined}>
                        {pct(x.r, 1)}
                      </b>
                    </li>
                  ))}
                </ol>
              </div>
              <div className="chart-box">
                <p className="eyebrow">
                  Each day against the forecast · {play.hits.length} of{" "}
                  {play.days.length} days past it, about{" "}
                  {(play.days.length / 100).toFixed(1)} expected
                </p>
                <VarChart dates={play.days} r={play.you} v={play.var99} />
                <p className="note">
                  Dots are your portfolio&apos;s daily returns; the line is the
                  99% loss forecast made the evening before, updated each day as
                  the model sees the new return. {rand(NOTIONAL)} became{" "}
                  {rand(NOTIONAL * (1 + play.month_return))}.
                </p>
              </div>
              <div className="step-foot">
                <button
                  className="run"
                  onClick={() => step(1)}
                  disabled={idx >= months.length - 1}
                >
                  Next month, same idea →
                </button>
                <button className="reset" onClick={random}>
                  Another month
                </button>
              </div>
            </>
          ) : (
            <p className="muted small">
              The month stays hidden until you have a forecast.
            </p>
          )}
        </li>
      </ol>

      {score && (
        <section className="scorecard">
          <div>
            <p className="eyebrow">Your record on this device</p>
            <h3 className="serif">
              {score.n} {score.n === 1 ? "month" : "months"} played
            </h3>
          </div>
          <dl>
            <div>
              <dt>Beat the Satrix 40</dt>
              <dd>
                {score.beatStx} of {score.n}
              </dd>
            </div>
            <div>
              <dt>Beat equal weight</dt>
              <dd>
                {score.beatEq} of {score.n}
              </dd>
            </div>
            <div>
              <dt>Average month</dt>
              <dd>
                {pct(score.you, 1)}{" "}
                <span className="muted">against {pct(score.stx, 1)}</span>
              </dd>
            </div>
            <div>
              <dt>Days past your forecast</dt>
              <dd>
                {score.hits}{" "}
                <span className="muted">
                  of {score.days}, about {(score.days / 100).toFixed(1)}{" "}
                  expected
                </span>
              </dd>
            </div>
          </dl>
          <button
            className="reset"
            onClick={() => {
              setPlayed([]);
              localStorage.removeItem(STORE);
            }}
          >
            Clear
          </button>
        </section>
      )}
      {err && month && <p className="note error">{err}</p>}
    </div>
  );
}
