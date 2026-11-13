/* Shared helpers for The Long Case prototypes: formatters, the issuance model and the ECharts-based time chart.
   Charts read every colour from CSS custom properties, so each design themes them with its own tokens. */
(function () {
  const reduce = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const css = (el, name) => getComputedStyle(el).getPropertyValue(name).trim();
  const resolve = (el, c) => (c && c.startsWith('--') ? css(el, c) : c);
  const rgba = (c, a) => { const k = d3.color(c); if (!k) return c; k.opacity = a; return k.formatRgb(); };
  /* The width a label will take, measured the way the canvas will draw it */
  const textWidth = (() => { let c = null; return (text, font) => { c = c || document.createElement('canvas').getContext('2d'); c.font = font; return c.measureText(text).width; }; })();
  /* The height of one row of mark names above a plot */
  /* True where the main pointer is a finger */
  const COARSE = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches;
  const MARK_ROW = 17;
  /* A series colour pulled toward the text colour, so a name can wear its line's colour and still read as text */
  const tint = (c, ink, k = 0.4) => (d3.color(c) && d3.color(ink) ? d3.interpolateRgb(c, ink)(k) : ink);

  /* Formatters */
  const compact = (v, digits = 1) => {
    if (v == null || isNaN(v)) return '–';
    if (v === 0) return '0';
    const a = Math.abs(v);
    /* Asking for 0 digits means "as few as this value needs", so axis ticks never round to duplicates */
    const d = (x) => {
      if (digits !== 0) return digits;
      const clean = (k) => Math.abs(x * k - Math.round(x * k)) < 1e-9;
      if (clean(1)) return 0;
      if (clean(10)) return 1;
      return clean(100) && Math.abs(x) < 10 ? 2 : 0;
    };
    if (a >= 1e12) return (v / 1e12).toFixed(d(v / 1e12)) + 'T';
    if (a >= 1e9) return (v / 1e9).toFixed(d(v / 1e9)) + 'B';
    if (a >= 1e6) return (v / 1e6).toFixed(d(v / 1e6)) + 'M';
    if (a >= 1e3) return (v / 1e3).toFixed(d(v / 1e3)) + 'K';
    return a >= 100 ? v.toFixed(0) : a >= 1 ? v.toFixed(d(v)) : v.toFixed(Math.max(d(v), 2));
  };
  const fmt = {
    compact,
    usd: (v, d = 1) => (v == null || isNaN(v) ? '–' : (v < 0 ? '-$' : '$') + compact(Math.abs(v), d)),
    near: (v, d = 1) => (v == null || isNaN(v) ? '–' : compact(v, d) + ' NEAR'),
    pct: (v, d = 1) => (v == null || isNaN(v) ? '–' : (v * 100).toFixed(d) + '%'),
    signedPct: (v, d = 2) => (v == null || isNaN(v) ? '–' : (v >= 0 ? '+' : '−') + Math.abs(v * 100).toFixed(d) + '%'),
    int: (v) => (v == null || isNaN(v) ? '–' : Math.round(v).toLocaleString('en-US')),
    date: (s) => new Date(s + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }),
    month: (s) => new Date(s + 'T00:00:00Z').toLocaleDateString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' }),
  };

  /* The issuance model used on every page. It starts from the warehouse's own break-even scenario
     (gold.fct_deflation_scenarios: current issuance at the measured capture rate), so it opens on the same
     figures as the scorecard. Everything is measured over the 30 days to the newest day whose fees are settled. */
  const LC = window.LC;
  const S0 = LC.thesis.scenarios.find((r) => r.scenario_id === 'current' && r.capture_case === 'measured');
  const DN0 = LC.thesis.dilutionNow;
  const baseline = {
    supply: (DN0.minted_30d_near * 365) / 30 / DN0.gross_inflation_rate,
    rate: DN0.gross_inflation_rate,
    price: S0.price_usd,
    burnYear: S0.burn_near_per_day * 365,
    volYear: S0.volume_usd_per_day * 365,
    feeYear: S0.volume_usd_per_day * 365 * S0.fee_rate,
    revYear: S0.volume_usd_per_day * 365 * S0.fee_rate * S0.capture_rate,
    mintedYearObserved: S0.issuance_near_per_day * 365,
  };
  baseline.takeBps = S0.fee_rate * S0.capture_rate * 1e4;
  /* Burn stays at its measured level, as in the warehouse: gas burned does not rise with swap volume */
  function model({ rate = baseline.rate, volMult = 1, takeBps = baseline.takeBps, price = baseline.price } = {}) {
    const minted = baseline.supply * rate;
    const burn = baseline.burnYear;
    const revUsd = baseline.volYear * volMult * (takeBps / 1e4);
    const bought = revUsd / price;
    const offset = burn + bought;
    const net = minted - offset;
    const breakEven = (minted - burn) / ((baseline.volYear * (takeBps / 1e4)) / price);
    return { rate, volMult, takeBps, price, minted, burn, revUsd, bought, offset, net, netRate: net / baseline.supply, covered: offset / minted, breakEven };
  }

  /* Run once an element is near the viewport, so each chart draws itself as it arrives.
     The timer is the fallback for hidden tabs and thumbnails, where nothing ever intersects. */
  function whenVisible(el, fn) {
    let done = false;
    const go = () => { if (done) return; done = true; io.disconnect(); clearTimeout(t); fn(); };
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) go(); }, { rootMargin: '120px' });
    io.observe(el);
    const t = setTimeout(go, 2200);
    return () => { done = true; io.disconnect(); clearTimeout(t); };
  }

  /* Everything a chart needs from the design's tokens */
  const theme = (el) => ({
    ink: css(el, '--chart-ink'), grid: css(el, '--chart-grid'), surface: css(el, '--chart-surface'), strong: css(el, '--chart-strong'), mark: css(el, '--chart-mark'),
    tipBg: css(el, '--tip-bg'), tipInk: css(el, '--tip-ink'), font: css(el, '--chart-font') || 'sans-serif',
  });
  const tooltipBase = (t) => ({
    backgroundColor: t.tipBg, borderWidth: 0, padding: [9, 11], confine: true, textStyle: { color: t.tipInk, fontSize: 12.5, fontFamily: t.font },
    extraCssText: 'border-radius:10px;box-shadow:0 12px 34px rgba(0,0,0,.28);',
  });
  const baseOption = (t) => ({ animation: !reduce(), animationDuration: 850, animationEasing: 'cubicOut', animationDurationUpdate: 480, animationEasingUpdate: 'cubicInOut', useUTC: true, textStyle: { fontFamily: t.font } });
  const axisText = (t) => ({ color: t.ink, fontSize: 12, fontFamily: t.font });
  const gradient = (top, bottom) => new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: top }, { offset: 1, color: bottom }]);
  /* A date label names a year, a month or a day, whichever is the finest step the axis shows */
  const dateFmt = [d3.utcFormat('%Y'), d3.utcFormat("%b '%y"), d3.utcFormat('%-d %b')];
  const tierOf = (days) => (days > 900 ? 0 : days > 200 ? 1 : 2);
  const UNITS = ['year', 'month', 'day'];

  /* Time series as line, area, bars or stacked bars. Same call everywhere; update() morphs to new data. */
  function timeChart(host, opts) {
    host.classList.add('lcc');
    let o = opts;
    const legend = document.createElement('div'); legend.className = 'lcc-legend';
    const box = document.createElement('div'); box.className = 'lcc-box'; box.style.width = '100%';
    host.append(legend, box);
    let ec = null;
    const ts = (d) => Date.parse(d + 'T00:00:00Z');

    /* Bars label the first bar of each year or two-month block, or every few weeks, by the span in view,
       so zooming in moves the labels from years to months to weeks. A bar chart keeps its plan in `bars`. */
    let bars = null;
    const barLabels = (i0, i1) => {
      const tier = tierOf((ts(o.x[i1]) - ts(o.x[i0])) / 864e5);
      const step = Math.max(1, Math.ceil((i1 - i0 + 1) / 6));
      const key = tier === 0 ? (d) => d.slice(0, 4) : tier === 1 ? (d) => d.slice(0, 4) + Math.floor((+d.slice(5, 7) - 1) / 2) : null;
      const keep = new Set();
      o.x.forEach((d, i) => { if (key ? !i || key(d) !== key(o.x[i - 1]) : (o.x.length - 1 - i) % step === 0) keep.add(i); });
      return { keep, tier, sig: key ? String(tier) : 'w' + step };
    };
    const barAxisLabel = (b) => ({ interval: (i) => b.keep.has(i), formatter: (v) => dateFmt[b.tier](new Date(ts(v))) });
    /* The zoom event arrives after ECharts has drawn the new window, so a changed plan draws once more in the same frame */
    const syncBars = () => {
      if (!ec || !bars) return;
      const z = (ec.getOption().dataZoom || [])[0];
      if (!z) return;
      const n = o.x.length - 1;
      const next = barLabels(Math.max(0, Math.floor(((z.start || 0) / 100) * n)), Math.min(n, Math.ceil(((z.end == null ? 100 : z.end) / 100) * n)));
      if (next.sig !== bars.sig) { bars = next; ec.setOption({ xAxis: { axisLabel: barAxisLabel(bars) } }); }
    };

    /* Event marks print their names above the plot. Two that fall close together would print on top of each other, and
       one near an edge would run off the chart. So each name takes the first free row above the plot, and a name that
       would cross an edge is set against its line instead of centred on it. Positions come from the drawn chart once
       there is one, and from the box's width before that. */
    let markSig = '';
    /* Names at the line ends wait for the first draw to finish. While a line is still being drawn its name rides the
       line's tip, where the names cannot be kept apart; once the lines are whole the names appear in their places. */
    let namesOn = false;
    const planMarks = (isBar, t) => {
      const list = (o.marks || []).filter((m) => m.d >= o.x[0] && m.d <= o.x[o.x.length - 1])
        .map((m) => ({ label: m.label, at: isBar ? o.x.reduce((best, d) => (d <= m.d ? d : best), o.x[0]) : ts(m.d), t: ts(m.d), row: 0, align: 'center' }));
      if (!list.length) return { list, rows: 0, sig: '' };
      const W = box.clientWidth || 640, left = 44, right = o.endLabels ? (o.compact ? 54 : 74) : 16;
      const x0 = ts(o.x[0]), x1 = ts(o.x[o.x.length - 1]);
      const where = (m) => {
        let px = NaN;
        if (ec) { try { px = ec.convertToPixel({ xAxisIndex: 0 }, m.at); } catch (e) { px = NaN; } }
        return Number.isFinite(px) ? px : left + ((m.t - x0) / Math.max(1, x1 - x0)) * (W - left - right);
      };
      const ends = [];
      list.map((m) => ({ m, cx: where(m), w: textWidth(m.label, `12px ${t.font}`) + 12 })).filter((k) => k.cx > 0 && k.cx < W).sort((a, b) => a.cx - b.cx).forEach(({ m, cx, w }) => {
        let l = cx - w / 2, r = cx + w / 2;
        if (r > W - 2 && cx - w > 0) { m.align = 'right'; r = cx + 2; l = r - w; } else if (l < 2) { m.align = 'left'; l = cx - 2; r = l + w; }
        while (m.row < 3 && ends[m.row] != null && l < ends[m.row] + 6) m.row++;
        ends[m.row] = Math.max(ends[m.row] == null ? -Infinity : ends[m.row], r);
      });
      return { list, rows: Math.max(...list.map((m) => m.row)), sig: list.map((m) => m.row + m.align[0]).join('') };
    };

    /* What a screen reader, or an agent reading the page, is told about the chart: its form, how many points it holds,
       and each series' first, newest and highest value with their dates, in the chart's own number and date formats.
       The library's own description prints dates as milliseconds and calls an area or bar chart a line chart. */
    const describe = () => {
      const day = o.tipDate || fmt.date;
      const form = o.type === 'stack' ? 'Stacked bar chart' : o.type === 'bar' ? 'Bar chart'
        : o.type === 'area' || o.series.some((s) => s.area) ? 'Area chart' : 'Line chart';
      const parts = o.series.map((s) => {
        const f = s.fmt || o.tipFmt || o.yFmt || compact;
        const ix = []; s.values.forEach((v, i) => { if (v != null && !isNaN(v)) ix.push(i); });
        if (!ix.length) return `${s.name}: no values`;
        const a = ix[0], b = ix[ix.length - 1], hi = ix.reduce((m, i) => (s.values[i] > s.values[m] ? i : m), a);
        return `${s.name}: first ${f(s.values[a])} (${day(o.x[a])}), newest ${f(s.values[b])} (${day(o.x[b])}), highest ${f(s.values[hi])} (${day(o.x[hi])})`;
      });
      const marks = (o.marks || []).filter((m) => m && m.label && m.d >= o.x[0] && m.d <= o.x[o.x.length - 1])
        .map((m) => `${String(m.label).replace(/\s+/g, ' ')} on ${fmt.date(m.d)}`);
      const soFar = o.open && o.through ? ` The last point is the period so far, to ${fmt.date(o.through)}.` : '';
      const soft = o.softDays && o.settled && o.x[o.x.length - 1] > o.settled ? ` Figures after ${fmt.date(o.settled)} can still be revised.` : '';
      return `${form}, ${o.x.length} points, ${day(o.x[0])} to ${day(o.x[o.x.length - 1])}. ${parts.join('. ')}.${marks.length ? ` Marked: ${marks.join('; ')}.` : ''}${soFar}${soft}`;
    };

    const build = () => {
      const t = theme(host);
      const isBar = o.type === 'bar' || o.type === 'stack';
      const fmtY = o.yFmt || compact;
      const span = (ts(o.x[o.x.length - 1]) - ts(o.x[0])) / 864e5;
      /* ECharts tags each time tick with the unit it falls on and how many finer levels of tick share the axis,
         so every label names the finest step in view: years at full span, then months, then days as you zoom in */
      const timeLabel = (v, _, x) => {
        const tm = x && x.time;
        const u = tm ? UNITS.indexOf(tm.lowerTimeUnit) : -1;
        return dateFmt[tm ? (u < 0 ? 2 : Math.min(2, u + (tm.level || 0))) : tierOf(span)](new Date(v));
      };
      bars = isBar ? barLabels(0, o.x.length - 1) : null;
      /* Zooming stops at eight points, so a weekly chart never shows hours */
      const minZoom = { minValueSpan: isBar ? Math.min(7, o.x.length - 1) : Math.min(8, o.x.length - 1) * ((ts(o.x[o.x.length - 1]) - ts(o.x[0])) / Math.max(1, o.x.length - 1)) };
      box.style.height = (o.height || 300) + 'px';
      const colours = o.series.map((s) => resolve(host, s.color));
      const lastIdx = o.series.map((s) => { let i = s.values.length - 1; while (i > 0 && s.values[i] == null) i--; return i; });
      const plan = planMarks(isBar, t);
      markSig = plan.sig;
      const markLine = plan.list.length ? {
        silent: true, symbol: 'none', animation: false,
        lineStyle: { color: t.mark, width: 1, type: 'solid' },
        label: { position: 'end', color: t.strong, fontSize: 12, fontFamily: t.font, formatter: (p) => p.name, backgroundColor: t.surface, padding: [2, 5], borderRadius: 4 },
        data: plan.list.map((m) => ({ name: m.label, xAxis: m.at, label: { distance: 5 + MARK_ROW * m.row, ...(m.align === 'center' ? {} : { align: m.align }) } })),
      } : undefined;

      /* Bars get gradient columns, with the latest one brightest; lines get a soft glow and a fading area */
      const barCount = o.x.length;
      /* Days after the settled day, in a view by day: their figures can still be revised, so they are drawn apart */
      const softN = o.softDays && o.settled ? o.x.filter((d) => d > o.settled).length : 0, softK = softN < barCount ? softN : 0;
      const radius = barCount > 70 ? 1.5 : barCount > 30 ? 3 : 4;
      const series = o.series.map((s, si) => {
        const c = colours[si];
        /* A bar chart can carry a series as a line on its own axis at the right, for a measure in another unit
           (a rate or an average beside a count). It sits on the bars' categories, so its points line up with them. */
        if (isBar && s.axis === 'right') {
          return {
            type: 'line', name: s.name, yAxisIndex: 1, data: s.values.map((v) => (v == null ? null : v)), smooth: 0.22, connectNulls: false, z: 6,
            showSymbol: barCount <= 40, symbol: 'circle', symbolSize: 6,
            lineStyle: { width: 2.25, color: c, cap: 'round', join: 'round', shadowColor: rgba(c, 0.38), shadowBlur: 9, shadowOffsetY: 3 },
            itemStyle: { color: c, borderColor: t.surface, borderWidth: 1.5 }, emphasis: { disabled: true },
          };
        }
        if (isBar) {
          const top = o.type === 'bar' || si === o.series.length - 1;
          return {
            type: 'bar', name: s.name, stack: o.type === 'stack' ? 's' : undefined, barMaxWidth: 26, barCategoryGap: barCount > 70 ? '12%' : '24%',
            /* A period still in progress is a lighter bar, so a short week or month is not read as a fall */
            data: s.values.map((v, i) => ({ value: v, itemStyle: (s.open && i === barCount - 1) || i >= barCount - softK ? { opacity: 0.4 } : o.type === 'bar' && i < barCount - 1 ? { opacity: 0.82 } : undefined })),
            itemStyle: { color: gradient(c, rgba(c, 0.58)), borderRadius: top ? [radius, radius, 0, 0] : 0 },
            emphasis: { focus: 'none', itemStyle: { opacity: 1, shadowBlur: 12, shadowColor: rgba(c, 0.4) } },
            markLine: si === 0 ? markLine : undefined,
          };
        }
        const hasArea = s.area || o.type === 'area';
        const pts = o.x.map((d, i) => [ts(d), s.values[i] == null || (o.log && s.values[i] <= 0) ? null : s.values[i]]);
        /* A total for a period still in progress, or days whose figures can still be revised: the line stops at the
           last firm point, and a dashed stretch leads on to a hollow dot */
        const n = pts.length, tail = softK || (s.open ? 1 : 0);
        const soFar = tail > 0 && n > tail && pts.slice(n - tail - 1).every((p) => p[1] != null);
        const stretch = soFar ? pts.slice(n - tail).map((p, j) => [{ coord: pts[n - tail - 1 + j], symbol: 'none', lineStyle: { color: c, width: 2, type: [4, 4] }, label: { show: false } }, { coord: p, symbol: 'none' }]) : [];
        const lines = si === 0 && markLine ? { ...markLine, data: [...markLine.data, ...stretch] } : stretch.length ? { silent: true, symbol: 'none', animation: false, data: stretch } : undefined;
        return {
          type: 'line', name: s.name, data: soFar ? [...pts.slice(0, n - tail), ...pts.slice(n - tail).flatMap((p, j) => [[(pts[n - tail - 1 + j][0] + p[0]) / 2, null], p])] : pts,
          smooth: o.step ? false : 0.22, step: o.step ? 'end' : false, showSymbol: false, symbol: 'circle', symbolSize: 9, connectNulls: false, z: 3 + si,
          lineStyle: { width: s.width || 2.25, color: c, cap: 'round', join: 'round', shadowColor: rgba(c, 0.38), shadowBlur: 9, shadowOffsetY: 3, type: s.dash ? 'dashed' : 'solid' },
          itemStyle: { color: c, borderColor: t.surface, borderWidth: 2 },
          areaStyle: hasArea ? { color: gradient(rgba(c, o.areaOpacity || 0.3), rgba(c, 0.01)) } : undefined,
          emphasis: { disabled: true },
          /* A name sits at the end of its line. Lines that end close together would print their names on top of each
             other, so the names move apart, up and down, with air between them (the line height), and each wears a tint of
             its line's colour, which still says whose it is once it has moved. */
          endLabel: { show: !!o.endLabels && namesOn, formatter: () => (s.label != null ? s.label : s.name), color: tint(c, t.strong), fontSize: 12, lineHeight: 17, fontWeight: 600, fontFamily: t.font, distance: 9 },
          labelLayout: o.endLabels ? { moveOverlap: 'shiftY' } : undefined,
          markPoint: { silent: true, symbol: 'circle', symbolSize: 9, itemStyle: soFar ? { color: t.surface, borderColor: c, borderWidth: 2 } : { color: c, borderColor: t.surface, borderWidth: 2 }, label: { show: false }, animation: false, data: [{ coord: [ts(o.x[lastIdx[si]]), s.values[lastIdx[si]]] }] },
          markLine: lines,
        };
      });

      return {
        ...baseOption(t),
        grid: { left: 4, right: o.endLabels ? (o.compact ? 54 : 74) : 16, top: plan.list.length ? 26 + MARK_ROW * plan.rows : 10, bottom: o.zoom ? 46 : 2, containLabel: true },
        tooltip: {
          ...tooltipBase(t), trigger: 'axis',
          axisPointer: isBar ? { type: 'shadow', shadowStyle: { color: rgba(t.strong, 0.06) } } : { type: 'line', lineStyle: { color: t.mark, width: 1, type: [3, 3] } },
          formatter: (ps) => {
            const list = Array.isArray(ps) ? ps : [ps];
            const raw = isBar ? list[0].axisValue : new Date(list[0].value[0]).toISOString().slice(0, 10);
            const value = (p) => (isBar ? (p.value && p.value.value !== undefined ? p.value.value : p.value) : p.value[1]);
            const rows = list.filter((p) => value(p) != null).map((p) => {
              const s = o.series[p.seriesIndex];
              return `<div class="lcc-tip-row"><i style="background:${colours[p.seriesIndex]}"></i><span>${s.name}</span><b>${(s.fmt || o.tipFmt || fmtY)(value(p))}</b></div>`;
            }).join('');
            const total = o.type === 'stack' ? `<div class="lcc-tip-row lcc-tip-total"><span>Total</span><b>${(o.tipFmt || fmtY)(d3.sum(list, value))}</b></div>` : '';
            const soFar = o.open && o.through && raw === o.x[o.x.length - 1] ? `, to ${new Date(o.through + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })}` : '';
            const soft = softK && raw > o.settled ? ', can still be revised' : '';
            return `<div class="lcc-tip-head">${(o.tipDate || fmt.date)(raw)}${soFar}${soft}</div>${rows}${total}`;
          },
        },
        xAxis: isBar
          ? { type: 'category', data: o.x, axisLine: { lineStyle: { color: t.grid } }, axisTick: { show: false }, axisLabel: { ...axisText(t), ...barAxisLabel(bars), hideOverlap: true } }
          : { type: 'time', boundaryGap: false, axisLine: { lineStyle: { color: t.grid } }, axisTick: { show: false }, splitLine: { show: false }, splitNumber: o.compact ? 3 : 6, axisLabel: { ...axisText(t), formatter: timeLabel, hideOverlap: true } },
        yAxis: (() => {
          const left = {
            type: o.log ? 'log' : 'value', logBase: 10, min: o.yDomain ? o.yDomain[0] : o.floor, max: o.yDomain ? o.yDomain[1] : undefined, interval: o.yStep, splitNumber: o.compact ? 3 : 4,
            axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.grid, width: 1 } }, axisLabel: { ...axisText(t), formatter: (v) => fmtY(v) },
          };
          const second = isBar && o.series.find((s) => s.axis === 'right');
          if (!second) return left;
          /* The second axis has no grid lines of its own, and starts at zero as the bars do */
          return [left, { type: 'value', position: 'right', min: 0, splitNumber: o.compact ? 3 : 4, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { ...axisText(t), formatter: (v) => (second.yFmt || second.fmt || fmtY)(v) } }];
        })(),
        dataZoom: o.zoom ? [
          /* Zoom takes the wheel only with Ctrl held, which is also how a trackpad pinch arrives. Under a finger a drag
             moves the chart without stopping the page, so a swipe that starts on the plot still scrolls. */
          { type: 'inside', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false, moveOnMouseMove: true, preventDefaultMouseMove: !COARSE, ...minZoom },
          { type: 'slider', ...minZoom, height: 24, bottom: 4, borderColor: 'transparent', backgroundColor: rgba(t.strong, 0.04), fillerColor: rgba(colours[0], 0.14), handleStyle: { color: t.surface, borderColor: t.mark }, moveHandleSize: 0, showDetail: false, dataBackground: { lineStyle: { color: rgba(colours[0], 0.5), width: 1 }, areaStyle: { color: rgba(colours[0], 0.14) } }, selectedDataBackground: { lineStyle: { color: colours[0], width: 1 }, areaStyle: { color: rgba(colours[0], 0.3) } }, labelFormatter: '' },
        ] : [],
        aria: { enabled: true, label: { description: o.alt || (() => { try { return describe(); } catch (e) { return undefined; } })() } },
        series,
      };
    };

    const paintLegend = () => {
      legend.innerHTML = o.series.length > 1 && !o.noLegend ? o.series.map((s) => `<span class="lcc-key"><i style="background:${resolve(host, s.color)}"></i>${s.name}</span>`).join('') : '';
      legend.hidden = !legend.innerHTML;
    };
    /* Tokens only resolve once the host is in the page, so the legend paints again on the next frame */
    paintLegend();
    requestAnimationFrame(paintLegend);
    box.style.height = (o.height || 300) + 'px';
    /* A zoomable chart leaves a plain wheel to the page. ECharts stops every wheel event inside the plot before it asks
       whether the zoom wants it, so without Ctrl a scroll over the plot moved neither the page nor the chart. This
       listener sits on the chart's box and hears the wheel first: with no Ctrl it keeps the event from ECharts, and
       the page scrolls as it does anywhere else. */
    box.addEventListener('wheel', (e) => { if (!e.ctrlKey) e.stopPropagation(); }, { capture: true, passive: true });
    const mount = () => {
      paintLegend();
      ec = echarts.init(box, null, { renderer: 'canvas' });
      if (o.group) { ec.group = o.group; echarts.connect(o.group); }
      ec.setOption(build());
      replan();
      ec.on('datazoom', () => { replan(); syncBars(); });
      const showNames = () => {
        ec.off('finished', showNames);
        namesOn = true;
        if (o.endLabels && o.type !== 'bar' && o.type !== 'stack') ec.setOption({ series: o.series.map(() => ({ endLabel: { show: true } })) });
      };
      ec.on('finished', showNames);
    };
    /* The names of the marks are placed again whenever the marks have moved: after the first draw, a zoom or a resize */
    const replan = () => {
      if (!ec || !(o.marks || []).length) return;
      if (planMarks(o.type === 'bar' || o.type === 'stack', theme(host)).sig !== markSig) ec.setOption(build(), { replaceMerge: ['series'] });
    };
    const cancel = whenVisible(host, mount);
    const ro = new ResizeObserver(() => { if (ec) { ec.resize(); replan(); syncBars(); } });
    ro.observe(box);
    return {
      update(next) { o = { ...o, ...next }; paintLegend(); if (ec) { ec.setOption(build(), { replaceMerge: ['series', 'dataZoom'] }); ec.resize(); replan(); syncBars(); } },
      redraw() { paintLegend(); if (ec) { ec.setOption(build(), true); replan(); } },
      destroy() { cancel(); ro.disconnect(); if (ec) ec.dispose(); host.innerHTML = ''; },
    };
  }

  /* Plain-SVG micro charts for tiles and tables */
  let uid = 0;
  function spark(host, values, { color = '--chart-1', height = 34, area = true, stroke = 1.75 } = {}) {
    const w = host.clientWidth || 120;
    const clean = values.filter((v) => v != null);
    const x = d3.scaleLinear().domain([0, clean.length - 1]).range([1, w - 6]);
    const y = d3.scaleLinear().domain(d3.extent(clean)).nice().range([height - 3, 6]);
    const c = resolve(host, color);
    const id = 'lcc-g' + uid++;
    const line = d3.line().x((_, i) => x(i)).y((v) => y(v)).curve(d3.curveMonotoneX);
    const a = d3.area().x((_, i) => x(i)).y0(height).y1((v) => y(v)).curve(d3.curveMonotoneX);
    host.innerHTML = `<svg viewBox="0 0 ${w} ${height}" width="100%" height="${height}" aria-hidden="true" style="display:block">
      <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c}" stop-opacity=".32"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></linearGradient></defs>
      ${area ? `<path d="${a(clean)}" fill="url(#${id})"/>` : ''}
      <path d="${line(clean)}" fill="none" stroke="${c}" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${x(clean.length - 1)}" cy="${y(clean[clean.length - 1])}" r="3.2" fill="${c}"/></svg>`;
  }
  function miniBars(host, values, { color = '--chart-1', height = 58, count = 28 } = {}) {
    const w = host.clientWidth || 200;
    const vals = values.filter((v) => v != null).slice(-count);
    const c = resolve(host, color);
    const id = 'lcc-g' + uid++;
    const max = d3.max(vals) || 1, step = w / vals.length, bw = Math.max(1.5, step * 0.68);
    host.innerHTML = `<svg viewBox="0 0 ${w} ${height}" width="100%" height="${height}" aria-hidden="true" style="display:block"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c}"/><stop offset="1" stop-color="${c}" stop-opacity=".35"/></linearGradient></defs>
      ${vals.map((v, i) => { const h = Math.max(1, (v / max) * (height - 4)); return `<rect x="${(i * step).toFixed(1)}" y="${(height - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="${Math.min(2, bw / 2)}" fill="url(#${id})" opacity="${i === vals.length - 1 ? 1 : 0.72}"/>`; }).join('')}</svg>`;
  }
  /* Progress ring for one share */
  const ring = (value, { size = 52, width = 6, color = 'var(--accent, #00ec97)', track = 'rgba(255,255,255,.14)' } = {}) => {
    const r = (size - width) / 2, c = 2 * Math.PI * r;
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true" style="display:block;transform:rotate(-90deg)"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${track}" stroke-width="${width}"/><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-dasharray="${(Math.min(1, value) * c).toFixed(1)} ${c.toFixed(1)}"/></svg>`;
  };

  /* Ranked bars with the value at the tip */
  function hbars(host, items, { color = '--chart-1', fmtV = compact, labelWidth = 150, emphasis = null, mute = '--chart-mute' } = {}) {
    const max = d3.max(items, (d) => d.value) || 1;
    const c = resolve(host, color), m = resolve(host, mute);
    host.classList.add('lcc-rank');
    host.innerHTML = items.map((d) => {
      const on = emphasis == null || d.label === emphasis;
      return `<div class="lcc-rbar" style="grid-template-columns:minmax(0,${labelWidth}px) 1fr"><span class="lcc-rl${on && emphasis ? ' on' : ''}">${d.label}</span><span class="lcc-rt"><i style="width:${Math.max(0.8, (d.value / max) * 84)}%;background:${d.color ? `linear-gradient(90deg,${rgba(d.color, 0.55)},${d.color})` : on ? `linear-gradient(90deg,${rgba(c, 0.55)},${c})` : m}"></i><b>${fmtV(d.value)}</b></span></div>`;
    }).join('');
  }

  /* Shared lookups for the data */
  const weeklyOf = (key, from) => {
    const w = LC.weekly; const start = from ? w.d.findIndex((d) => d >= from) : 0;
    return { x: w.d.slice(start), v: w[key].slice(start) };
  };
  const priceAt = (() => { const m = new Map(LC.weekly.d.map((d, i) => [d, LC.weekly.price[i]])); return (d) => m.get(d); })();
  const issuanceValue = () => LC.weekly.d.map((d, i) => (LC.weekly.minted[i] != null && LC.weekly.price[i] != null ? LC.weekly.minted[i] * LC.weekly.price[i] : null));
  const rangeFrom = (range) => {
    const end = new Date(LC.asOf + 'T00:00:00Z');
    const back = { '30D': 30, '90D': 90, '6M': 182, '1Y': 365, '2Y': 730 }[range];
    if (!back) return null;
    return new Date(end - back * 864e5).toISOString().slice(0, 10);
  };

  /* Bar linking the prototypes for review */
  function reviewBar(current) {
    const names = { D: 'Hub', A: 'Terminal' };
    const bar = document.createElement('nav');
    bar.className = 'review-bar'; bar.setAttribute('aria-label', 'Switch prototype');
    bar.innerHTML = `<a href="index.html" class="rb-home">Proposal</a>` + Object.keys(names).map((k) => `<a href="design-${k.toLowerCase()}.html"${k === current ? ' aria-current="page"' : ''}>${names[k]}</a>`).join('');
    document.body.append(bar);
    const style = document.createElement('style');
    style.textContent = `.review-bar{position:fixed;z-index:60;right:max(14px,env(safe-area-inset-right,0px));bottom:calc(14px + env(safe-area-inset-bottom,0px));display:flex;gap:2px;padding:3px;background:rgba(20,22,22,.9);border-radius:10px;font:500 12px/1 system-ui,sans-serif;backdrop-filter:blur(8px);box-shadow:0 6px 24px rgba(0,0,0,.28)}
    .review-bar a{color:#d8dbda;text-decoration:none;padding:7px 9px;border-radius:7px}.review-bar a:hover{background:rgba(255,255,255,.12)}.review-bar a:focus-visible{outline:2px solid #00ec97;outline-offset:1px}.review-bar a[aria-current]{background:#00ec97;color:#0c1512}.review-bar .rb-home{border-right:1px solid rgba(255,255,255,.14);border-radius:7px 0 0 7px;margin-right:2px}`;
    document.head.append(style);
  }

  /* Base styles every chart host needs */
  const base = document.createElement('style');
  base.textContent = `.lcc-legend{display:flex;flex-wrap:wrap;gap:4px 14px;margin:0 0 8px;font-size:13px;color:var(--chart-strong)}.lcc-key{display:inline-flex;align-items:center;gap:6px}.lcc-key i{width:10px;height:10px;border-radius:3px;display:block}
  .lcc-tip-head{opacity:.68;margin-bottom:5px;font-size:11.5px}.lcc-tip-row{display:flex;align-items:center;gap:7px;padding:1.5px 0;min-width:150px}.lcc-tip-row i{width:8px;height:8px;border-radius:50%;flex:none}.lcc-tip-row span{flex:1;min-width:0}.lcc-tip-row b{font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}.lcc-tip-total{border-top:1px solid rgba(128,128,128,.3);margin-top:4px;padding-top:5px}
  .lcc-rank{display:grid;gap:3px}.lcc-rbar{display:grid;gap:12px;align-items:center;padding:5px 0}.lcc-rl{font-size:13.5px;overflow-wrap:anywhere;line-height:1.25;color:var(--chart-strong)}.lcc-rl.on{font-weight:650}.lcc-rt{display:flex;align-items:center;gap:9px;min-width:0}.lcc-rt i{display:block;height:14px;border-radius:0 4px 4px 0}.lcc-rt b{font-weight:600;font-size:12.5px;font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--chart-strong)}`;
  document.head.append(base);

  window.LCC = { fmt, model, baseline, timeChart, spark, miniBars, ring, hbars, weeklyOf, priceAt, issuanceValue, rangeFrom, reviewBar, reduce, whenVisible, theme, tooltipBase, baseOption, axisText, gradient, rgba, resolve, textWidth };
})();
