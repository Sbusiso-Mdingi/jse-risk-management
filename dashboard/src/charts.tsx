import { useRef, useState } from "react";
import { fmtDate, pct, short } from "./format";

const W = 760;

function scaleLinear(d0: number, d1: number, r0: number, r1: number) {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v: number) => r0 + (v - d0) * k;
}

function ticks(min: number, max: number, count = 4) {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-12; v += step) out.push(+v.toFixed(10));
  return out;
}

function dateTicks(dates: string[]) {
  const out: { i: number; label: string }[] = [];
  if (dates.length < 2) return out;
  const spanYears = (Date.parse(dates[dates.length - 1]) - Date.parse(dates[0])) / 3.15e10;
  const seen = new Set<string>();
  dates.forEach((d, i) => {
    if (spanYears > 2) {
      const y = d.slice(0, 4);
      if (!seen.has(y)) {
        seen.add(y);
        if (i > 0 && +y % (spanYears > 9 ? 2 : 1) === 0) out.push({ i, label: y });
      }
    } else if (spanYears > 0.25) {
      const m = d.slice(0, 7);
      if (!seen.has(m)) {
        seen.add(m);
        if (i > 0) out.push({ i, label: fmtDate(d, { month: "short", year: "2-digit" }) });
      }
    } else if (i % Math.max(1, Math.round(dates.length / 6)) === 0) {
      out.push({ i, label: fmtDate(d, { day: "numeric", month: "short" }) });
    }
  });
  return out;
}

export type Line = { key: string; label: string; values: number[]; tone: "main" | "bench" | "other" };

export function GrowthChart({ dates, lines, label }: { dates: string[]; lines: Line[]; label: string }) {
  const H = 300;
  const pad = { l: 46, r: 12, t: 12, b: 28 };
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const all = lines.flatMap((l) => l.values).filter((v) => Number.isFinite(v));
  const min = Math.min(1, ...all);
  const max = Math.max(1, ...all);
  const x = scaleLinear(0, Math.max(1, dates.length - 1), pad.l, W - pad.r);
  const y = scaleLinear(min - (max - min) * 0.05, max + (max - min) * 0.05, H - pad.b, pad.t);
  const path = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  const ordered = [...lines].sort((a, b) => (a.tone === "main" ? 1 : 0) - (b.tone === "main" ? 1 : 0));
  const shown = lines.filter((l) => l.tone !== "other");
  const onMove = (e: React.MouseEvent) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (dates.length - 1));
    setHover(i >= 0 && i < dates.length ? i : null);
  };
  return (
    <svg ref={ref} className="chart" viewBox={`0 0 ${W} ${H}`} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label={label}>
      {ticks(min, max).map((t) => (
        <g key={t}>
          <path d={`M${pad.l} ${y(t)}H${W - pad.r}`} stroke="var(--border)" />
          <text x={pad.l - 8} y={y(t) + 3} textAnchor="end">
            {t.toFixed(2)}
          </text>
        </g>
      ))}
      <path d={`M${pad.l} ${y(1)}H${W - pad.r}`} stroke="var(--border-strong)" strokeDasharray="2 3" />
      {dateTicks(dates).map((t) => (
        <text key={t.i} x={x(t.i)} y={H - 8} textAnchor="middle">
          {t.label}
        </text>
      ))}
      {ordered.map((l) => (
        <path
          key={l.key}
          d={path(l.values)}
          fill="none"
          stroke={l.tone === "main" ? "var(--primary)" : l.tone === "bench" ? "#b58b3c" : "var(--border-strong)"}
          strokeWidth={l.tone === "main" ? 2 : l.tone === "bench" ? 1.4 : 0.9}
          strokeDasharray={l.tone === "bench" ? "5 3" : undefined}
          opacity={l.tone === "other" ? 0.7 : 1}
        />
      ))}
      {hover != null && (
        <g pointerEvents="none">
          <path d={`M${x(hover)} ${pad.t}V${H - pad.b}`} stroke="var(--foreground)" strokeOpacity=".4" />
          <g transform={`translate(${Math.min(x(hover) + 10, W - 200)} ${pad.t + 6})`}>
            <rect width="190" height={22 + 15 * shown.length} fill="var(--background)" stroke="var(--border-strong)" />
            <text x="10" y="16" style={{ fill: "var(--foreground)" }}>
              {fmtDate(dates[hover])}
            </text>
            {shown.map((l, k) => (
              <text key={l.key} x="10" y={31 + 15 * k}>
                {l.label} {pct(l.values[hover] - 1, 1)}
              </text>
            ))}
          </g>
        </g>
      )}
    </svg>
  );
}

