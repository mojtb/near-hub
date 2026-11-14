/* Richer data forms for the Hub and the Terminal: treemap, flow diagram, bump chart, bubble chart, take-rate scatter,
   bars with targets, stacked columns, rank matrix, nested log bars, calendar stripes and the ledger strip.
   Colour follows the entity everywhere, so a chain keeps its hue from chart to chart. */
(function () {
  const { fmt, whenDrawable, theme, tooltipBase, baseOption, axisText, gradient, rgba, textWidth } = LCC;
  const HUE = {
    ethereum: '#4f7fe8', eth: '#4f7fe8', solana: '#8a70e0', sol: '#8a70e0', near: '#00b37a', tron: '#e5604f',
    zec: '#e0a02a', btc: '#0f9a8a', avalanche: '#d97f2e', sui: '#e27fa8', aptos: '#3f9a5a', ton: '#7f8c9a', other: '#8b918f', hidden: '#8b918f',
  };
  const NAME = { eth: 'Ethereum', tron: 'Tron', near: 'NEAR', zec: 'Zcash', sol: 'Solana', arb: 'Arbitrum', base: 'Base', bsc: 'BNB Chain', xrp: 'XRP', btc: 'Bitcoin', ethereum: 'Ethereum', solana: 'Solana', avalanche: 'Avalanche', sui: 'Sui', aptos: 'Aptos', ton: 'TON', doge: 'Dogecoin', pol: 'Polygon', op: 'Optimism', avax: 'Avalanche' };
  const nameOf = (k) => NAME[k] || k.toUpperCase();
  const hueOf = (k) => HUE[k] || HUE.other;
  const wash = (hue, pct) => `color-mix(in srgb, ${hue} ${pct}%, var(--surface))`;

  /* One floating tooltip for the HTML forms */
  const tipEl = document.createElement('div');
  tipEl.className = 'vz-tip'; tipEl.hidden = true;
  const showTip = (ev, html) => {
    if (!tipEl.isConnected) document.body.append(tipEl);
    tipEl.innerHTML = html; tipEl.hidden = false;
    const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    tipEl.style.left = Math.min(innerWidth - w - 8, Math.max(8, ev.clientX + 14)) + 'px';
    tipEl.style.top = Math.min(innerHeight - h - 8, Math.max(8, ev.clientY + 14)) + 'px';
  };
  const hideTip = () => { tipEl.hidden = true; };

  const responsive = (el, draw) => {
    let last = 0;
    const run = () => { const w = el.clientWidth; if (w && Math.abs(w - last) > 2) { last = w; draw(w); } };
    run();
    const ro = new ResizeObserver(run); ro.observe(el);
    return () => ro.disconnect();
  };

  /* Mount any ECharts option lazily and keep it sized */
  /* `after`, when given, runs once the chart is drawn and again after every resize and update, with the chart in hand:
     a form uses it to place labels from where its marks really landed. */
  function echart(el, height, build, after) {
    const box = document.createElement('div');
    box.style.cssText = `width:100%;height:${typeof height === 'function' ? height() : height}px`;
    el.append(box);
    let ec = null;
    const then = () => { if (ec && after) after(ec, theme(el)); };
    const cancel = whenDrawable(el, () => { ec = echarts.init(box, null, { renderer: 'canvas' }); ec.setOption(build(theme(el))); then(); });
    const ro = new ResizeObserver(() => { if (ec) { ec.resize(); then(); } });
    ro.observe(box);
    return { update() { if (ec) { ec.setOption(build(theme(el)), true); then(); } }, destroy() { cancel(); ro.disconnect(); if (ec) ec.dispose(); el.innerHTML = ''; } };
  }

  /* Anything too small to draw well moves to one quiet box, so a treemap never has slivers.
     A group's label totals the boxes drawn in it, so the labels add up to the whole; a group that sets labelTotal
     keeps that figure as its label instead. */
  function foldTree(tree, { minLeaf = 0.012, minGroup = 0.02 } = {}) {
    const leafSum = (g) => d3.sum(g.children, (c) => c.value || 0);
    const total = d3.sum(tree.children, leafSum);
    let rest = 0, restCount = 0;
    const groups = [];
    tree.children.forEach((g) => {
      const gTotal = leafSum(g);
      if (gTotal / total < minGroup && !g.children.some((c) => c.dashed)) { rest += gTotal; restCount += g.children.length; return; }
      const keep = g.children.filter((c) => c.dashed || c.value / total >= minLeaf);
      const small = g.children.filter((c) => !keep.includes(c));
      const smallSum = d3.sum(small, (c) => c.value);
      const children = [...keep];
      if (smallSum / total >= minLeaf) children.push({ name: 'Other', value: smallSum, note: `${small.length} smaller items` });
      else if (small.length) { rest += smallSum; restCount += small.length; }
      if (children.length) groups.push({ ...g, children, shownTotal: g.labelTotal != null ? g.labelTotal : d3.sum(children, (c) => c.value || 0) });
      else { rest += gTotal; restCount += g.children.length; }
    });
    if (rest > 0) groups.push({ name: 'Others', hue: HUE.other, shownTotal: rest, children: [{ name: 'The rest', value: rest, note: `${restCount} smaller items` }] });
    return { name: tree.name, children: groups };
  }

  /* Treemap sized by money. Group labels sit on the top edge; a dashed box has no breakdown. */
  function treemap(host, tree, { height = 560, phoneHeight = 620, fmtV = fmt.usd, minLeaf, minGroup } = {}) {
    /* An inner box holds the height, because a flex parent can collapse the host itself */
    const el = document.createElement('div');
    el.className = 'vz-tree';
    host.append(el);
    const folded = foldTree(tree, { minLeaf, minGroup });
    return responsive(el, (w) => {
      const h = w < 640 ? phoneHeight : height;
      el.style.height = h + 'px';
      /* Named boxes come first, whatever their size, so a catch-all never reads as the leader */
      const isRest = (n) => /^(Other|Others|The rest)$/.test(n.data.name);
      const root = d3.hierarchy(folded).sum((d) => d.value || 0).sort((a, b) => isRest(a) - isRest(b) || b.value - a.value);
      d3.treemap().tile(d3.treemapSquarify.ratio(1.25)).size([w, h]).paddingOuter(2).paddingTop(25).paddingInner(4).round(true)(root);
      const total = root.value;
      el.innerHTML = '';
      root.children.forEach((g) => {
        const hue = g.data.hue;
        const gw = g.x1 - g.x0;
        const shown = g.data.shownTotal != null ? g.data.shownTotal : g.value;
        /* The value shows only when name and value both fit, so they can never collide */
        const fitsValue = gw > g.data.name.length * 7 + fmtV(shown).length * 7 + 34;
        if (gw > 54) {
          const lab = document.createElement('div');
          lab.className = 'vz-glabel';
          lab.style.cssText = `left:${g.x0 + 3}px;top:${g.y0 + 3}px;width:${gw - 6}px`;
          lab.innerHTML = `<span><i style="background:${hue}"></i><u>${g.data.name}</u></span>${fitsValue ? `<b>${fmtV(shown)}</b>` : ''}`;
          el.append(lab);
        }
        g.leaves().forEach((l) => {
          const bw = l.x1 - l.x0, bh = l.y1 - l.y0;
          if (bw < 3 || bh < 3) return;
          const box = document.createElement('div');
          box.className = 'vz-box' + (l.data.dashed ? ' dashed' : '');
          const roomy = bw >= 34 && bh >= 22;
          const geom = `left:${l.x0}px;top:${l.y0}px;width:${bw}px;height:${bh}px;padding:${roomy ? '7px 9px' : '0'};border-radius:${Math.min(7, Math.min(bw, bh) / 2)}px`;
          box.style.cssText = l.data.dashed
            ? `${geom};border-color:${wash(hue, 55)};background:repeating-linear-gradient(135deg,transparent 0 7px,${wash(hue, 8)} 7px 8px)`
            : `${geom};background:linear-gradient(155deg,${wash(hue, 38)},${wash(hue, 17)});border-color:${wash(hue, 42)}`;
          /* Shrink the label to fit on one line, or wrap it in a tall narrow box, so large boxes are never left blank */
          const inner = bw - 20;
          const base = Math.max(11, Math.min(34, Math.sqrt(bw * bh) / 8.8));
          const oneLine = Math.min(base, inner / Math.max(1, l.data.name.length * 0.56));
          const longest = Math.max(1, ...l.data.name.split(/[\s.\-_]+/).map((w) => w.length));
          const wraps = oneLine < 12 && bh > bw * 0.9;
          const size = wraps ? Math.min(base, 18, inner / (longest * 0.6)) : oneLine;
          const lines = wraps ? Math.ceil((l.data.name.length * 0.56 * size) / inner) + 1 : 1;
          if (roomy && size >= 10.5 && bh >= lines * size * 1.08 + 12) {
            const subSize = Math.max(10.5, size * 0.6);
            const sub = bh > lines * size * 1.08 + subSize * 1.3 + 14 ? `<em style="font-size:${subSize}px">${fmtV(l.value)}</em>` : '';
            const note = l.data.note && bh > size * 4.2 && bw > 150 ? `<small>${l.data.note}</small>` : '';
            box.innerHTML = `<strong style="font-size:${size}px${wraps ? ';white-space:normal;overflow-wrap:anywhere' : ''}">${l.data.name}</strong>${sub}${note}`;
          } else if (bw >= 46 && bh >= 30) {
            box.style.padding = '5px 7px';
            box.innerHTML = `<strong class="cut" style="font-size:11px">${l.data.name}</strong>`;
          } else if (bw >= 60 && bh >= 15) {
            box.style.padding = '0 8px';
            box.style.justifyContent = 'center';
            box.innerHTML = `<strong class="cut" style="font-size:11px">${l.data.name}</strong>`;
          } else if (bw >= 18 && bh >= 56) {
            box.style.padding = '7px 0';
            box.style.alignItems = 'center';
            box.innerHTML = `<strong class="cut up" style="font-size:11px">${l.data.name}</strong>`;
          }
          const tip = `<b>${l.data.name}</b><br>${g.data.name}: ${fmtV(l.value)}, ${fmt.pct(l.value / total, 1)} of the total${l.data.note ? `<br>${l.data.note}` : ''}`;
          box.addEventListener('pointermove', (ev) => showTip(ev, tip));
          box.addEventListener('pointerleave', hideTip);
          el.append(box);
        });
      });
    });
  }

  /* Flow diagram. iterations is how hard the layout reorders the nodes to untangle the bands; 0 keeps them in the
     order given, which suits a diagram with the same names on both sides. room is the space kept for the names on
     the right. */
  function sankey(el, { nodes, links, height = 380, fmtV = fmt.usd, iterations = 40, room = 190 }) {
    return echart(el, () => (el.clientWidth < 620 ? 460 : height), (t) => ({
      ...baseOption(t),
      tooltip: { ...tooltipBase(t), trigger: 'item', formatter: (p) => (p.dataType === 'edge' ? `${p.data.source} to ${p.data.target}<br><b>${fmtV(p.data.value)}</b>` : `${p.name}<br><b>${fmtV(p.value)}</b>`) },
      series: [{
        type: 'sankey', left: 4, right: el.clientWidth < 620 ? Math.min(96, room) : room, top: 8, bottom: 8, nodeWidth: 14, nodeGap: 18, nodeAlign: 'left', layoutIterations: iterations, draggable: false,
        emphasis: { focus: 'adjacency' },
        lineStyle: { color: 'gradient', curveness: 0.52, opacity: 0.34 },
        itemStyle: { borderWidth: 0, borderRadius: 3 },
        label: { color: t.strong, fontFamily: t.font, fontSize: 12.5, formatter: (p) => `{n|${p.name}}\n{v|${fmtV(p.value)}}`, rich: { n: { color: t.strong, fontSize: 12.5, fontWeight: 600, lineHeight: 17, fontFamily: t.font }, v: { color: t.ink, fontSize: 12, lineHeight: 15, fontFamily: t.font } } },
        data: nodes.map((n) => ({ name: n.name, itemStyle: { color: n.color } })),
        links,
      }],
    }));
  }

  /* Rank over time: each line is one entity, the highlighted one carries the story */
  function bump(el, { x, series, highlight = 'near', height = 360, fmtTip = (d) => d, count }) {
    return echart(el, height, (t) => ({
      ...baseOption(t),
      grid: { left: 4, right: 76, top: 12, bottom: 2, containLabel: true },
      tooltip: { ...tooltipBase(t), trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.mark, type: [3, 3] } },
        formatter: (ps) => `<div class="lcc-tip-head">${fmtTip(ps[0].axisValue)}</div>${[...ps].filter((p) => p.value != null).sort((a, b) => a.value - b.value).map((p) => `<div class="lcc-tip-row"><i style="background:${p.color}"></i><span>${p.seriesName}</span><b>#${p.value}</b></div>`).join('')}` },
      xAxis: { type: 'category', data: x, boundaryGap: false, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { ...axisText(t), formatter: (v) => fmtTip(v), hideOverlap: true, alignMinLabel: 'left', alignMaxLabel: 'right' } },
      yAxis: { type: 'value', inverse: true, min: 0.6, max: count + 0.4, interval: 1, splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { ...axisText(t), formatter: (v) => (Number.isInteger(v) ? '#' + v : '') } },
      series: series.map((s) => {
        const on = s.key === highlight;
        return {
          type: 'line', name: s.name, data: s.values, smooth: 0.35, symbol: 'circle', symbolSize: on ? 9 : 6, showSymbol: true, z: on ? 9 : 2, connectNulls: true,
          lineStyle: { width: on ? 4.5 : 2, color: s.color, opacity: on ? 1 : 0.42, shadowColor: on ? rgba(s.color, 0.5) : 'transparent', shadowBlur: on ? 12 : 0, cap: 'round' },
          itemStyle: { color: s.color, opacity: on ? 1 : 0.55, borderColor: t.surface, borderWidth: on ? 2 : 1 },
          emphasis: { focus: 'series', lineStyle: { width: on ? 4.5 : 3, opacity: 1 } },
          blur: { lineStyle: { opacity: 0.1 }, itemStyle: { opacity: 0.1 } },
          endLabel: { show: true, formatter: () => s.name, color: on ? t.strong : t.ink, fontWeight: on ? 700 : 500, fontSize: on ? 12.5 : 11.5, lineHeight: 16, fontFamily: t.font, distance: 8 },
          labelLayout: { moveOverlap: 'shiftY' },
        };
      }),
    }));
  }

  /* Rounds an axis bound to one significant figure, so log axes end on clean numbers */
  const nice1 = (v, up) => { const p = 10 ** Math.floor(Math.log10(v)); return (up ? Math.ceil(v / p) : Math.floor(v / p)) * p; };

  /* Log-log bubbles with diagonals of constant multiple. A bubble's name goes on the side it asks for, unless there it
     would sit on another name, on another bubble or off the plot; then it takes the next free side. The sides are
     chosen from where the bubbles were really drawn, so they are chosen again whenever the chart changes size. */
  function bubbles(el, { points, lines, xLabel, yLabel, height = 460, fmtX = fmt.usd, fmtY = fmt.usd, dropCrowded = false }) {
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
    const x0 = nice1(d3.min(xs) / 2.2), x1 = nice1(d3.max(xs) * 2.6, true), y0 = nice1(d3.min(ys) / 2.5), y1 = nice1(d3.max(ys) * 3, true);
    const SIDES = ['top', 'right', 'left', 'bottom'];
    let sides = points.map((p) => p.pos || 'top');
    /* With dropCrowded, a name that could only sit across another bubble is left off; the bubble's tooltip still names it */
    let dropped = points.map(() => false);
    const point = (p, i, t) => ({ value: [p.x, p.y], name: p.name, tip: p.tip, symbolSize: p.size, itemStyle: { color: new echarts.graphic.RadialGradient(0.38, 0.32, 0.9, [{ offset: 0, color: rgba(p.color, 0.9) }, { offset: 1, color: rgba(p.color, 0.45) }]), borderColor: p.color, borderWidth: p.on ? 2 : 1, shadowColor: p.on ? rgba(p.color, 0.6) : 'transparent', shadowBlur: p.on ? 18 : 0 }, label: { show: !dropped[i], position: sides[i], distance: 6, formatter: p.name, color: t.strong, fontWeight: p.on ? 700 : 500, fontSize: p.on ? 13 : 12, fontFamily: t.font } });
    const place = (ec, t) => {
      let plot = { x: 0, y: 0, width: ec.getWidth(), height: ec.getHeight() };
      try { plot = ec.getModel().getComponent('grid').coordinateSystem.getRect(); } catch (e) { /* the whole canvas will do */ }
      const at = (x, y) => ec.convertToPixel({ seriesId: 'pts' }, [x, y]);
      const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
      const discs = points.map((p) => { const c = at(p.x, p.y), r = p.size / 2; return { cx: c[0], cy: c[1], r, x: c[0] - r, y: c[1] - r, w: p.size, h: p.size }; });
      /* The diagonals' names are already on the chart, so the bubbles' names keep clear of them */
      const taken = lines.map((l) => { const ex = Math.min(x1, y1 / l.ratio), c = at(ex, ex * l.ratio), w = textWidth(l.label, `11px ${t.font}`); return { x: c[0] - w - 14, y: c[1] - 20, w: w + 14, h: 20 }; });
      const next = sides.slice(), drop = points.map(() => false);
      /* The highlighted bubble chooses first, then the larger ones, so the small ones fit around them */
      points.map((p, i) => i).sort((a, b) => (points[b].on ? 1 : 0) - (points[a].on ? 1 : 0) || points[b].size - points[a].size).forEach((i) => {
        const p = points[i], d = discs[i], size = p.on ? 13 : 12, w = textWidth(p.name, `${p.on ? 700 : 500} ${size}px ${t.font}`) + 2, h = size + 4;
        const rect = (side) => (side === 'top' ? { x: d.cx - w / 2, y: d.cy - d.r - 6 - h, w, h } : side === 'bottom' ? { x: d.cx - w / 2, y: d.cy + d.r + 6, w, h }
          : side === 'right' ? { x: d.cx + d.r + 6, y: d.cy - h / 2, w, h } : { x: d.cx - d.r - 6 - w, y: d.cy - h / 2, w, h });
        const inside = (r) => r.x >= plot.x && r.x + r.w <= plot.x + plot.width && r.y >= plot.y && r.y + r.h <= plot.y + plot.height;
        const free = (r, alsoBubbles) => inside(r) && !taken.some((k) => hit(r, k)) && (!alsoBubbles || !discs.some((k, j) => j !== i && hit(r, k)));
        const want = p.pos || 'top', tries = [want, ...SIDES.filter((side) => side !== want)];
        /* When no side is clear of every bubble, the name goes where it covers the least of them */
        const covered = (r) => discs.reduce((sum, k, j) => (j === i ? sum : sum + Math.max(0, Math.min(r.x + r.w, k.x + k.w) - Math.max(r.x, k.x)) * Math.max(0, Math.min(r.y + r.h, k.y + k.h) - Math.max(r.y, k.y))), 0);
        next[i] = tries.find((side) => free(rect(side), true)) || tries.filter((side) => free(rect(side), false)).sort((a, b) => covered(rect(a)) - covered(rect(b)))[0] || want;
        drop[i] = dropCrowded && !p.on && covered(rect(next[i])) > 0.25 * w * h;
        if (!drop[i]) taken.push(rect(next[i]));
      });
      if (next.join() !== sides.join() || drop.join() !== dropped.join()) { sides = next; dropped = drop; ec.setOption({ series: [{ id: 'pts', data: points.map((p, i) => point(p, i, t)) }] }); }
    };
    return echart(el, height, (t) => {
      const axis = (name, f, pos) => ({ type: 'log', logBase: 10, name, nameLocation: 'end', nameTextStyle: { ...axisText(t), align: pos === 'x' ? 'right' : 'left', padding: pos === 'x' ? [26, 0, 0, 0] : [0, 0, 6, 0] }, min: pos === 'x' ? x0 : y0, max: pos === 'x' ? x1 : y1, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.grid } }, axisLabel: { ...axisText(t), formatter: (v) => f(v, 0) } });
      return {
        ...baseOption(t),
        /* The top leaves room for the vertical axis's name, which sits above the plot */
        grid: { left: 6, right: 16, top: 40, bottom: 30, containLabel: true },
        tooltip: { ...tooltipBase(t), trigger: 'item', formatter: (p) => (p.data && p.data.tip) || '' },
        xAxis: axis(xLabel, fmtX, 'x'), yAxis: axis(yLabel, fmtY, 'y'),
        series: [
          ...lines.map((l) => ({ type: 'line', silent: true, symbol: 'none', z: 1, animation: false, data: [[x0, x0 * l.ratio], [Math.min(x1, y1 / l.ratio), Math.min(x1, y1 / l.ratio) * l.ratio]], lineStyle: { color: t.mark, width: 1, type: [2, 4] }, endLabel: { show: true, formatter: () => l.label, color: t.ink, fontSize: 11, fontFamily: t.font, offset: [-8, -10], align: 'right' } })),
          { type: 'scatter', id: 'pts', z: 3, animationDurationUpdate: 0, data: points.map((p, i) => point(p, i, t)) },
        ],
      };
    }, place);
  }

  /* Dots on one log plane, coloured from old to recent, with diagonals drawn at y = ratio x. With `reach`, the vertical
     axis runs far enough to show the diagonals even when every dot sits well under them. */
  function diagonalScatter(el, { points, lines, xLabel, yLabel, height = 470, hue = '#00b37a', fmtX = fmt.usd, fmtY = fmt.usd, reach = false }) {
    return echart(el, height, (t) => {
      const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
      const x0 = nice1(d3.min(xs) * 0.85), x1 = nice1(d3.max(xs) * 1.2, true), y0 = nice1(d3.min(ys) * 0.8), y1 = nice1(Math.max(d3.max(ys) * 1.25, reach && lines.length ? d3.max(lines, (l) => x1 * l.ratio) * 1.15 : 0), true);
      const sizes = d3.scaleSqrt().domain(d3.extent(points, (p) => p.size)).range([7, 28]);
      const axis = (name, f, pos, lo, hi) => ({ type: 'log', logBase: 10, name, nameLocation: 'end', nameTextStyle: { ...axisText(t), align: pos === 'x' ? 'right' : 'left', padding: pos === 'x' ? [26, 0, 0, 0] : [0, 0, 6, 0] }, min: lo, max: hi, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.grid } }, axisLabel: { ...axisText(t), formatter: (v) => f(v, 0) } });
      const n = points.length;
      return {
        ...baseOption(t),
        /* The top leaves room for the vertical axis's name, which sits above the plot */
        grid: { left: 6, right: 16, top: 40, bottom: 30, containLabel: true },
        tooltip: { ...tooltipBase(t), trigger: 'item', formatter: (p) => (p.data && p.data.tip) || '' },
        xAxis: axis(xLabel, fmtX, 'x', x0, x1), yAxis: axis(yLabel, fmtY, 'y', y0, y1),
        series: [
          ...lines.map((l) => ({ type: 'line', silent: true, symbol: 'none', z: 1, animation: false, data: [[x0, x0 * l.ratio], [x1, x1 * l.ratio]], lineStyle: { color: t.mark, width: 1, type: [2, 4] }, endLabel: { show: x1 * l.ratio < y1, formatter: () => l.label, color: t.ink, fontSize: 11, fontFamily: t.font, offset: [-6, -10], align: 'right' } })),
          { type: 'scatter', z: 3, data: points.map((p, i) => {
            const k = i / (n - 1), recent = p.kind === 2;
            return { value: [p.x, p.y], tip: p.tip, symbolSize: sizes(p.size), itemStyle: { color: rgba(d3.interpolateRgb(t.mark, hue)(Math.pow(k, 1.6)), recent ? 0.95 : 0.55), borderColor: recent ? hue : rgba(d3.interpolateRgb(t.mark, hue)(k), 0.9), borderWidth: 1, shadowColor: recent ? rgba(hue, 0.6) : 'transparent', shadowBlur: recent ? 14 : 0 } };
          }) },
        ],
      };
    });
  }

  /* Bars with dashed targets on the right. When the bars sit too close for their labels to fit side by side,
     the labels turn: slanted first, upright when it gets tighter still. The chart redraws when that changes,
     so turning a phone or narrowing a window is enough. */
  function targetBars(el, items, { height = 400, fmtV = fmt.usd, hue = '#00b37a', emphasis = items.length - 3 } = {}) {
    /* A label needs about 6.4px a letter at this size; two lines need the longer one */
    const longest = Math.max(...items.map((d) => Math.max(String(d.label).length, String(d.label2 || '').length)));
    const pitchOf = () => el.clientWidth / items.length;
    const turnAt = () => { const pitch = pitchOf(); return pitch >= Math.max(44, longest * 6.4 + 8) ? 0 : pitch >= 20 ? 60 : 90; };
    /* A value marked show: 'wide' is printed only where the bars leave room for it */
    const roomy = () => pitchOf() >= 34;
    let turn = turnAt(), wide = roomy();
    const handle = echart(el, height, (t) => {
      turn = turnAt(); wide = roomy();
      return {
        ...baseOption(t),
        grid: { left: 4, right: turn ? 22 : 8, top: 28, bottom: 2, containLabel: true },
        tooltip: { ...tooltipBase(t), trigger: 'item', formatter: (p) => `${p.data.tip || p.name}<br><b>${fmtV(p.value)}</b>` },
        xAxis: { type: 'category', data: items.map((d) => d.label + (d.label2 ? (turn ? ' ' : '\n') + d.label2 : '')), axisLine: { lineStyle: { color: t.grid } }, axisTick: { show: false }, axisLabel: { ...axisText(t), interval: 0, hideOverlap: false, lineHeight: 14, rotate: turn, ...(turn ? { fontSize: 11.5, margin: 10 } : {}) } },
        yAxis: { type: 'value', splitNumber: 4, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.grid } }, axisLabel: { ...axisText(t), formatter: (v) => fmtV(v, 0) } },
        series: [{
          type: 'bar', barCategoryGap: '26%', barMaxWidth: 54,
          data: items.map((d, i) => ({
            value: d.value, tip: d.tip,
            itemStyle: d.dashed
              ? { color: gradient(rgba(hue, 0.2), rgba(hue, 0.03)), borderColor: hue, borderWidth: 1.5, borderType: [4, 3], borderRadius: [6, 6, 0, 0] }
              : { color: gradient(hue, rgba(hue, 0.55)), borderRadius: [5, 5, 0, 0], opacity: i === emphasis ? 1 : 0.8 },
            label: { show: d.show === 'wide' ? wide : !!d.show, position: 'top', distance: 6, color: t.strong, fontSize: turn ? 11.5 : 13, fontWeight: 650, fontFamily: t.font, formatter: () => fmtV(d.value) },
          })),
        }],
      };
    });
    const ro = new ResizeObserver(() => { if (turnAt() !== turn || roomy() !== wide) handle.update(); });
    ro.observe(el);
    return { update: handle.update, destroy() { ro.disconnect(); handle.destroy(); } };
  }

  /* Side-by-side 100% columns with labels inside the segment when they fit */
  function stackColumns(el, columns, { height = 430 } = {}) {
    el.classList.add('vz-cols');
    el.innerHTML = columns.map((c) => {
      const sum = d3.sum(c.segments, (s) => s.value);
      return `<figure class="vz-col"><figcaption>${c.title}</figcaption><div class="vz-stack" style="height:${height}px">${c.segments.map((s) => {
        const px = (s.value / sum) * height;
        const pct = fmt.pct(s.value / sum, s.value / sum < 0.1 ? 1 : 0);
        const inside = px >= 19;
        return `<div class="vz-seg" style="flex:${s.value} 0 0;background:linear-gradient(160deg,${wash(s.color, 42)},${wash(s.color, 20)})" data-tip="${s.label}: ${pct}">${inside ? `<span>${s.label} <b>${pct}</b></span>` : ''}</div>`;
      }).join('')}</div></figure>`;
    }).join('');
    el.querySelectorAll('.vz-seg').forEach((s) => {
      s.addEventListener('pointermove', (ev) => showTip(ev, s.dataset.tip));
      s.addEventListener('pointerleave', hideTip);
    });
  }

  /* Rows are measures, columns are ranks, colour is the entity */
  function rankMatrix(el, rows, { columns = 7, highlight = 'near' } = {}) {
    el.classList.add('vz-matrix');
    const ord = ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th'];
    el.innerHTML = `<div class="vz-mgrid" style="grid-template-columns:minmax(104px,1.1fr) repeat(${columns},minmax(82px,1fr))">
      <div></div>${ord.slice(0, columns).map((o) => `<div class="vz-mhead">${o}</div>`).join('')}
      ${rows.map((r) => `<div class="vz-mrow"><b>${r.label}</b>${r.note ? `<small>${r.note}</small>` : ''}</div>` + d3.range(columns).map((i) => {
        const it = r.items[i];
        if (!it) return '<div class="vz-mcell empty"></div>';
        const hue = hueOf(it.key);
        const on = it.key === highlight;
        return `<div class="vz-mcell${on ? ' on' : ''}" style="background:${on ? `linear-gradient(150deg,${hue},${wash(hue, 72)})` : wash(hue, 11)}"><strong>${it.name}</strong><span>${it.value}</span></div>`;
      }).join('')).join('')}
    </div>`;
  }

  /* A strong bar inside a pale one on the same log scale */
  function nestedBars(el, rows, { domain = [1e6, 1e12], fmtV = fmt.usd, labelWidth = 150 } = {}) {
    el.classList.add('vz-nested');
    const x = d3.scaleLog().domain(domain).range([0, 100]).clamp(true);
    const ticks = d3.range(Math.round(Math.log10(domain[0])), Math.round(Math.log10(domain[1])) + 1).map((p) => 10 ** p);
    el.innerHTML = `<div class="vz-nrows" style="--lw:${labelWidth}px">
      <div class="vz-ngrid">${ticks.map((t) => `<i style="left:${x(t)}%"></i>`).join('')}</div>
      ${rows.map((r) => {
        const hue = hueOf(r.key);
        const outerPos = r.outer && x(r.outer) > 74 ? `right:calc(${100 - x(r.outer)}% + 8px)` : `left:calc(${x(r.outer || 1)}% + 8px)`;
        return `<div class="vz-nrow"><div class="vz-nlabel"><b>${r.name}</b>${r.sub ? `<small>${r.sub}</small>` : ''}</div><div class="vz-ntrack">
          ${r.outer ? `<div class="vz-nouter" style="width:${x(r.outer)}%;background:${wash(hue, 22)}"></div><span class="vz-nv out" style="${outerPos}">${fmtV(r.outer)}</span>` : ''}
          <div class="vz-ninner" style="width:${x(r.inner)}%;background:linear-gradient(90deg,${rgba(hue, 0.7)},${hue})"></div><span class="vz-nv in" style="left:calc(${x(r.inner)}% + 7px)">${fmtV(r.inner)}</span>
        </div></div>`;
      }).join('')}
      <div class="vz-naxis">${ticks.map((t) => `<span style="left:${x(t)}%">${fmtV(t, 0)}</span>`).join('')}</div>
    </div>`;
  }

  /* Low to high colour for stripes, read from the current theme */
  const stripeRamp = (el) => {
    const css = getComputedStyle(el);
    return d3.interpolateRgbBasis([css.getPropertyValue('--cal-low').trim() || '#10231c', css.getPropertyValue('--cal-mid').trim() || '#0a6b4c', css.getPropertyValue('--cal-high').trim() || '#00ec97']);
  };

  /* One stripe per day, one row per year. Colours come from the design's tokens, so it follows day and night. */
  function calendar(el, { d, v, marks = [], fmtV = fmt.int, rowH = 34, unit = '' }) {
    el.classList.add('vz-cal');
    const years = [...new Set(d.map((s) => +s.slice(0, 4)))];
    const doy = (s) => { const t = new Date(s + 'T00:00:00Z'); return Math.floor((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5); };
    const scale = d3.scaleLinear().domain([0, d3.quantile(v.filter((x) => x > 0).sort(d3.ascending), 0.99)]).range([0, 1]).clamp(true);
    return responsive(el, (w) => {
      const lab = w < 560 ? 34 : 46, top = 22, H = top + years.length * (rowH + 4) + 18;
      el.innerHTML = '';
      const cv = document.createElement('canvas');
      const dpr = Math.min(2, devicePixelRatio || 1);
      const inner = w - 32;
      cv.width = inner * dpr; cv.height = H * dpr; cv.style.cssText = `width:${inner}px;height:${H}px;display:block`;
      cv.setAttribute('role', 'img');
      cv.setAttribute('aria-label', 'Daily values by year. Stronger colour means higher. The query behind the chart is available below it.');
      el.append(cv);
      const c = cv.getContext('2d'); c.setTransform(dpr, 0, 0, dpr, 0, 0);
      const ramp = stripeRamp(el);
      const css = getComputedStyle(el);
      const low = css.getPropertyValue('--cal-low').trim() || '#10231c', ink = css.getPropertyValue('--cal-ink').trim() || 'rgba(255,255,255,.6)', markC = css.getPropertyValue('--cal-mark').trim() || '#ffffff';
      const font = css.getPropertyValue('--chart-font').trim() || 'sans-serif';
      const cw = (inner - lab) / 366;
      c.font = `11px ${font}`; c.fillStyle = ink;
      ['Jan', 'Apr', 'Jul', 'Oct'].forEach((mn, i) => { c.fillText(mn, lab + (i * 91.25) * cw, 12); });
      years.forEach((yr, i) => { c.fillStyle = ink; c.font = `11.5px ${font}`; c.fillText(String(yr), 0, top + i * (rowH + 4) + rowH / 2 + 4); });
      d.forEach((s, i) => {
        const row = years.indexOf(+s.slice(0, 4));
        c.fillStyle = v[i] > 0 ? ramp(scale(v[i])) : low;
        c.fillRect(lab + doy(s) * cw, top + row * (rowH + 4), Math.max(1, cw + 0.4), rowH);
      });
      marks.forEach((mk) => {
        const row = years.indexOf(+mk.d.slice(0, 4));
        const mx = lab + doy(mk.d) * cw, my = top + row * (rowH + 4);
        c.strokeStyle = markC; c.lineWidth = 1.5; c.beginPath(); c.moveTo(mx, my - 3); c.lineTo(mx, my + rowH + 3); c.stroke();
        const note = document.createElement('span');
        note.className = 'vz-calnote';
        const leftSide = mx > inner * 0.6;
        note.style.cssText = `top:${16 + my + rowH + 5}px;${leftSide ? `right:${w - 16 - mx - 2}px` : `left:${16 + mx - 2}px`}`;
        note.textContent = mk.label;
        el.append(note);
      });
      cv.addEventListener('pointermove', (ev) => {
        const b = cv.getBoundingClientRect();
        const px = ev.clientX - b.left - lab, py = ev.clientY - b.top - top;
        const row = Math.floor(py / (rowH + 4));
        if (row < 0 || row >= years.length || px < 0) return hideTip();
        const day = Math.floor(px / cw);
        const target = new Date(Date.UTC(years[row], 0, 1 + day)).toISOString().slice(0, 10);
        const i = d.indexOf(target);
        if (i < 0) return hideTip();
        showTip(ev, `<b>${fmt.date(target)}</b><br>${fmtV(v[i])}${unit}`);
      });
      cv.addEventListener('pointerleave', hideTip);
    });
  }

  /* Every check as a dot on one log axis of how far apart two sources are */
  function ledgerStrip(el, rows, { onPick, height = 360, hueOk = '#00b37a', hueBad = '#e5604f' } = {}) {
    return responsive(el, (w) => {
      const m = { t: 12, r: 12, b: 46, l: w < 560 ? 72 : 112 };
      el.innerHTML = '';
      const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${w} ${height}`).attr('width', '100%').attr('height', height).attr('role', 'img').attr('aria-label', 'Gap between sources for each check').style('display', 'block');
      const x = d3.scaleLog().domain([0.001, 120]).range([m.l + 18, w - m.r]).clamp(true);
      const bands = [['independent', 'Independent'], ['same_upstream', 'Same upstream']];
      const bandH = (height - m.t - m.b) / 2;
      [0.001, 0.01, 0.1, 1, 10, 100].forEach((t) => {
        svg.append('line').attr('x1', x(t)).attr('x2', x(t)).attr('y1', m.t).attr('y2', height - m.b).attr('stroke', 'var(--chart-grid)');
        svg.append('text').attr('x', x(t)).attr('y', height - m.b + 18).attr('text-anchor', 'middle').attr('font-size', 11).attr('fill', 'var(--chart-ink)').text(t < 0.01 ? 'Exact' : t + '%');
      });
      const rad = w < 560 ? 5 : 6.5;
      bands.forEach(([key, label], bi) => {
        const cy = m.t + bandH * (bi + 0.5);
        svg.append('text').attr('x', 0).attr('y', cy + 4).attr('font-size', 12.5).attr('font-weight', 600).attr('fill', 'var(--chart-strong)').text(label);
        svg.append('line').attr('x1', m.l).attr('x2', w - m.r).attr('y1', m.t + bandH * (bi + 1)).attr('y2', m.t + bandH * (bi + 1)).attr('stroke', 'var(--chart-grid)');
        const items = rows.map((r, i) => ({ r, i })).filter((o) => o.r.independence === key).sort((a, b) => (+a.r.diff_pct) - (+b.r.diff_pct));
        const placed = [];
        items.forEach((o) => {
          const px = x(Math.max(0.001, +o.r.diff_pct));
          let off = 0, step = 0, shift = 0;
          const clash = () => placed.some((p) => Math.hypot(p.x - (px + shift), p.y - (cy + off)) < rad * 2 + 1);
          while (clash() && step < 80) {
            step++;
            off = (step % 2 ? 1 : -1) * Math.ceil(step / 2) * (rad * 0.9);
            if (Math.abs(off) > bandH / 2 - rad - 2) { shift += rad * 1.1; off = 0; step = 0; }
          }
          placed.push({ x: px + shift, y: cy + off });
          const bad = o.r.status === 'differs';
          const hue = bad ? hueBad : hueOk;
          const c = svg.append('circle').attr('cx', px + shift).attr('cy', cy + off).attr('r', rad).attr('fill', hue).attr('fill-opacity', bad ? 0.95 : 0.55).attr('stroke', hue).attr('stroke-width', 1).attr('tabindex', 0).style('cursor', 'pointer');
          if (bad) c.style('filter', `drop-shadow(0 0 6px ${rgba(hue, 0.6)})`);
          const text = `<b>${o.r.metric}${o.r.subject ? ', ' + o.r.subject : ''}</b><br>Gap ${(+o.r.diff_pct).toFixed(2)}%, limit ${(+o.r.tolerance_pct).toFixed(2)}%`;
          c.on('pointermove', (ev) => showTip(ev, text)).on('pointerleave', hideTip).on('click', () => onPick && onPick(o.i)).on('keydown', (ev) => { if (ev.key === 'Enter') onPick && onPick(o.i); });
        });
      });
      svg.append('text').attr('x', w - m.r).attr('y', height - 4).attr('text-anchor', 'end').attr('font-size', 11).attr('fill', 'var(--chart-ink)').text('Gap between the two sources, log scale');
    });
  }

  /* Table twin behind a disclosure, so no value depends on hovering */
  const tableTwin = (headers, rows) => `<details class="vz-twin"><summary>Show the table</summary><div class="vz-twin-w"><table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;

  /* Data prepared the same way for every design */
  const LC = window.LC;
  /* All-route volume by blockchain over the 30 days the last Dune reading covers, as NEAR's dashboard splits it.
     NearBlocks sees public routes only, so its split would leave most of the volume as one unnamed box. */
  function chainTree() {
    return { name: 'Intents', children: (LC.duneChains30 || []).map((c) => ({ name: nameOf(c.blockchain), hue: hueOf(c.blockchain), children: [{ name: nameOf(c.blockchain), value: c.vol }] })) };
  }
  function peerRanks() {
    const P = LC.peers.map((p) => ({ ...p, feesY: p.fees_30d * 365 / 30, revY: p.revenue_30d * 365 / 30, dexY: p.dex_30d != null ? p.dex_30d * 365 / 30 : null }));
    const row = (label, key, f = fmt.usd, note) => ({ label, note, items: P.filter((p) => p[key] != null && p[key] > 0).sort((a, b) => b[key] - a[key]).map((p) => ({ key: p.chain_id, name: nameOf(p.chain_id), value: f(p[key]) })) });
    return [row('Market cap', 'mcap'), row('Fees', 'feesY', fmt.usd, 'a year'), row('Revenue', 'revY', fmt.usd, 'a year'), row('DEX volume', 'dexY', fmt.usd, 'a year'), row('Stablecoins', 'stablecoins'), row('TVL', 'tvl')];
  }
  /* Monthly rank of each chain by one measure, for the bump chart */
  function peerBump(metric = 'fees') {
    const chains = LC.peers.map((p) => p.chain_id);
    const monthly = Object.fromEntries(chains.map((c) => {
      const w = LC.peerWeekly[c];
      return [c, d3.rollup(w.d.map((d, i) => ({ d, v: w[metric][i] })), (g) => d3.sum(g, (r) => r.v || 0), (r) => r.d.slice(0, 7))];
    }));
    const months = [...new Set(LC.peerWeekly[chains[0]].d.map((d) => d.slice(0, 7)))].filter((m) => m < LC.windows.fees.slice(0, 7)).slice(-24);
    const ranks = Object.fromEntries(chains.map((c) => [c, []]));
    months.forEach((m) => {
      const order = chains.filter((c) => (monthly[c].get(m) || 0) > 0).sort((a, b) => monthly[b].get(m) - monthly[a].get(m));
      chains.forEach((c) => ranks[c].push(order.includes(c) ? order.indexOf(c) + 1 : null));
    });
    return { months, series: chains.map((c) => ({ key: c, name: nameOf(c), color: hueOf(c), values: ranks[c] })), count: chains.length };
  }

  /* The compare tool: any measure, any chains, actual or indexed */
  function compare(el, { height = 400, start = ['near', 'avalanche', 'sui', 'aptos'], metric = 'fees', indexed = false } = {}) {
    const METRICS = [['fees', 'Fees', true], ['revenue', 'Revenue', true], ['tvl', 'TVL', false], ['mcap', 'Market cap', false], ['stablecoins', 'Stablecoins', false], ['dex', 'DEX volume', true]];
    const chains = LC.peers.map((p) => p.chain_id);
    const st = { m: metric, on: new Set(start), idx: indexed };
    el.innerHTML = '<div class="cmp-bar"><div class="chips" data-r="m"></div><div class="chips" data-r="mode"></div></div><div class="chips" data-r="c"></div><div data-r="ch"></div>';
    const part = (k) => el.querySelector(`[data-r="${k}"]`);
    let c = null;
    const spec = () => {
      const [key, label] = METRICS.find((x) => x[0] === st.m);
      /* Every week the export holds is a whole week, so the first one is a fair base for the index and the last is drawn */
      const base = LC.peerWeekly.near.d;
      const series = chains.filter((k) => st.on.has(k)).map((k) => {
        const w = LC.peerWeekly[k];
        const map = new Map(w.d.map((d, i) => [d, w[key][i]]));
        let vals = base.map((d) => { const v = map.get(d); return v == null || v <= 0 ? null : v; });
        if (st.idx) { const first = vals.find((v) => v != null); vals = vals.map((v) => (v == null ? null : (v / first) * 100)); }
        return { name: nameOf(k), label: nameOf(k), values: vals, color: hueOf(k), width: k === 'near' ? 3.25 : 1.75 };
      }).filter((s) => s.values.some((v) => v != null));
      return { type: 'line', x: base, series, log: true, endLabels: true, noLegend: true, yFmt: st.idx ? (v) => fmt.compact(v, 0) : (v) => fmt.usd(v, 0), tipFmt: st.idx ? (v) => v.toFixed(0) : (v) => fmt.usd(v), tipDate: (d) => 'Week of ' + fmt.date(d), height, alt: `${label} by chain, weekly, log scale` };
    };
    const paint = () => {
      part('m').innerHTML = METRICS.map((m) => `<button class="chip" aria-pressed="${m[0] === st.m}" data-m="${m[0]}">${m[1]}</button>`).join('');
      part('mode').innerHTML = [['Actual', false], ['Indexed to 100', true]].map(([t, v]) => `<button class="chip" aria-pressed="${st.idx === v}" data-i="${v}">${t}</button>`).join('');
      part('c').innerHTML = chains.map((k) => `<button class="chip dot" aria-pressed="${st.on.has(k)}" data-c="${k}"><i style="background:${hueOf(k)}"></i>${nameOf(k)}</button>`).join('');
      if (c) c.update(spec()); else c = LCC.timeChart(part('ch'), spec());
    };
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.m) st.m = b.dataset.m;
      if (b.dataset.i !== undefined) st.idx = b.dataset.i === 'true';
      if (b.dataset.c) { if (st.on.has(b.dataset.c)) { if (st.on.size > 1) st.on.delete(b.dataset.c); } else st.on.add(b.dataset.c); }
      paint();
    });
    paint();
    return { destroy() { if (c) c.destroy(); } };
  }

  /* Source logos: one tidy row, with the name and what it provides on hover or focus */
  const SOURCES = {
    rpc: { name: 'NEAR RPC', group: 'chain', logo: 'near', url: 'https://near.org', what: 'Protocol config, validators, contract state, lockups and archival blocks, read from chain', how: 'Public RPC' },
    hos: { name: 'House of Stake', group: 'chain', url: 'https://houseofstake.org', what: 'Proposals and votes, read from the vote.dao contract', how: 'Contract views over RPC' },
    fastnear: { name: 'FastNear', group: 'chain', url: 'https://fastnear.com', what: 'Wallet transfers, holdings and the largest holders of each token', how: 'Public API' },
    neardata: { name: 'Neardata', group: 'chain', logo: 'neardata.svg', url: 'https://neardata.xyz', what: 'Sample blocks, kept only as aggregated counts', how: 'Public API' },
    bigquery: { name: "NEAR's public BigQuery dataset", group: 'chain', logo: 'near', url: 'https://docs.near.org/data-infrastructure/big-query', what: 'Transactions, signers and calls by contract for each day, and how many accounts came back, read from the dataset as counts', how: 'SQL on Google BigQuery' },
    nearblocks: { name: 'NearBlocks', group: 'data', url: 'https://nearblocks.io', what: 'Daily chain, Intents, per-contract and wallet statistics', how: 'Public API' },
    defillama: { name: 'DefiLlama', group: 'data', url: 'https://defillama.com', what: 'TVL, fees, revenue, DEX volume, stablecoins, yields and prices', how: 'Public API' },
    nansen: { name: 'Nansen', group: 'data', url: 'https://www.nansen.ai', what: 'Published signer counts, used as a cross-check', how: 'Published report, read by hand' },
    revenue: { name: 'revenue.near.org', group: 'near', logo: 'near', url: 'https://revenue.near.org', what: "NEAR's own revenue and fee series", how: 'Public page' },
    dune: { name: "NEAR's dashboard on Dune", group: 'near', url: 'https://dune.com/near/near-intents', what: "NEAR's public Intents dashboard, read on request", how: 'Public dashboard, read on request and not every night' },
    explorer: { name: 'NEAR Intents Explorer and 1Click', group: 'near', url: 'https://docs.near-intents.org', what: '1Click swaps counted per day, and the supported token list', how: 'Partner API, daily counts only' },
    gov: { name: 'NEAR governance forum', group: 'near', logo: 'near', url: 'https://gov.near.org', what: 'Governance threads', how: 'Public forum' },
    coinmetrics: { name: 'Coin Metrics', group: 'prices', url: 'https://coinmetrics.io', what: 'Reference price and market cap', how: 'Community API' },
    coinbase: { name: 'Coinbase', group: 'prices', url: 'https://www.coinbase.com', what: 'Daily NEAR-USD candles', how: 'Public API' },
    bitwise: { name: 'Bitwise', group: 'fund', url: 'https://nrretf.com', what: "The fund's share count, NEAR held, NAV, market price and wallet list", how: 'Public page' },
    sosovalue: { name: 'SoSoValue', group: 'fund', url: 'https://sosovalue.com', what: 'Daily ETF flows, read by hand from news reports, with a link on every row', how: 'News reports, read by hand' },
    github: { name: 'GitHub', group: 'code', url: 'https://github.com', what: 'Repository statistics', how: 'Public API' },
    registry: { name: 'Labels checked by hand', group: 'code', logo: 'registry.svg', url: 'https://github.com', what: 'Wallets, tokens, peers and events, each with an evidence level and a link', how: 'Lists kept by hand' },
    nearcatalog: { name: 'NEAR Catalog', group: 'code', url: 'https://nearcatalog.xyz', what: 'Project directory', how: 'Public API' },
    metapool: { name: 'Meta Pool', group: 'code', url: 'https://metapool.app', what: 'Meta Pool metrics', how: 'Public page' },
    rhea: { name: 'Rhea', group: 'code', url: 'https://rhea.finance', what: 'Pools and token prices', how: 'Public API' },
    warehouse: { name: 'This warehouse', logo: 'github', url: 'https://github.com', what: 'Rebuilt from committed raw data with make warehouse' },
  };
  const SOURCE_GROUPS = [['chain', 'Read from chain'], ['data', 'Data providers'], ['near', "NEAR's reports"], ['prices', 'Prices'], ['fund', 'The fund'], ['code', 'Code and labels']];
  const logoOf = (id) => { const f = SOURCES[id].logo || id; return `shared/logos/${f.includes('.') ? f : f + '.png'}`; };
  const sources = (ids = []) => `<span class="src-row" role="list" aria-label="Sources">${ids.map((id) => {
    const s = SOURCES[id]; if (!s) return '';
    return `<a class="src" role="listitem" href="${s.url}" target="_blank" rel="noopener" data-src="${id}" aria-label="${s.name.replace(/"/g, '&quot;')}: ${s.what.replace(/"/g, '&quot;')}"><img src="${logoOf(id)}" alt="" width="18" height="18" loading="lazy"></a>`;
  }).join('')}</span>`;
  const srcTip = document.createElement('div');
  srcTip.className = 'src-tip'; srcTip.hidden = true; srcTip.setAttribute('role', 'tooltip');
  const showSrc = (el) => {
    const s = SOURCES[el.dataset.src]; if (!s) return;
    if (!srcTip.isConnected) document.body.append(srcTip);
    srcTip.innerHTML = `<b>${s.name}</b><span>${s.what}</span>`; srcTip.hidden = false;
    const r = el.getBoundingClientRect(), w = srcTip.offsetWidth, h = srcTip.offsetHeight;
    srcTip.style.left = Math.min(innerWidth - w - 8, Math.max(8, r.left + r.width / 2 - w / 2)) + 'px';
    srcTip.style.top = (r.top - h - 8 > 8 ? r.top - h - 8 : r.bottom + 8) + 'px';
  };
  const srcOf = (t) => (t.closest ? t.closest('.src') : null);
  document.addEventListener('pointerover', (e) => { const el = srcOf(e.target); if (el) showSrc(el); });
  document.addEventListener('pointerout', (e) => { if (srcOf(e.target)) srcTip.hidden = true; });
  document.addEventListener('focusin', (e) => { const el = srcOf(e.target); if (el) showSrc(el); });
  document.addEventListener('focusout', (e) => { if (srcOf(e.target)) srcTip.hidden = true; });
  addEventListener('scroll', () => { srcTip.hidden = true; }, { passive: true });

  /* Display names for the fee channels */
  const channelName = (r) => ({ swapkit: 'SwapKit', zodl: 'Zodl', 'confidential intents': 'Confidential Intents', zashi: 'Zashi', 'near-intents.intents-referral.near': 'near-intents referral', rango: 'Rango', 'new.intents-referral.near': 'new referral', aurora: 'Aurora' }[r] || r);


  /* The Bitwise NEAR ETF: the facts its tile draws from, and its three own charts. The questions live in the page. */
  const ETF_HUE = '#1f9bcf', ETF_OUT = '#e5604f';
  const lastOf = (a) => a.filter((v) => v != null).slice(-1)[0];
  function etfFacts() {
    const D = LC.etf.daily, C = LC.etf.chain;
    const flows = D.d.map((d, i) => ({ d, flow: D.flow[i], cum: D.cum[i], basis: D.basis[i], rep: D.rep_cum[i] })).filter((r) => r.basis !== 'seed_capital' && r.flow != null);
    const cum = lastOf(D.cum), near = lastOf(C.near);
    return {
      flows, cum, near, assets: lastOf(D.assets), circ: lastOf(C.circ), shares: lastOf(D.shares), settled: lastOf(C.settled), nav: lastOf(D.nav),
      nav0: D.nav[D.d.indexOf(flows[0].d)], first3: d3.sum(flows.slice(0, 3), (r) => r.flow) / cum, poolShare: lastOf(C.pool_share),
      maxGap: d3.max(D.prem.filter((v) => v != null), Math.abs), estimated: flows.filter((r) => r.basis === 'chain_settlement').length,
    };
  }

  /* Every trading day's flow floats where the last one ended, so the bars themselves build the running total */
  function flowWaterfall(el, { height = 350, phoneHeight = 300 } = {}) {
    const { flows, cum } = etfFacts();
    const BASIS = { reported: 'Reported by SoSoValue', cumulative_difference: 'Gap between two reported totals', chain_settlement: 'Estimated from NEAR settling on chain', fund_page: "Change in Bitwise's share count" };
    const key = document.createElement('div'); key.className = 'lcc-legend';
    key.innerHTML = `<span class="lcc-key"><i style="background:${ETF_HUE}"></i>Inflow</span><span class="lcc-key"><i style="background:${rgba(ETF_HUE, 0.3)};box-shadow:inset 0 0 0 1px ${ETF_HUE}"></i>Inflow, estimated</span><span class="lcc-key"><i style="background:${ETF_OUT}"></i>Outflow</span><span class="lcc-key"><i style="background:transparent;border-radius:50%;box-shadow:inset 0 0 0 2px var(--chart-strong)"></i>SoSoValue's running total</span>`;
    el.append(key);
    const dayFmt = d3.utcFormat('%-d %b');
    const handle = echart(el, () => (el.clientWidth < 620 ? phoneHeight : height), (t) => {
      const tick = cum * 0.005;
      const pick = (test, v) => flows.map((r) => (test(r) ? v(r) : null));
      const est = (r) => r.basis === 'chain_settlement';
      let run = 0;
      const base = flows.map((r) => { const b = Math.min(run, r.cum); run = r.cum; return b; });
      const bar = (name, data, itemStyle) => ({ type: 'bar', name, stack: 'w', data, barCategoryGap: '20%', itemStyle: { borderRadius: 3, ...itemStyle }, emphasis: { disabled: true } });
      return {
        ...baseOption(t),
        grid: { left: 4, right: 16, top: 14, bottom: 2, containLabel: true },
        tooltip: {
          ...tooltipBase(t), trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: rgba(t.strong, 0.06) } },
          formatter: (ps) => {
            const r = flows.find((f) => f.d === ps[0].axisValue);
            const sign = r.flow > 0 ? '+' : r.flow < 0 ? '−' : '';
            return `<div class="lcc-tip-head">${fmt.date(r.d)}</div><div class="lcc-tip-row"><span>Net flow</span><b>${sign}${fmt.usd(Math.abs(r.flow))}</b></div><div class="lcc-tip-row"><span>Running total</span><b>${fmt.usd(r.cum)}</b></div>${r.rep != null ? `<div class="lcc-tip-row"><span>SoSoValue's total</span><b>${fmt.usd(r.rep)}</b></div>` : ''}<div class="lcc-tip-row"><span>${BASIS[r.basis] || r.basis}</span></div>`;
          },
        },
        xAxis: { type: 'category', data: flows.map((r) => r.d), axisLine: { lineStyle: { color: t.grid } }, axisTick: { show: false }, axisLabel: { ...axisText(t), interval: (i) => (flows.length - 1 - i) % 5 === 0, formatter: (v) => dayFmt(new Date(v + 'T00:00:00Z')) } },
        yAxis: { type: 'value', splitNumber: 4, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.grid } }, axisLabel: { ...axisText(t), formatter: (v) => fmt.usd(v, 0) } },
        series: [
          { type: 'bar', name: 'base', stack: 'w', silent: true, data: base, barCategoryGap: '20%', itemStyle: { color: 'transparent' }, emphasis: { disabled: true }, tooltip: { show: false } },
          bar('Inflow', pick((r) => r.flow > 0 && !est(r), (r) => r.flow), { color: gradient(ETF_HUE, rgba(ETF_HUE, 0.72)) }),
          bar('Inflow, estimated', pick((r) => r.flow > 0 && est(r), (r) => r.flow), { color: rgba(ETF_HUE, 0.3), borderColor: ETF_HUE, borderWidth: 1 }),
          bar('Outflow', pick((r) => r.flow < 0, (r) => -r.flow), { color: ETF_OUT }),
          bar('No flow', pick((r) => r.flow === 0, () => tick), { color: t.mark }),
          {
            type: 'scatter', name: "SoSoValue's running total", z: 5, symbolSize: 8, data: flows.map((r, i) => (r.rep != null ? [i, r.rep] : null)).filter(Boolean),
            itemStyle: { color: t.surface, borderColor: t.strong, borderWidth: 1.75 }, emphasis: { disabled: true },
            markLine: { silent: true, symbol: 'none', animation: false, lineStyle: { color: t.mark, type: [3, 3], width: 1 }, label: { position: 'insideStartTop', color: t.strong, fontSize: 11.5, fontWeight: 600, fontFamily: t.font, formatter: () => `${fmt.usd(cum)} so far` }, data: [{ yAxis: cum }] },
          },
        ],
      };
    });
    return handle;
  }

  /* Above or below a line: two hues around zero, and the bars point the way too */
  function divergingBars(el, { x, values, height = 270, pos = ETF_HUE, neg = ETF_OUT, posLabel, negLabel, tipLabel, fmtTip, fmtAxis, edge, interval }) {
    const rows = x.map((d, i) => ({ d, v: values[i] })).filter((r) => r.v != null);
    const key = document.createElement('div'); key.className = 'lcc-legend';
    key.innerHTML = `<span class="lcc-key"><i style="background:${pos}"></i>${posLabel}</span><span class="lcc-key"><i style="background:${neg}"></i>${negLabel}</span>`;
    el.append(key);
    const dayFmt = d3.utcFormat('%-d %b');
    return echart(el, height, (t) => ({
      ...baseOption(t),
      grid: { left: 4, right: 16, top: 8, bottom: 2, containLabel: true },
      tooltip: { ...tooltipBase(t), trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: rgba(t.strong, 0.06) } }, formatter: (ps) => `<div class="lcc-tip-head">${fmt.date(ps[0].axisValue)}</div><div class="lcc-tip-row"><span>${tipLabel}</span><b>${fmtTip(ps[0].value)}</b></div>` },
      xAxis: { type: 'category', position: 'bottom', data: rows.map((r) => r.d), axisLine: { onZero: false, lineStyle: { color: t.grid } }, axisTick: { show: false }, axisLabel: { ...axisText(t), interval: (i) => (rows.length - 1 - i) % Math.max(5, Math.ceil(rows.length / 6)) === 0, formatter: (v) => dayFmt(new Date(v + 'T00:00:00Z')) } },
      yAxis: { type: 'value', min: edge ? -edge : undefined, max: edge || undefined, interval, splitNumber: 4, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.grid } }, axisLabel: { ...axisText(t), formatter: fmtAxis } },
      series: [{
        type: 'bar', barCategoryGap: '26%', emphasis: { disabled: true },
        data: rows.map((r) => ({ value: r.v, itemStyle: { color: r.v >= 0 ? pos : neg, borderRadius: r.v >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3] } })),
        markLine: { silent: true, symbol: 'none', animation: false, label: { show: false }, lineStyle: { color: t.mark, type: 'solid', width: 1 }, data: [{ yAxis: 0 }] },
      }],
    }));
  }
  function premiumBars(el, { height = 270 } = {}) {
    const D = LC.etf.daily;
    const signed = (v, n) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(n)}%`;
    const known = D.prem.filter((v) => v != null);
    return divergingBars(el, { x: D.d, values: D.prem, height, posLabel: 'Above NAV', negLabel: 'Below NAV', tipLabel: 'Market price to NAV', fmtTip: (v) => signed(v, 2), fmtAxis: (v) => signed(v, 1), edge: Math.ceil(d3.max(known, Math.abs) * 2) / 2, interval: 0.5 });
  }

  /* A small waterfall for the subject tile */
  function miniWaterfall(el, { height = 116, hue = ETF_HUE, out = ETF_OUT } = {}) {
    const { flows, cum } = etfFacts();
    el.innerHTML = '<div></div>';
    const box = el.firstChild, w = box.clientWidth || el.clientWidth;
    const top = d3.max(flows, (r) => r.cum), y = (v) => height - (v / top) * (height - 3), bw = w / flows.length;
    let run = 0;
    const bars = flows.map((r, i) => {
      const a = run; run = r.cum;
      const hi = Math.max(a, r.cum), lo = Math.min(a, r.cum);
      const h = Math.max(2, y(lo) - y(hi));
      const fill = r.flow < 0 ? out : r.flow === 0 ? 'var(--chart-mark)' : hue;
      return `<rect x="${(i * bw + bw * 0.12).toFixed(1)}" y="${(y(hi)).toFixed(1)}" width="${(bw * 0.76).toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="${fill}" opacity="${r.basis === 'chain_settlement' ? 0.5 : 1}"/>`;
    }).join('');
    box.innerHTML = `<svg width="${w}" height="${height}" viewBox="0 0 ${w} ${height}" role="img" aria-label="Daily flows into the fund, building to ${fmt.usd(cum)}" style="display:block">${bars}</svg>`;
  }

  /* Where each section's numbers come from. A solid line is a source a chart plots; a dashed line is one that also
     feeds the tables behind it, walked from the warehouse's dependency graph at export. */
  const tablesIn = (...texts) => [...new Set(texts.join(' ').match(/\bgold\.\w+/g) || [])].map((t) => t.slice(5));
  const lineageOf = (tables) => [...new Set(tables.flatMap((t) => (LC.lineage.tables[t] || [])))];
  /* A table that compares or judges every subject reads almost every source, so it says nothing about one section's own inputs */
  const READS_ALL = (t) => /^dq_/.test(t) || t === 'fct_thesis_scorecard';
  function sectionSources(sec) {
    const plotted = new Map(), behind = new Map();
    const bump = (m, id) => { if (SOURCES[id] && id !== 'warehouse') m.set(id, (m.get(id) || 0) + 1); };
    sec.analyses.forEach((a) => {
      const shown = a.src || [];
      shown.forEach((id) => bump(plotted, id));
      lineageOf((a.tables || []).filter((t) => !READS_ALL(t))).forEach((id) => { if (!shown.includes(id)) bump(behind, id); });
    });
    const plottedIds = [...plotted.keys()], behindIds = [...behind.keys()].filter((id) => !plotted.has(id));
    return { plotted, behind, plottedIds, behindIds, count: plottedIds.length + behindIds.length };
  }
  const sourceList = (ids) => ids.map((id) => SOURCES[id].name);
  const words = (list) => (list.length < 2 ? list.join('') : `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`);
  const builtFrom = (sec, href) => {
    const { plottedIds, behindIds } = sectionSources(sec);
    if (!plottedIds.length && !behindIds.length) return '';
    return `<div class="built">${plottedIds.length ? `<span>Charts use</span>${sources(plottedIds)}` : ''}${behindIds.length ? `<span>Tables also read</span>${sources(behindIds)}` : ''}${href ? `<a href="${href}">See the full map</a>` : ''}</div>`;
  };

  let mapUid = 0, mapPlayed = false;
  function sourceMap(host, { sections, minWide = 720 } = {}) {
    const el = document.createElement('div'); el.className = 'sm'; host.append(el);
    const uid = ++mapUid;
    const secs = sections.map((s) => ({ ...s, ...sectionSources(s) })).filter((s) => s.count);
    const used = new Set(secs.flatMap((s) => [...s.plottedIds, ...s.behindIds]));
    const groups = SOURCE_GROUPS.map(([g, label]) => ({ g, label, ids: Object.keys(SOURCES).filter((id) => SOURCES[id].group === g && used.has(id)) })).filter((g) => g.ids.length);
    const order = groups.flatMap((g) => g.ids);
    const feedsOf = (id) => secs.filter((s) => s.plottedIds.includes(id) || s.behindIds.includes(id));
    const hint = `${order.length} sources reach the charts of ${secs.length} subjects. Select a logo or a subject to trace its lines.`;
    const key = `<div class="sm-foot"><div class="sm-key"><span><i class="solid"></i>A chart plots it</span><span><i class="dash"></i>It also feeds a table behind the chart, shown once you select</span></div></div>`;
    const twin = tableTwin(['Subject', 'Charts use', 'Tables also read', 'Questions'], secs.map((s) => [s.full || s.name, sourceList(s.plottedIds).join(', ') || 'None', sourceList(s.behindIds).join(', ') || 'None', s.analyses.length]));
    let pinned = null, stopPlay = null;

    function drawList() {
      el.innerHTML = `<div class="sm-rows">${secs.map((s) => `<div class="sm-row"><a href="${s.href}"><i style="background:${s.hue}"></i><b>${s.full || s.name}</b><small>${s.count} ${s.count === 1 ? 'source' : 'sources'}</small></a><div class="sm-row-src">${sources(s.plottedIds)}${s.behindIds.length ? `<span class="sm-behind">${sources(s.behindIds)}</span>` : ''}</div></div>`).join('')}</div><p class="sm-listkey">Paler logos feed a table behind the charts.</p>${twin}`;
    }

    function drawMap(w) {
      const pad = 4, gap = 15, H = w > 980 ? 450 : 420;
      const step = (w - pad * 2 - gap * (groups.length - 1)) / order.length;
      const size = Math.round(Math.max(24, Math.min(38, step - 7)));
      const col = (w - pad * 2) / secs.length;
      const pos = {};
      let x = pad;
      groups.forEach((g) => { g.x0 = x; g.ids.forEach((id) => { pos[id] = x + step / 2; x += step; }); g.x1 = x; x += gap; });
      secs.forEach((s, i) => { s.cx = pad + col * (i + 0.5); });
      const links = secs.flatMap((s) => [...s.plottedIds, ...s.behindIds].map((id) => ({ id, s, direct: s.plottedIds.includes(id), n: (s.plotted.get(id) || 0) + (s.behind.get(id) || 0) })));
      const sum = (list) => d3.sum(list, (l) => l.n);
      const u = Math.min(3, (step - 8) / d3.max(order, (id) => sum(links.filter((l) => l.id === id))), (col - 16) / d3.max(secs, (s) => sum(links.filter((l) => l.s === s))));
      links.forEach((l) => { l.w = Math.max(l.direct ? 1.5 : 1, l.n * u * (l.direct ? 1 : 0.6)); });
      const barOf = {};
      order.forEach((id) => {
        const list = links.filter((l) => l.id === id).sort((a, b) => a.s.cx - b.s.cx);
        const total = d3.sum(list, (l) => l.w); let a = pos[id] - total / 2;
        list.forEach((l) => { l.sx = a + l.w / 2; a += l.w; }); barOf[id] = total;
      });
      secs.forEach((s) => {
        const list = links.filter((l) => l.s === s).sort((a, b) => pos[a.id] - pos[b.id]);
        const total = d3.sum(list, (l) => l.w); let a = s.cx - total / 2;
        list.forEach((l) => { l.tx = a + l.w / 2; a += l.w; }); s.barW = total;
      });
      const chipTop = 26, y1 = chipTop + size + 11, y2 = H - 62, bend = (y2 - y1) * 0.56;
      const defs = secs.map((s, i) => `<linearGradient id="smg${uid}-${i}" gradientUnits="userSpaceOnUse" x1="0" y1="${y1}" x2="0" y2="${y2}"><stop offset="0" stop-color="${s.hue}" stop-opacity=".3"/><stop offset=".55" stop-color="${s.hue}" stop-opacity=".62"/><stop offset="1" stop-color="${s.hue}" stop-opacity="1"/></linearGradient>`).join('');
      const paths = links.map((l, i) => `<path class="sm-link${l.direct ? '' : ' behind'}"${l.direct ? ' pathLength="1"' : ` stroke-dasharray="${Math.max(2, l.w).toFixed(1)} 4"`} d="M${l.sx.toFixed(1)} ${y1}C${l.sx.toFixed(1)} ${(y1 + bend).toFixed(1)} ${l.tx.toFixed(1)} ${(y2 - bend).toFixed(1)} ${l.tx.toFixed(1)} ${y2}" stroke="url(#smg${uid}-${secs.indexOf(l.s)})" stroke-width="${l.w.toFixed(2)}" data-src="${l.id}" data-sec="${l.s.id}" style="--d:${order.indexOf(l.id) * 26}ms"/>`).join('');
      const srcBars = order.map((id) => `<rect class="sm-sbar" data-src="${id}" x="${(pos[id] - barOf[id] / 2).toFixed(1)}" y="${y1 - 3}" width="${barOf[id].toFixed(1)}" height="3" rx="1.5"/>`).join('');
      const secBars = secs.map((s) => `<rect class="sm-tbar" data-sec="${s.id}" x="${(s.cx - s.barW / 2).toFixed(1)}" y="${y2}" width="${s.barW.toFixed(1)}" height="5" rx="2.5" fill="${s.hue}"/>`).join('');
      const chips = order.map((id) => `<button type="button" class="src sm-chip" data-src="${id}" style="--s:${size}px;left:${(pos[id] - size / 2).toFixed(1)}px;top:${chipTop}px" aria-label="${SOURCES[id].name.replace(/"/g, '&quot;')}, feeds ${feedsOf(id).length} ${feedsOf(id).length === 1 ? 'subject' : 'subjects'}" aria-pressed="false"><img src="${logoOf(id)}" alt="" loading="lazy"></button>`).join('');
      const heads = groups.map((g) => `<div class="sm-group" style="left:${(g.x0 + 2).toFixed(1)}px;width:${(g.x1 - g.x0 - 4).toFixed(1)}px">${g.label}</div>`).join('');
      const labels = secs.map((s) => `<a class="sm-sec" data-sec="${s.id}" href="${s.href}" style="left:${(s.cx - col / 2).toFixed(1)}px;width:${col.toFixed(1)}px;top:${y2 + 10}px"><b>${s.name}</b><small>${s.count} ${s.count === 1 ? 'source' : 'sources'}</small></a>`).join('');
      el.innerHTML = `<div class="sm-plot" style="height:${H}px"><svg class="sm-svg" width="${w}" height="${H}" viewBox="0 0 ${w} ${H}" aria-hidden="true"><defs>${defs}</defs><g>${paths}</g>${srcBars}${secBars}</svg>${heads}${chips}${labels}</div><div class="sm-note" aria-live="polite"><div>${hint}</div></div>${key}${twin}`;

      const note = el.querySelector('.sm-note');
      const paint = (kind, id) => {
        const hot = kind ? (kind === 'src' ? (l) => l.id === id : (l) => l.s.id === id) : null;
        el.classList.toggle('sel', !!kind);
        const on = new Set(), onSec = new Set();
        if (hot) links.filter(hot).forEach((l) => { on.add(l.id); onSec.add(l.s.id); });
        el.querySelectorAll('.sm-link').forEach((p) => p.classList.toggle('on', !!hot && (kind === 'src' ? p.dataset.src === id : p.dataset.sec === id)));
        el.querySelectorAll('.sm-chip').forEach((c) => { c.classList.toggle('on', on.has(c.dataset.src)); });
        el.querySelectorAll('.sm-sec').forEach((c) => { c.classList.toggle('on', onSec.has(c.dataset.sec)); });
        if (!kind) { note.firstChild.textContent = hint; return; }
        if (kind === 'src') {
          const s = SOURCES[id], f = feedsOf(id);
          note.firstChild.innerHTML = `<b>${s.name}</b> ${s.what}. Feeds ${words(f.map((x) => x.name))}.${id === 'registry' ? '' : ` <a href="${s.url}" target="_blank" rel="noopener">Open its site</a>`}`;
        } else {
          const s = secs.find((x) => x.id === id);
          note.firstChild.innerHTML = `<b>${s.full || s.name}</b> ${s.analyses.length} ${s.analyses.length === 1 ? 'question' : 'questions'}. ${s.plottedIds.length ? `Charts use ${words(sourceList(s.plottedIds))}.` : ''}${s.behindIds.length ? ` Its tables also read ${words(sourceList(s.behindIds))}.` : ''}`;
        }
      };
      const pick = (t) => { const c = t.closest && t.closest('.sm-chip,.sm-sec'); return c ? (c.classList.contains('sm-chip') ? ['src', c.dataset.src] : ['sec', c.dataset.sec]) : null; };
      const plot = el.querySelector('.sm-plot');
      plot.addEventListener('pointerover', (e) => { const p = pick(e.target); if (p) paint(...p); });
      plot.addEventListener('pointerleave', () => { pinned ? paint(...pinned) : paint(); });
      plot.addEventListener('focusin', (e) => { const p = pick(e.target); if (p) paint(...p); });
      plot.addEventListener('focusout', () => { pinned ? paint(...pinned) : paint(); });
      plot.addEventListener('click', (e) => {
        const chip = e.target.closest && e.target.closest('.sm-chip');
        if (!chip) { if (pinned && !e.target.closest('.sm-sec')) { pinned = null; paint(); el.querySelectorAll('.sm-chip[aria-pressed="true"]').forEach((c) => c.setAttribute('aria-pressed', 'false')); } return; }
        const same = pinned && pinned[1] === chip.dataset.src;
        el.querySelectorAll('.sm-chip').forEach((c) => c.setAttribute('aria-pressed', 'false'));
        pinned = same ? null : ['src', chip.dataset.src];
        if (pinned) chip.setAttribute('aria-pressed', 'true');
        pinned ? paint(...pinned) : paint();
      });
      /* The lines draw themselves once, the first time a map scrolls into view */
      if (!mapPlayed && !LCC.reduce()) {
        const svg = el.querySelector('.sm-svg');
        const io = new IntersectionObserver((es) => {
          if (!es.some((en) => en.isIntersecting)) return;
          io.disconnect(); mapPlayed = true; svg.classList.add('play');
          setTimeout(() => svg.classList.remove('play'), 2100);
        }, { threshold: 0.3 });
        io.observe(svg);
        stopPlay = () => io.disconnect();
      }
    }

    const stop = responsive(el, (w) => { if (stopPlay) { stopPlay(); stopPlay = null; } pinned = null; el.classList.remove('sel'); if (w < minWide) drawList(); else drawMap(w); });
    return { destroy() { stop(); if (stopPlay) stopPlay(); host.innerHTML = ''; } };
  }

  /* Every source, by kind, and what it reaches */
  function sourceDirectory(host, { sections }) {
    const secs = sections.map((s) => ({ ...s, ...sectionSources(s) }));
    const known = new Set([...Object.keys(LC.lineage.sources), ...secs.flatMap((s) => [...s.plottedIds, ...s.behindIds])]);
    host.innerHTML = SOURCE_GROUPS.map(([g, label]) => {
      const ids = Object.keys(SOURCES).filter((id) => SOURCES[id].group === g && known.has(id));
      if (!ids.length) return '';
      return `<section class="sd-group"><h3>${label}</h3><div class="sd-grid">${ids.map((id) => {
        const s = SOURCES[id], info = LC.lineage.sources[id] || {};
        const feeds = secs.filter((x) => x.plottedIds.includes(id) || x.behindIds.includes(id));
        return `<article class="sd-card"><div class="sd-top"><span class="src"><img src="${logoOf(id)}" alt="" loading="lazy"></span><div><b>${s.name}</b><small>${s.how}</small></div></div><p>${s.what}</p><div class="sd-feeds">${feeds.length ? feeds.map((x) => `<a href="${x.href}"><i style="background:${x.hue}"></i>${x.name}</a>`).join('') : '<em>In the warehouse, no chart yet</em>'}</div><div class="sd-links">${info.feeds ? `<span>${info.feeds} raw ${info.feeds === 1 ? 'feed' : 'feeds'}</span>` : ''}<a href="${s.url}" target="_blank" rel="noopener">Site</a>${info.terms ? `<a href="${info.terms}" target="_blank" rel="noopener">Terms</a>` : ''}</div></article>`;
      }).join('')}</div></section>`;
    }).join('');
  }
  const sourceCount = (sections) => new Set([...Object.keys(LC.lineage.sources), ...sections.flatMap((s) => { const x = sectionSources(s); return [...x.plottedIds, ...x.behindIds]; })]).size;

  /* The Studio lists sources by name and logo */
  const sourceInfo = (id) => (SOURCES[id] ? { ...SOURCES[id], logo: logoOf(id) } : null);
  /* A bridge between two totals: each step starts where the one before it ended */
  function waterfall(el, items, { height = 340, fmtV = fmt.usd, up = '#00a874', down = '#d9584a' } = {}) {
    let run = 0;
    const rows = items.map((d) => {
      if (d.total) { run = d.value; return { ...d, base: 0, size: d.value }; }
      const from = run; run += d.value;
      return { ...d, base: Math.min(from, run), size: Math.abs(d.value) };
    });
    const signed = (d) => (d.total ? fmtV(d.value) : (d.value >= 0 ? '+' : '−') + fmtV(Math.abs(d.value)));
    /* Where the labels have turned there is no room for a step's full figure, so dollars lose their last digit */
    const brief = (d) => { const a = Math.abs(d.value); return d.total || fmtV !== fmt.usd || a < 1e3 ? signed(d) : (d.value >= 0 ? '+' : '−') + '$' + (a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : Math.round(a / 1e3) + 'K'); };
    /* On a phone the steps sit close together, so the labels under them shorten and the figures above them shrink.
       When even the short labels would touch, they turn, as the bars with targets do: slanted, then upright. */
    const turnAt = () => {
      const narrow = el.clientWidth < 520, slot = (el.clientWidth - 52) / items.length, font = `${narrow ? 11 : 12}px ${getComputedStyle(el).fontFamily}`;
      const widest = Math.max(...items.map((d) => Math.max(...String((narrow && d.short) || d.label).split('\n').map((line) => textWidth(line, font)))));
      return widest + 3 <= slot ? 0 : slot >= 20 ? 60 : 90;
    };
    let turn = turnAt();
    const handle = echart(el, height, (t) => { const narrow = el.clientWidth < 520; turn = turnAt(); return {
      ...baseOption(t),
      grid: { left: 4, right: turn ? 22 : 8, top: 30, bottom: 2, containLabel: true },
      tooltip: { ...tooltipBase(t), trigger: 'item', formatter: (p) => `${rows[p.dataIndex].tip || rows[p.dataIndex].label}<br><b>${signed(rows[p.dataIndex])}</b>` },
      xAxis: { type: 'category', data: rows.map((d) => { const s = (narrow && d.short) || d.label; return turn ? s.replace(/\n/g, ' ') : s; }), axisLine: { lineStyle: { color: t.grid } }, axisTick: { show: false }, axisLabel: { ...axisText(t), interval: 0, hideOverlap: false, lineHeight: 14, rotate: turn, ...(narrow ? { fontSize: 11 } : {}), ...(turn ? { margin: 10 } : {}) } },
      yAxis: { type: 'value', splitNumber: 4, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.grid } }, axisLabel: { ...axisText(t), formatter: (v) => fmtV(v, 0) } },
      series: [
        { type: 'bar', stack: 'w', silent: true, data: rows.map((d) => d.base), barCategoryGap: narrow ? '18%' : '30%', barMaxWidth: 88, itemStyle: { color: 'transparent' }, emphasis: { disabled: true }, tooltip: { show: false } },
        {
          type: 'bar', stack: 'w', barMaxWidth: 88, emphasis: { disabled: true },
          /* A rising step that ends beside a total has its figure at the total's height. When the bars are close
             enough for the labels to turn, that figure goes under its floating bar, clear of the total's. */
          data: rows.map((d, i) => ({
            value: d.size,
            itemStyle: d.total ? { color: gradient(rgba(t.strong, 0.85), rgba(t.strong, 0.55)), borderRadius: [5, 5, 0, 0] } : { color: d.value >= 0 ? up : down, borderRadius: 4 },
            label: { show: true, position: turn && !d.total && d.value >= 0 && rows[i + 1] && rows[i + 1].total ? 'bottom' : 'top', distance: narrow ? 4 : 6, color: t.strong, fontSize: narrow ? 10.5 : 13, fontWeight: 650, fontFamily: t.font, formatter: () => (turn ? brief(d) : signed(d)) },
          })),
        },
      ],
    }; });
    let wasNarrow = el.clientWidth < 520;
    const ro = new ResizeObserver(() => { const now = el.clientWidth < 520; if (now !== wasNarrow || turnAt() !== turn) { wasNarrow = now; handle.update(); } });
    ro.observe(el);
    return { update: handle.update, destroy() { ro.disconnect(); handle.destroy(); } };
  }

  window.VZ = { waterfall, HUE, nameOf, sourceInfo, hueOf, wash, showTip, hideTip, responsive, echart, treemap, sankey, bump, bubbles, stackColumns, rankMatrix, nestedBars, diagonalScatter, targetBars, calendar, ledgerStrip, tableTwin, chainTree, peerRanks, peerBump, compare, channelName, sources, stripeRamp, ETF_HUE, etfFacts, flowWaterfall, divergingBars, premiumBars, miniWaterfall, tablesIn, lineageOf, sectionSources, builtFrom, sourceMap, sourceDirectory, sourceCount, sourceGroups: SOURCE_GROUPS };

  const style = document.createElement('style');
  style.textContent = `
  .src-row{display:inline-flex;align-items:center;gap:4px;vertical-align:middle}
  .src{display:grid;place-items:center;width:26px;height:26px;border-radius:8px;background:#fff;box-shadow:0 0 0 1px rgba(12,16,15,.1),0 1px 2px rgba(12,16,15,.06);transition:transform .15s,box-shadow .15s;flex:none}
  .src img{display:block;width:18px;height:18px;border-radius:4px;object-fit:contain}
  .src:hover,.src:focus-visible{transform:translateY(-2px);box-shadow:0 0 0 1px rgba(12,16,15,.16),0 6px 14px rgba(12,16,15,.16)}
  .src-tip{position:fixed;z-index:90;pointer-events:none;max-width:260px;padding:8px 11px;border-radius:10px;background:var(--tip-bg);color:var(--tip-ink);font-size:12.5px;line-height:1.35;box-shadow:0 12px 34px rgba(0,0,0,.28)}
  .src-tip b{display:block;font-weight:600}.src-tip span{opacity:.72}
  .vz-tip{position:fixed;z-index:80;pointer-events:none;max-width:280px;padding:8px 11px;border-radius:10px;background:var(--tip-bg);color:var(--tip-ink);font-size:12.5px;line-height:1.4;box-shadow:0 12px 34px rgba(0,0,0,.28)}
  .vz-tree{position:relative;width:100%}
  .vz-glabel{position:absolute;display:flex;justify-content:space-between;gap:8px;align-items:baseline;font-size:12.5px;color:var(--ink);white-space:nowrap;overflow:hidden}
  .vz-glabel span{display:inline-flex;align-items:center;gap:6px;font-weight:600;min-width:0}.vz-glabel u{text-decoration:none;overflow:hidden;text-overflow:ellipsis}.vz-glabel i{width:8px;height:8px;border-radius:50%;flex:none}.vz-glabel b{font-weight:500;color:var(--mute)}
  .vz-box{position:absolute;border:1px solid;border-radius:7px;padding:7px 9px;overflow:hidden;display:flex;flex-direction:column;gap:1px;color:var(--ink);box-sizing:border-box;transition:filter .15s,transform .15s}
  .vz-box:hover{filter:brightness(1.06) saturate(1.1);z-index:2;transform:translateY(-1px)}
  .vz-box.dashed{border-style:dashed}
  .vz-box strong{font-weight:600;letter-spacing:-.015em;line-height:1.05;white-space:nowrap}.vz-box strong.cut{overflow:hidden;text-overflow:ellipsis;min-height:1.2em;line-height:1.2}.vz-box strong.up{writing-mode:vertical-rl;transform:rotate(180deg);max-height:100%;min-height:0}.vz-box em{font-style:normal;font-weight:500;color:var(--mute);line-height:1.25}.vz-box small{font-size:11.5px;color:var(--mute);line-height:1.3;margin-top:3px}
  .vz-cols{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:clamp(8px,2vw,22px)}
  .vz-col{margin:0;min-width:0}.vz-col figcaption{font-size:13.5px;font-weight:600;margin-bottom:8px;min-height:2.6em;line-height:1.3}
  .vz-stack{display:flex;flex-direction:column;gap:3px}
  .vz-seg{border-radius:6px;display:flex;align-items:center;justify-content:center;text-align:center;min-height:2px;overflow:hidden;color:var(--ink);font-size:12.5px;line-height:1.15;padding-inline:3px}.vz-seg b{font-weight:700}
  .vz-matrix{overflow-x:auto}
  .vz-mgrid{display:grid;gap:5px;min-width:700px}
  .vz-mhead{font-size:12px;color:var(--mute);text-align:center}
  .vz-mrow{display:flex;flex-direction:column;justify-content:center;font-size:14px}.vz-mrow b{font-weight:600}.vz-mrow small{font-size:11.5px;color:var(--mute)}
  .vz-mcell{border-radius:8px;padding:8px 4px;text-align:center;display:flex;flex-direction:column;gap:1px;color:var(--ink);min-height:52px;justify-content:center}
  .vz-mcell strong{font-size:13.5px;font-weight:600}.vz-mcell span{font-size:12px;color:var(--mute)}.vz-mcell.on{color:#04261a;box-shadow:0 6px 18px rgba(0,179,122,.3)}.vz-mcell.on strong{font-weight:700}.vz-mcell.on span{color:#04261a}
  .vz-mcell.empty{border:1px dashed var(--line);background:none}
  .vz-nrows{position:relative;--lw:150px}
  .vz-ngrid{position:absolute;left:calc(var(--lw) + 12px);right:34px;top:0;bottom:24px}.vz-ngrid i{position:absolute;top:0;bottom:0;width:1px;background:var(--chart-grid)}
  .vz-nrow{position:relative;display:grid;grid-template-columns:var(--lw) minmax(0,1fr);gap:12px;align-items:center;padding-block:10px;padding-right:34px}
  .vz-nlabel b{display:block;font-size:15px;font-weight:600;line-height:1.2}.vz-nlabel small{font-size:12px;color:var(--mute);display:block;line-height:1.3}
  .vz-ntrack{position:relative;height:28px}
  .vz-nouter,.vz-ninner{position:absolute;left:0;top:0;height:100%;border-radius:6px}.vz-ninner{top:6px;height:16px;border-radius:4px}
  .vz-nv{position:absolute;top:50%;transform:translateY(-50%);font-size:12px;font-weight:600;white-space:nowrap;color:var(--ink)}.vz-nv.out{color:var(--mute);font-weight:500}
  .vz-naxis{position:relative;margin-left:calc(var(--lw) + 12px);margin-right:34px;height:24px}.vz-naxis span{position:absolute;top:6px;transform:translateX(-50%);font-size:11px;color:var(--chart-ink)}
  .vz-cal{position:relative;background:var(--cal-bg,#0b1211);border-radius:12px;padding:16px}
  .vz-calnote{position:absolute;font-size:12px;font-weight:600;color:var(--cal-mark,#fff);white-space:nowrap;line-height:1}
  .vz-twin{margin-top:10px;font-size:13.5px}.vz-twin summary{cursor:pointer;color:var(--mute);width:max-content}.vz-twin summary:hover{color:var(--ink)}
  .vz-twin-w{overflow-x:auto;margin-top:8px;max-height:320px;overflow-y:auto}.vz-twin table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}.vz-twin th{font-weight:500;color:var(--mute);text-align:left;padding:5px 12px 5px 0;border-bottom:1px solid var(--line);white-space:nowrap}.vz-twin td{padding:5px 12px 5px 0;border-bottom:1px solid var(--line);white-space:nowrap}
  @media (max-width:560px){.vz-nrows{--lw:84px!important}.vz-nlabel b{font-size:13px}.vz-nlabel small{display:none}.vz-nrow,.vz-ngrid,.vz-naxis{margin-right:0;padding-right:0}.vz-ngrid{right:0}}

  .built{display:flex;flex-wrap:wrap;align-items:center;gap:7px 9px;margin-top:14px;font-size:13px}
  .built>span:not(.src-row){opacity:.72}.built .src-row{margin-right:7px;flex-wrap:wrap}
  .built>a{color:inherit;opacity:.72;text-underline-offset:2px}.built>a:hover{opacity:1}
  .sm{position:relative}.sm-plot{position:relative}
  .sm-svg{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
  .sm-link{fill:none;opacity:.6;mix-blend-mode:multiply;transition:opacity .16s}.sm-link.behind{opacity:0}
  @media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .sm-link{mix-blend-mode:screen}}
  :root[data-theme="dark"] .sm-link{mix-blend-mode:screen}
  .sm.sel .sm-link{opacity:.05}.sm.sel .sm-link.on{opacity:1}.sm.sel .sm-link.behind.on{opacity:.9}
  @keyframes sm-draw{from{stroke-dasharray:1;stroke-dashoffset:1}to{stroke-dasharray:1;stroke-dashoffset:0}}
  @keyframes sm-fade{from{opacity:0}}
  .sm-svg.play .sm-link:not(.behind){animation:sm-draw 1200ms cubic-bezier(.3,.7,.2,1) var(--d) backwards}
  .sm-sbar{fill:var(--chart-mark);transition:opacity .16s}.sm-tbar{transition:opacity .16s}
  .sm.sel .sm-sbar,.sm.sel .sm-tbar{opacity:.3}
  .sm-group{position:absolute;top:0;box-sizing:border-box;padding-bottom:4px;border-bottom:1px solid var(--line);text-align:center;font-size:12px;line-height:1.15;color:var(--mute);white-space:nowrap}
  .sm-chip{position:absolute;width:var(--s);height:var(--s);padding:0;border:0;border-radius:calc(var(--s) * .29);cursor:pointer;font:inherit;transition:opacity .16s,transform .15s,box-shadow .15s}
  .sm-chip img{width:calc(var(--s) * .68);height:calc(var(--s) * .68);border-radius:calc(var(--s) * .14)}
  .sm.sel .sm-chip:not(.on){opacity:.22}
  .sm-chip[aria-pressed="true"]{box-shadow:0 0 0 2px var(--ink)}
  .sm-sec{position:absolute;display:flex;flex-direction:column;align-items:center;gap:0;padding-block:2px;color:var(--ink);text-decoration:none;text-align:center;border-radius:8px;transition:opacity .16s}
  .sm-sec b{font-size:13px;font-weight:500;letter-spacing:-.005em;white-space:nowrap}.sm-sec small{font-size:11.5px;color:var(--mute);white-space:nowrap}
  .sm-sec:hover b{text-decoration:underline;text-underline-offset:2px}
  .sm.sel .sm-sec:not(.on){opacity:.3}
  .sm-note{display:grid;align-items:center;min-height:62px;box-sizing:border-box;margin-top:6px;padding:9px 12px;border-radius:10px;background:color-mix(in srgb,var(--ink) 4%,transparent);font-size:13.5px;line-height:1.38;color:var(--mute)}
  .sm-note b{color:var(--ink);font-weight:600;margin-right:3px}.sm-note a{color:var(--ink);text-underline-offset:2px}
  .sm-foot{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 18px;margin-top:10px;font-size:12.5px;color:var(--mute)}
  .sm-key{display:flex;flex-wrap:wrap;gap:4px 14px}.sm-key span{display:inline-flex;align-items:center;gap:7px}
  .sm-key i{display:block;width:20px;height:0;border-top:2.5px solid var(--chart-strong)}.sm-key i.dash{border-top:2px dashed var(--chart-mark)}
  .sm-idle{display:flex;flex-wrap:wrap;align-items:center;gap:6px 9px}.sm-idle .src-row{opacity:.72}
  .sm-rows{display:grid;gap:0}
  .sm-row{display:grid;gap:7px;padding:10px 0;border-top:1px solid var(--line)}.sm-row:first-child{border-top:0;padding-top:0}
  .sm-row>a{display:flex;align-items:center;gap:8px;color:var(--ink);text-decoration:none}.sm-row>a i{flex:none;width:9px;height:9px;border-radius:3px}.sm-row>a b{font-size:14.5px;font-weight:500}.sm-row>a small{margin-left:auto;font-size:12.5px;color:var(--mute)}
  .sm-row-src{display:flex;flex-wrap:wrap;gap:4px}.sm-row-src .src-row{flex-wrap:wrap}.sm-behind{display:inline-flex;opacity:.62;margin-left:6px}
  .sm-listkey{margin:8px 0 0;font-size:12.5px;color:var(--mute)}
  .sd-group{margin-top:22px}.sd-group:first-child{margin-top:0}.sd-group>h3{font-size:14px;font-weight:600;margin:0 0 9px;color:var(--mute)}
  .sd-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(270px,100%),1fr));gap:10px}
  .sd-card{display:flex;flex-direction:column;gap:9px;padding:13px 14px;background:var(--surface);border:1px solid var(--line);border-radius:12px;min-width:0}
  .sd-top{display:flex;align-items:center;gap:10px}.sd-top>div{min-width:0}.sd-top b{display:block;font-size:14.5px;font-weight:600;line-height:1.2}.sd-top small{display:block;font-size:12.5px;color:var(--mute);line-height:1.25}
  .sd-card p{margin:0;font-size:13.5px;line-height:1.36;color:var(--mute)}
  .sd-feeds{display:flex;flex-wrap:wrap;gap:4px;margin-top:auto}.sd-feeds a{display:inline-flex;align-items:center;gap:5px;padding:2px 8px 2px 6px;border:1px solid var(--line);border-radius:99px;font-size:12.5px;color:var(--ink);text-decoration:none}.sd-feeds a:hover{border-color:var(--chart-mark)}.sd-feeds i{width:7px;height:7px;border-radius:50%}.sd-feeds em{font-style:normal;font-size:12.5px;color:var(--faint)}
  .sd-links{display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px;font-size:12.5px;color:var(--faint)}.sd-links span{margin-right:auto}.sd-links a{display:inline-flex;align-items:center;justify-content:center;min-height:24px;min-width:24px;color:var(--mute);text-underline-offset:2px}
  @media (prefers-reduced-motion:reduce){.sm-link,.sm-chip,.sm-sec{transition:none}}
  `;
  document.head.append(style);
})();
