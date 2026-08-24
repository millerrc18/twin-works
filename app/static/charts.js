// Plotly helpers — theme-aware (read CSS vars from the current theme).

function _tok(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
function _theme() {
  return {
    panel: _tok('--panel', '#ffffff'),
    text: _tok('--text', '#1a1f2e'),
    muted: _tok('--muted', '#5b6473'),
    faint: _tok('--faint', '#9aa4b6'),
    border2: _tok('--border2', '#eef0f3'),
    brand: _tok('--brand', '#2f6fdb'),
    late: _tok('--late-tx', '#b42318'),
    early: _tok('--early-tx', '#1e7a44'),
    wip: _tok('--wip-bg', '#f5a623'),
    font: "'JetBrains Mono', ui-monospace, Consolas, monospace",
  };
}

// Forecast bullet/range chart: one row per unit, X = ship date.
//   • bar P50 -> P80 (schedule uncertainty), colored by status (green/amber/red)
//   • whisker (tick) at sim floor, left of P50 (best-case, quiet)
//   • target (RTG) = high-contrast vertical tick crossing the row (reference, not a data point)
//   • +Nd / -Nd slip label right-aligned (P50 - target); worst-slip sorted to top
// Data rows: {serial, sim, p50, p80, target, status:'red'|'amber'|'green', slip:int, stalled}
function renderForecastBullet(divId, data) {
  const t = _theme();
  const statusColor = { red: t.late, amber: t.wip, green: t.early };
  // worst-first: largest slip at array index 0, which on a reversed categorical axis
  // renders at the TOP so problems draw the eye first.
  const live = data.filter(d => !d.stalled && d.p50 && d.p80)
                   .sort((a, b) => (b.slip ?? -9999) - (a.slip ?? -9999));
  if (!live.length) {
    Plotly.newPlot(divId, [], { height: 120, paper_bgcolor: t.panel, plot_bgcolor: t.panel,
      annotations: [{ text: 'No active units to forecast', showarrow: false,
        font: { color: t.faint, size: 13 } }] }, { displayModeBar: false });
    return;
  }
  const serials = live.map(d => d.serial);
  const ms = d => new Date(d).getTime();
  const DAY = 86400000;

  // P50->P80 range bars: base=P50 (ISO date so Plotly keeps the axis a DATE axis — an
  // all-numeric base silently re-types the axis to linear and breaks date ticks/range),
  // width=(P80-P50) in ms. Enforce a >=1.5-day floor so a low-uncertainty bar stays visible.
  const bar = {
    type: 'bar', orientation: 'h', y: serials,
    base: live.map(d => d.p50),
    x: live.map(d => Math.max(ms(d.p80) - ms(d.p50), 1.5 * DAY)),
    marker: { color: live.map(d => statusColor[d.status] || t.brand),
              line: { width: 0 } },
    width: 0.5, hoverinfo: 'skip', showlegend: false, name: 'P50–P80',
  };

  // Sim-floor whisker: a short quiet tick left of P50 (best-case floor)
  const sim = {
    type: 'scatter', mode: 'markers', y: serials, x: live.map(d => d.sim),
    marker: { symbol: 'line-ns-open', size: 12, color: t.faint,
              line: { width: 1.5, color: t.faint } },
    hovertemplate: '%{y} sim floor %{x|%b %d}<extra></extra>',
    showlegend: false, name: 'sim floor',
  };

  // P50 point (the "likely" anchor) on the left edge of the bar
  const p50pt = {
    type: 'scatter', mode: 'markers', y: serials, x: live.map(d => d.p50),
    marker: { symbol: 'circle', size: 7, color: t.text },
    hovertemplate: '%{y} P50 %{x|%b %d}<extra></extra>',
    showlegend: false, name: 'P50',
  };

  // Target (RTG) reference — a tall vertical tick per row. Drawn as a SCATTER trace with a
  // categorical y (serial) so the y-axis stays categorical. (Numeric shape y-coords silently
  // re-type the axis to linear and collapse every row onto one line — the bug this replaces.)
  const target = {
    type: 'scatter', mode: 'markers', y: serials, x: live.map(d => d.target),
    marker: { symbol: 'line-ns', size: 18, color: t.text,
              line: { width: 2, color: t.text } },
    hovertemplate: '%{y} RTG target %{x|%b %d}<extra></extra>',
    showlegend: false, name: 'target',
  };

  // Slip labels pinned to the right margin (annotations in paper x)
  const anns = live.map((d, i) => ({
    xref: 'paper', x: 1.0, xanchor: 'left',
    yref: 'y', y: d.serial,
    text: (d.slip > 0 ? '+' : '') + (d.slip ?? 0) + 'd',
    showarrow: false, font: { family: t.font, size: 11,
      color: d.status === 'green' ? t.early : (d.status === 'amber' ? t.wip : t.late) },
  }));

  // Tight x-range to the actual data (sim/P50/P80/target across all rows) + ~4-day pad,
  // so clustered forecasts fill the width instead of collapsing into a thin band.
  const xs = [];
  live.forEach(d => { [d.sim, d.p50, d.p80, d.target].forEach(v => { if (v) xs.push(ms(v)); }); });
  // range as ISO date strings (keep the axis a date axis; numeric range can re-type it linear)
  const iso = m => new Date(m).toISOString().slice(0, 10);
  const xmin = iso(Math.min(...xs) - 4 * DAY), xmax = iso(Math.max(...xs) + 6 * DAY);

  const rowH = 26;
  const layout = {
    barmode: 'overlay',
    margin: { l: 84, r: 52, t: 8, b: 34 },
    font: { family: "'Inter',system-ui,sans-serif", color: t.muted, size: 11 },
    xaxis: { type: 'date', gridcolor: t.border2, tickfont: { family: t.font },
             autorange: false, range: [xmin, xmax],
             title: { text: 'ship date   ·   bar = P50–P80  |  vertical tick = RTG target  |  whisker = sim floor',
                      font: { size: 10, color: t.faint } } },
    yaxis: { automargin: true, autorange: 'reversed', tickfont: { family: t.font },
             showgrid: false, categoryorder: 'array', categoryarray: serials },
    annotations: anns,
    height: Math.max(140, live.length * rowH + 60),
    paper_bgcolor: t.panel, plot_bgcolor: t.panel, bargap: 0.45,
  };
  Plotly.newPlot(divId, [bar, sim, p50pt, target], layout, { responsive: true, displayModeBar: false });
  _remember(divId, renderForecastBullet, data);
}

// Bias-over-time trend: one line per program, x=sync date, y=measured optimism bias (days).
// bias -> 0 = the forecast is converging on reality. A dashed y=0 line marks "unbiased".
// data: [{at, program, bias, n_scored, mode}]  (already time-sorted).
function renderBiasTrend(divId, data) {
  const t = _theme();
  if (!data || !data.length) {
    Plotly.newPlot(divId, [], { height: 120, paper_bgcolor: t.panel, plot_bgcolor: t.panel,
      annotations: [{ text: 'No sync history yet — run a sync to start the trend',
        showarrow: false, font: { color: t.faint, size: 12 } }] }, { displayModeBar: false });
    _remember(divId, renderBiasTrend, data); return;
  }
  const colors = { ELEV: t.brand, RAD: t.wip, AEGIS: t.early };
  const progs = [...new Set(data.map(d => d.program))];
  const traces = progs.map(p => {
    const rows = data.filter(d => d.program === p);
    return {
      type: 'scatter', mode: 'lines+markers', name: p,
      x: rows.map(d => d.at), y: rows.map(d => d.bias),
      line: { color: colors[p] || t.muted, width: 2 },
      marker: { size: 6, color: colors[p] || t.muted },
      hovertemplate: p + ' %{x|%b %d}: bias %{y}d<extra></extra>',
    };
  });
  const layout = {
    margin: { l: 48, r: 16, t: 10, b: 36 },
    font: { family: "'Inter',system-ui,sans-serif", color: t.muted, size: 11 },
    xaxis: { type: 'date', gridcolor: t.border2, tickfont: { family: t.font } },
    yaxis: { title: { text: 'bias (days)', font: { size: 10 } }, gridcolor: t.border2,
             zeroline: true, zerolinecolor: t.faint, tickfont: { family: t.font } },
    legend: { orientation: 'h', y: 1.16, font: { color: t.muted } },
    height: 240, paper_bgcolor: t.panel, plot_bgcolor: t.panel,
    shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 0, y1: 0,
               line: { color: t.faint, width: 1, dash: 'dash' } }],
  };
  Plotly.newPlot(divId, traces, layout, { responsive: true, displayModeBar: false });
  _remember(divId, renderBiasTrend, data);
}