export function VarChart({ dates, r, v }: { dates: string[]; r: number[]; v: number[] }) {
  const H = 280;
  const pad = { l: 46, r: 12, t: 12, b: 28 };
  const lo = Math.min(...r, ...v.map((x) => -x));
  const hi = Math.max(...r);
  const x = scaleLinear(0, dates.length - 1, pad.l, W - pad.r);
  const y = scaleLinear(lo * 1.05, hi * 1.05, H - pad.b, pad.t);
  const line = v.map((q, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(-q).toFixed(1)}`).join("");
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Daily returns against the 99% value at risk forecast">
      {ticks(lo, hi, 5).map((t) => (
        <g key={t}>
          <path d={`M${pad.l} ${y(t)}H${W - pad.r}`} stroke={t === 0 ? "var(--foreground)" : "var(--border)"} strokeOpacity={t === 0 ? 0.4 : 1} />
          <text x={pad.l - 8} y={y(t) + 3} textAnchor="end">
            {pct(t, 0)}
          </text>
        </g>
      ))}
      {r.map((ret, i) => {
        const hit = ret < -v[i];
        return <circle key={i} cx={x(i)} cy={y(ret)} r={hit ? 2.8 : 1.1} fill={hit ? "var(--negative)" : "var(--border-strong)"} opacity={hit ? 1 : 0.6} />;
      })}
      <path d={line} fill="none" stroke="var(--primary)" strokeWidth="1.4" />
      {dateTicks(dates).map((t) => (
        <text key={t.i} x={x(t.i)} y={H - 8} textAnchor="middle">
          {t.label}
        </text>
      ))}
    </svg>
  );
}

export function FrontierChart({
  frontier,
  assets,
  portfolio,
  rf,
}: {
  frontier: { ret: number; vol: number }[];
  assets: { ticker: string; ret: number; vol: number; weight: number }[];
  portfolio: { ret: number; vol: number };
  rf: number;
}) {
  const H = 320;
  const pad = { l: 50, r: 16, t: 14, b: 34 };
  const vols = [...frontier.map((p) => p.vol), ...assets.map((a) => a.vol), portfolio.vol, 0];
  const rets = [...frontier.map((p) => p.ret), ...assets.map((a) => a.ret), portfolio.ret, rf];
  const xmax = Math.max(...vols) * 1.08;
  const ylo = Math.min(...rets);
  const yhi = Math.max(...rets);
  const span = yhi - ylo || 0.1;
  const x = scaleLinear(0, xmax, pad.l, W - pad.r);
  const y = scaleLinear(ylo - span * 0.08, yhi + span * 0.08, H - pad.b, pad.t);
  const path = frontier.map((p, i) => `${i ? "L" : "M"}${x(p.vol).toFixed(1)} ${y(p.ret).toFixed(1)}`).join("");
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Efficient frontier, shares and the chosen portfolio">
      {ticks(ylo - span * 0.08, yhi + span * 0.08, 5).map((t) => (
        <g key={t}>
          <path d={`M${pad.l} ${y(t)}H${W - pad.r}`} stroke={t === 0 ? "var(--foreground)" : "var(--border)"} strokeOpacity={t === 0 ? 0.4 : 1} />
          <text x={pad.l - 8} y={y(t) + 3} textAnchor="end">
            {pct(t, 0)}
          </text>
        </g>
      ))}
      {ticks(0, xmax, 5).map((t) => (
        <text key={t} x={x(t)} y={H - 12} textAnchor="middle">
          {pct(t, 0)}
        </text>
      ))}
      <text x={W - pad.r} y={H - 0} textAnchor="end">
        VOLATILITY (ANNUAL)
      </text>
      <circle cx={x(0)} cy={y(rf)} r="3" fill="var(--foreground)" />
      <text x={x(0) + 6} y={y(rf) - 6}>
        T-BILL
      </text>
      {assets.map((a) => (
        <g key={a.ticker}>
          <circle cx={x(a.vol)} cy={y(a.ret)} r={a.weight > 1e-4 ? 3.2 : 2.2} fill={a.weight > 1e-4 ? "var(--foreground)" : "var(--border-strong)"} opacity=".75" />
          <text x={x(a.vol) + 5} y={y(a.ret) + 3} style={{ fontSize: 9 }}>
            {short(a.ticker)}
          </text>
        </g>
      ))}
      <path d={path} fill="none" stroke="var(--primary)" strokeWidth="2" />
      <circle cx={x(portfolio.vol)} cy={y(portfolio.ret)} r="6" fill="none" stroke="#b58b3c" strokeWidth="2.2" />
      <text x={x(portfolio.vol) + 9} y={y(portfolio.ret) - 8} style={{ fill: "#8a6526" }}>
        PORTFOLIO
      </text>
    </svg>
  );
}