function renderBottleneckBar(divId, data) {
  const t = _theme();
  const wcs = data.map(d => d.wc);
  const util = data.map(d => d.util);
  const colors = data.map(d => d.util > 100 ? t.late : (d.util > 80 ? t.wip : t.brand));
  const trace = {
    x: util, y: wcs, type: 'bar', orientation: 'h',
    marker: { color: colors }, text: util.map(u => u + '%'), textposition: 'auto',
    textfont: { family: t.font, color: t.text },
  };
  const layout = {
    margin: { l: 72, r: 20, t: 10, b: 34 },
    font: { family: "'Inter',system-ui,sans-serif", color: t.muted, size: 11 },
    xaxis: { title: { text: 'peak weekly util %', font: { size: 10 } }, gridcolor: t.border2, tickfont: { family: t.font } },
    yaxis: { automargin: true, autorange: 'reversed', tickfont: { family: t.font } },
    shapes: [{ type: 'line', x0: 100, x1: 100, y0: -0.5, y1: wcs.length - 0.5,
               line: { color: t.late, width: 1, dash: 'dash' } }],
    height: 250, paper_bgcolor: t.panel, plot_bgcolor: t.panel,
  };
  Plotly.newPlot(divId, [trace], layout, { responsive: true, displayModeBar: false });
}

// Remember the last render per div so a theme toggle can fully re-color (per-row bar
// colors + token-derived styling are baked at render time, so a resize alone won't retheme).
const _lastRender = {};
function _remember(divId, fn, data) { _lastRender[divId] = { fn, data }; }

// re-theme charts when the theme toggles: re-call the original render with its data so
// per-row colors, target ticks, and slip labels pick up the new theme tokens.
document.addEventListener('click', (e) => {
  if (e.target.closest && e.target.closest('.tgl')) {
    setTimeout(() => {
      Object.entries(_lastRender).forEach(([divId, r]) => {
        if (document.getElementById(divId)) r.fn(divId, r.data);
      });
      // any charts not tracked (bottleneck etc.) at least repaint responsively
      window.dispatchEvent(new Event('resize'));
    }, 60);
  }
});
