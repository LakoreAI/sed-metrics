/* Interactive figures: draws the data in ../figures/*.json.
 *
 * No metric is computed here. Every number and every credited or penalised
 * state comes from tools/docs_figures.py, which calls the library.
 *
 *   <div class="pen" data-figure="event_f1"></div>
 *   <div class="pen" data-figure="event_f1" data-scenarios="onset,split"></div>
 *   <div class="pen" data-figure="matrix"></div>
 *   <div class="lab" data-figure="matrix" data-layout="lab" data-row="split">...</div>
 *   <div class="pen" data-figure="event_f1" data-layout="thumb" data-scenario="onset"
 *        data-frame="20" data-metric="f1"></div>
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var base = new URL("../figures/", script.src);
  var NS = "http://www.w3.org/2000/svg";
  var cache = {};
  var uid = 0;

  function load(name) {
    if (!cache[name]) {
      cache[name] = fetch(new URL(name + ".json", base)).then(function (response) {
        if (!response.ok) throw new Error(response.status + " " + response.url);
        return response.json();
      });
    }
    return cache[name];
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    for (var key in attrs || {}) {
      if (key === "text") node.textContent = attrs[key];
      else node.setAttribute(key, attrs[key]);
    }
    (children || []).forEach(function (child) { if (child) node.appendChild(child); });
    return node;
  }

  function svg(tag, attrs, parent) {
    var node = document.createElementNS(NS, tag);
    for (var key in attrs || {}) {
      if (key === "text") node.textContent = attrs[key];
      else node.setAttribute(key, attrs[key]);
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  var tip;
  function showTip(event, lines) {
    if (!tip) {
      tip = el("div", { class: "pen-tip", role: "status" });
      document.body.appendChild(tip);
    }
    tip.textContent = "";
    lines.forEach(function (line) { tip.appendChild(el("span", { text: line })); });
    tip.hidden = false;
    var box = tip.getBoundingClientRect();
    var x = Math.min(event.clientX + 14, window.innerWidth - box.width - 8);
    var y = event.clientY - box.height - 12;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = (y < 8 ? event.clientY + 16 : y) + "px";
  }
  function hideTip() { if (tip) tip.hidden = true; }
  function hoverable(node, lines) {
    node.addEventListener("pointermove", function (event) { showTip(event, lines); });
    node.addEventListener("pointerleave", hideTip);
  }

  var STATE_NAMES = {
    ref: "Reference", hit: "Credited", plain: "Prediction", "false": "False detection",
    missed: "Missed", censored: "Censored", tp: "Hit", fp: "False positive", fn: "Miss", tn: "Silent"
  };

  /* The key lists only the states a timeline shows, so it never explains an absent mark. */
  function stateLegend(data) {
    var seen = {};
    (data.rows || []).forEach(function (row) { row.items.forEach(function (i) { seen[i.s] = true; }); });
    if (data.points) data.points.items.forEach(function (i) { seen[i.s === "hit" ? "alert" : "falsealert"] = true; });
    (data.cells || []).forEach(function (row) {
      row.items.forEach(function (i) { if (i.s === "fp" || i.s === "fn") seen[i.s] = true; });
    });
    var names = Object.assign({ alert: "Matched alert", falsealert: "False alert" }, STATE_NAMES);
    var keys = ["ref", "hit", "plain", "false", "missed", "censored", "fp", "fn", "alert", "falsealert"]
      .filter(function (k) { return seen[k]; });
    var out = keys.map(function (k) { return el("span", { class: "pen-state pen-state--" + k, text: names[k] }); });
    if (data.bands && data.bands.length) {
      out.push(el("span", { class: "pen-state pen-state--band", text: data.points ? "Matching window" : "Collar" }));
    }
    return out;
  }

  function number(value, digits) {
    return value === null || value === undefined ? "None" : Number(value).toFixed(digits);
  }

  function trim(value) {
    return String(Math.round(value * 100) / 100);
  }

  function hatch(root) {
    var id = "pen-hatch-" + ++uid;
    var defs = svg("defs", {}, root);
    var pattern = svg("pattern", {
      id: id, width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)"
    }, defs);
    svg("rect", { width: 6, height: 6, class: "pen-hatch-bg" }, pattern);
    svg("line", { x1: 0, y1: 0, x2: 0, y2: 6, class: "pen-hatch-line" }, pattern);
    return "url(#" + id + ")";
  }

  /* ---- timeline ------------------------------------------------------- */

  /* compact drops the lane names and tightens the lanes, for a small card on a phone */
  function drawTimeline(host, data, width, compact) {
    host.textContent = "";
    var narrow = !compact && width < 520;
    var left = narrow || compact ? 0 : 116;
    var rowHeight = compact ? 22 : 30;
    var laneGap = compact ? 5 : 10;
    var right = 8;
    var span = data.domain[1] - data.domain[0];
    var x = function (t) { return left + (t - data.domain[0]) / span * (width - left - right); };

    var lanes = [];
    var y = 4;
    function lane(kind, label, height, payload) {
      if (narrow) y += 18;
      lanes.push({ kind: kind, label: label, y: y, h: height, data: payload });
      y += height + laneGap;
    }
    (data.rows || []).forEach(function (row) { lane("row", row.label, rowHeight, row.items); });
    if (data.points) lane("points", data.points.label, 26, data.points.items);
    if (data.series) lane("series", data.series.label, compact ? 52 : 86, data.series);
    (data.cells || []).forEach(function (row) { lane("cells", row.label, compact ? 16 : 22, row.items); });

    var height = y + (compact ? 18 : 22);
    var root = svg("svg", { viewBox: "0 0 " + width + " " + height, width: width, height: height }, host);
    var fill = hatch(root);
    var bottom = y - laneGap;

    (data.bands || []).forEach(function (band) {
      var a = x(Math.max(band.a, data.domain[0]));
      var b = x(Math.min(band.b, data.domain[1]));
      svg("rect", { x: a, y: 0, width: Math.max(b - a, 0), height: bottom + 4, class: "pen-band" }, root);
    });

    if (data.grid && span / data.grid <= 120) {
      for (var g = data.domain[0]; g <= data.domain[1] + 1e-9; g += data.grid) {
        svg("line", { x1: x(g), x2: x(g), y1: 0, y2: bottom + 4, class: "pen-grid" }, root);
      }
    }

    var classes = {};
    (data.rows || []).forEach(function (row) {
      row.items.forEach(function (item) { classes[item.t] = true; });
    });
    var named = Object.keys(classes).length > 1;

    lanes.forEach(function (l) {
      if (!compact) {
        svg("text", {
          x: 0, y: narrow ? l.y - 6 : l.y + Math.min(l.h, 30) / 2 + 4, class: "pen-lane", text: l.label
        }, root);
      }

      if (l.kind === "row") {
        l.data.forEach(function (item) {
          var a = x(item.a), b = x(item.b);
          var box = svg("rect", {
            x: a + 1, y: l.y + 1, width: Math.max(b - a - 2, 2), height: l.h - 2, rx: 3,
            class: "pen-ev pen-ev--" + item.s
          }, root);
          if (item.s === "false" || item.s === "missed") box.style.fill = fill;
          hoverable(box, [STATE_NAMES[item.s] + ": " + item.t, trim(item.a) + " to " + trim(item.b) + " s"]);
          if (named && b - a > 52) {
            svg("text", {
              x: (a + b) / 2, y: l.y + l.h / 2 + 4, class: "pen-evtext pen-evtext--" + item.s, text: item.t
            }, root);
          }
        });
      } else if (l.kind === "cells") {
        l.data.forEach(function (cell) {
          var a = x(cell.a), b = x(cell.b);
          var gap = b - a > 6 ? 1 : 0.25;
          var box = svg("rect", {
            x: a + gap, y: l.y, width: Math.max(b - a - 2 * gap, 0.5), height: l.h, rx: b - a > 10 ? 2 : 0,
            class: "pen-cell pen-cell--" + cell.s
          }, root);
          if (cell.s === "fp" || cell.s === "fn") box.style.fill = fill;
          hoverable(box, [STATE_NAMES[cell.s], trim(cell.a) + " to " + trim(cell.b) + " s"]);
        });
      } else if (l.kind === "series") {
        var sy = function (v) { return l.y + l.h - v * l.h; };
        svg("line", { x1: left, x2: width - right, y1: sy(0), y2: sy(0), class: "pen-axis" }, root);
        var path = "";
        l.data.steps.forEach(function (s, i) {
          path += (i ? "L" : "M") + x(s[0]) + " " + sy(s[2]) + "L" + x(s[1]) + " " + sy(s[2]);
        });
        svg("path", { d: path, class: "pen-score" }, root);
        var ty = sy(l.data.threshold);
        svg("line", { x1: left, x2: width - right, y1: ty, y2: ty, class: "pen-threshold" }, root);
        svg("text", {
          x: width - right, y: ty - 5, class: "pen-tick pen-tick--end", text: "threshold " + l.data.threshold.toFixed(2)
        }, root);
      } else {
        svg("line", { x1: left, x2: width - right, y1: l.y + l.h, y2: l.y + l.h, class: "pen-axis" }, root);
        l.data.forEach(function (point) {
          var px = x(point.t);
          var mark = svg("path", {
            d: "M" + px + " " + (l.y + l.h) + "l-7 -14h14z", class: "pen-alert pen-alert--" + point.s
          }, root);
          hoverable(mark, [point.s === "hit" ? "Matched alert" : "False alert", "at " + trim(point.t) + " s"]);
        });
      }
    });

    /* the closest round step that keeps the labels at least 34px apart */
    var every = [1, 2, 5, 10, 20].filter(function (s) { return s / span * (width - left - right) >= 44; })[0] || span;
    for (var t = data.domain[0]; t <= data.domain[1] + 1e-9; t += every) {
      if (t < data.domain[1] - 1e-9 && x(data.domain[1]) - x(t) < 44) continue;
      var anchor = t === data.domain[0] ? "start" : t + every > data.domain[1] ? "end" : "middle";
      svg("text", {
        x: x(t), y: height - 4, class: "pen-tick", "text-anchor": anchor,
        text: trim(t) + (anchor === "end" ? " s" : "")
      }, root);
    }
  }

  /* ---- x/y charts ----------------------------------------------------- */

  function drawChart(host, spec, width) {
    host.textContent = "";
    var limit = Number(getComputedStyle(host).getPropertyValue("--pen-chart-max")) || 250;
    var height = Math.round(Math.min(Math.max(width * 0.5, Math.min(180, limit)), limit));
    var m = { l: 34, r: 10, t: 10, b: 38 };
    var xMin = spec.xMin || 0;
    var x = function (v) { return m.l + (v - xMin) / (spec.xMax - xMin || 1) * (width - m.l - m.r); };
    var y = function (v) { return height - m.b - v / spec.yMax * (height - m.t - m.b); };
    var root = svg("svg", { viewBox: "0 0 " + width + " " + height, width: width, height: height }, host);
    var fill = hatch(root);

    var main = spec.lines.filter(function (line) { return line.style === "main"; })[0];

    function pathOf(line) {
      var d = "";
      line.points.forEach(function (p, i) {
        if (!i) d += "M" + x(p[0]) + " " + y(p[1]);
        else if (line.step) d += "H" + x(p[0]) + "V" + y(p[1]);
        else d += "L" + x(p[0]) + " " + y(p[1]);
      });
      if (line.step && line.points.length) d += "H" + x(spec.xMax);
      return d;
    }

    /* What the metric loses is the area above its curve. */
    if (spec.lostArea && main && main.points.length) {
      var first = main.points[0][0];
      var d = "M" + x(xMin) + " " + y(spec.yMax) + "H" + x(spec.xMax);
      var pts = main.points;
      d += "V" + y(pts[pts.length - 1][1]);
      for (var i = pts.length - 1; i > 0; i--) d += "H" + x(pts[i][0]) + "V" + y(pts[i - 1][1]);
      d += "H" + x(first) + "V" + y(0) + "H" + x(xMin) + "Z";
      svg("path", { d: d, class: "pen-lost" }, root).style.fill = fill;
    }

    [0, 0.5, 1].forEach(function (f) {
      var v = f * spec.yMax;
      svg("line", { x1: m.l, x2: width - m.r, y1: y(v), y2: y(v), class: f ? "pen-grid" : "pen-axis" }, root);
      svg("text", { x: m.l - 6, y: y(v) + 4, class: "pen-tick pen-tick--end", text: trim(v) }, root);
    });
    [0, 0.5, 1].forEach(function (f) {
      var v = xMin + f * (spec.xMax - xMin);
      svg("text", {
        x: x(v), y: height - m.b + 15, class: "pen-tick",
        "text-anchor": f === 0 ? "start" : f === 1 ? "end" : "middle", text: trim(v)
      }, root);
    });
    svg("text", { x: (m.l + width - m.r) / 2, y: height - 4, class: "pen-lane", "text-anchor": "middle", text: spec.xLabel }, root);

    spec.lines.slice().sort(function (a) { return a.style === "main" ? 1 : -1; }).forEach(function (line) {
      svg("path", { d: pathOf(line), class: "pen-line pen-line--" + line.style }, root);
    });

    var cross = svg("line", { y1: y(0), y2: y(spec.yMax), class: "pen-cross", visibility: "hidden" }, root);
    var hit = svg("rect", {
      x: m.l, y: m.t, width: Math.max(width - m.l - m.r, 0), height: Math.max(height - m.t - m.b, 0), class: "pen-hit"
    }, root);
    hit.addEventListener("pointermove", function (event) {
      var box = root.getBoundingClientRect();
      var px = (event.clientX - box.left) * width / box.width;
      var value = xMin + (px - m.l) / (width - m.l - m.r) * (spec.xMax - xMin);
      var read = [spec.xLabel + ": " + trim(value)];
      spec.lines.forEach(function (line) {
        var at = null;
        if (line.step) {
          line.points.forEach(function (p) { if (p[0] <= value) at = p[1]; });
          if (at === null) at = 0;
        } else {
          var best = Infinity;
          line.points.forEach(function (p) {
            if (Math.abs(p[0] - value) < best) { best = Math.abs(p[0] - value); at = p[1]; }
          });
        }
        if (at !== null) read.push(line.label + ": " + trim(at));
      });
      cross.setAttribute("x1", px);
      cross.setAttribute("x2", px);
      cross.setAttribute("visibility", "visible");
      showTip(event, read);
    });
    hit.addEventListener("pointerleave", function () { cross.setAttribute("visibility", "hidden"); hideTip(); });

    if (spec.marker) {
      var mx = x(spec.marker[0]), my = y(spec.marker[1]);
      svg("line", { x1: mx, x2: mx, y1: y(0), y2: my, class: "pen-drop" }, root);
      svg("circle", { cx: mx, cy: my, r: 5, class: "pen-dot" }, root);
    }
    if (spec.cursor !== undefined) {
      svg("line", { x1: x(spec.cursor), x2: x(spec.cursor), y1: y(0), y2: y(spec.yMax), class: "pen-cursor" }, root);
    }
  }

  function legend(lines) {
    return el("div", { class: "pen-legend" }, lines.map(function (line) {
      return el("span", { class: "pen-key pen-key--" + line.style, text: line.label });
    }));
  }

  /* ---- score tiles ---------------------------------------------------- */

  function scoreTile(m, value) {
    var bounded = m.key !== "fah";
    var lost = value === null || value === undefined ? 0
      : m.lowerIsBetter ? Math.min(value, 1) : 1 - value;
    var bar = null;
    if (bounded) {
      bar = el("span", { class: "pen-bar", "aria-hidden": "true" }, [el("i")]);
      bar.firstChild.style.width = Math.max(0, Math.min(lost, 1)) * 100 + "%";
    }
    var shown = lost.toFixed(m.digits);
    var delta = bounded && !m.lowerIsBetter && Number(shown) > 0
      ? el("span", { class: "pen-delta", text: "\u2212" + shown }) : null;
    return el("div", { class: "pen-score-tile" + (lost > 1e-9 ? " is-lost" : "") }, [
      el("dt", { text: m.label }),
      el("dd", {}, [el("span", { text: number(value, m.digits) }), delta]),
      bar
    ]);
  }

  /* ---- one figure ----------------------------------------------------- */

  var SWEEP_KEYS = ["f1", "error_rate", "psds1", "psds2", "audr", "average_precision"];

  function figure(host, data) {
    var wanted = host.getAttribute("data-scenarios");
    var scenarios = wanted
      ? wanted.split(",").map(function (id) { return data.scenarios.filter(function (s) { return s.id === id; })[0]; })
      : data.scenarios;
    var state = { scenario: scenarios[0], index: scenarios[0].control.default };
    var id = "pen-" + ++uid;

    var tabs = el("div", { class: "pen-tabs", role: "group", "aria-label": "Mistake to illustrate" });
    var intro = el("p", { class: "pen-intro" });
    var timeline = el("div", { class: "pen-timeline" });
    var key = el("div", { class: "pen-legend pen-legend--states" });
    var control = el("div", { class: "pen-control" });
    var scores = el("dl", { class: "pen-scores" });
    var note = el("p", { class: "pen-note", "aria-live": "polite" });
    var charts = el("div", { class: "pen-charts" });

    host.textContent = "";
    if (scenarios.length > 1) host.appendChild(tabs);
    [intro, timeline, key, control, scores, note, charts].forEach(function (n) { host.appendChild(n); });

    scenarios.forEach(function (s) {
      var button = el("button", { type: "button", class: "pen-tab", text: s.label });
      button.addEventListener("click", function () { pick(s); });
      tabs.appendChild(button);
    });

    function pick(s) {
      state.scenario = s;
      state.index = s.control.default;
      Array.prototype.forEach.call(tabs.children, function (b, i) {
        b.setAttribute("aria-pressed", String(scenarios[i] === s));
      });
      intro.textContent = s.intro;
      intro.hidden = !s.intro;
      buildControl(s);
      draw();
    }

    function valueText(s, i) {
      if (s.control.valueLabels) return s.control.valueLabels[i];
      return trim(s.control.values[i]) + (s.control.unit ? " " + s.control.unit : "");
    }

    function buildControl(s) {
      control.textContent = "";
      if (s.control.valueLabels) {
        var group = el("div", { class: "pen-choices", role: "group", "aria-label": s.control.label });
        s.control.valueLabels.forEach(function (label, i) {
          var b = el("button", { type: "button", class: "pen-choice", text: label, "aria-pressed": String(i === state.index) });
          b.addEventListener("click", function () {
            state.index = i;
            Array.prototype.forEach.call(group.children, function (c, j) { c.setAttribute("aria-pressed", String(i === j)); });
            draw();
          });
          group.appendChild(b);
        });
        control.appendChild(el("span", { class: "pen-control-label", text: s.control.label }));
        control.appendChild(group);
        return;
      }
      var input = el("input", {
        type: "range", id: id, min: 0, max: s.control.values.length - 1, step: 1, value: state.index
      });
      var output = el("output", { for: id, text: valueText(s, state.index) });
      input.setAttribute("aria-valuetext", valueText(s, state.index));
      input.addEventListener("input", function () {
        state.index = Number(input.value);
        output.textContent = valueText(s, state.index);
        input.setAttribute("aria-valuetext", output.textContent);
        draw();
      });
      control.appendChild(el("label", { for: id, class: "pen-control-label", text: s.control.label }));
      control.appendChild(input);
      control.appendChild(output);
    }

    function draw() {
      var s = state.scenario;
      var frame = s.frames[state.index];

      hideTip();
      timeline.hidden = key.hidden = !frame.timeline;
      key.textContent = "";
      if (frame.timeline) {
        stateLegend(frame.timeline).forEach(function (item) { key.appendChild(item); });
        drawTimeline(timeline, frame.timeline, Math.max(timeline.clientWidth, 260));
        timeline.setAttribute("role", "img");
        timeline.setAttribute("aria-label", frame.note || s.label);
      }

      scores.textContent = "";
      s.metrics.forEach(function (m) { scores.appendChild(scoreTile(m, frame.scores[m.key])); });
      note.textContent = frame.note || "";
      note.hidden = !frame.note;

      charts.textContent = "";
      var specs = [];
      if (frame.curve) {
        var curve = Object.assign({}, frame.curve);
        curve.lostArea = data.id !== "brier";
        var title = data.id === "streaming" ? "Deadline recall. AUDR is the area under it."
          : data.id === "brier" ? "Penalty for every possible prediction"
          : "Operating curve. The score is the area under it.";
        specs.push({ title: title, chart: curve });
      }
      if (s.sweep) {
        var metrics = s.metrics.filter(function (m) { return SWEEP_KEYS.indexOf(m.key) >= 0; }).slice(0, 2);
        var values = s.control.values;
        var top = 1;
        var lines = metrics.map(function (m, k) {
          var points = s.frames.map(function (f, i) { return [values[i], f.scores[m.key]]; })
            .filter(function (p) { return p[1] !== null; });
          points.forEach(function (p) { top = Math.max(top, p[1]); });
          /* stepped: a collar or a threshold jumps, and a sloped line would suggest partial credit */
          return { label: m.label, style: k ? "alt" : "main", points: points, step: true };
        });
        specs.push({
          title: "Score across the whole range",
          chart: {
            xLabel: s.control.label + (s.control.unit ? " (" + s.control.unit + ")" : ""),
            xMin: values[0], xMax: values[values.length - 1], yMax: Math.ceil(top * 2) / 2,
            lines: lines, cursor: values[state.index]
          }
        });
      }
      charts.hidden = !specs.length;
      specs.forEach(function (spec) {
        var plot = el("div", { class: "pen-plot" });
        var box = el("div", { class: "pen-chart" }, [
          el("p", { class: "pen-chart-title", text: spec.title }), plot, legend(spec.chart.lines)
        ]);
        charts.appendChild(box);
      });
      specs.forEach(function (spec, i) {
        var plot = charts.children[i].children[1];
        drawChart(plot, spec.chart, Math.max(plot.clientWidth, 240));
        plot.setAttribute("role", "img");
        plot.setAttribute("aria-label", spec.title);
      });
    }

    pick(state.scenario);
    return draw;
  }

  /* ---- cross-metric comparison ---------------------------------------- */

  function loss(column, value) {
    return Math.max(0, Math.min(column.lowerIsBetter ? value : 1 - value, 1));
  }

  function matrix(host, data) {
    var selected = 3;
    host.textContent = "";
    var head = el("tr", {}, [el("th", { scope: "col", text: "Mistake" })].concat(data.columns.map(function (c) {
      return el("th", { scope: "col", text: c.label });
    })));
    var body = el("tbody");
    var detail = el("p", { class: "pen-intro" });
    var timeline = el("div", { class: "pen-timeline" });

    data.rows.forEach(function (row, i) {
      var button = el("button", { type: "button", class: "pen-rowbtn", text: row.label });
      var cells = data.columns.map(function (c) {
        var value = row.scores[c.key];
        var td = el("td", { text: number(value, c.digits) });
        var amount = loss(c, value);
        td.style.setProperty("--loss", Math.round(amount * 100) + "%");
        if (amount > 0.55) td.className = "is-heavy";
        return td;
      });
      var tr = el("tr", {}, [el("th", { scope: "row" }, [button])].concat(cells));
      tr.addEventListener("click", function () { pick(i); });
      body.appendChild(tr);
    });

    var table = el("table", { class: "pen-matrix" }, [el("thead", {}, [head]), body]);
    host.appendChild(el("div", { class: "pen-scroll" }, [table]));
    host.appendChild(detail);
    host.appendChild(timeline);

    function draw() {
      var row = data.rows[selected];
      detail.textContent = row.label + ". " + row.detail;
      drawTimeline(timeline, row.timeline, Math.max(timeline.clientWidth, 260));
      timeline.setAttribute("role", "img");
      timeline.setAttribute("aria-label", row.detail);
    }

    function pick(i) {
      selected = i;
      Array.prototype.forEach.call(body.children, function (tr, j) {
        tr.classList.toggle("is-on", i === j);
        tr.querySelector("button").setAttribute("aria-pressed", String(i === j));
      });
      draw();
    }

    pick(selected);
    return draw;
  }

  /* The landing page's windows: one scored mistake, optionally with a list to pick from.
     data-row names the mistake shown first. */
  function lab(host, data) {
    var wanted = host.getAttribute("data-row");
    var selected = Math.max(0, data.rows.map(function (row) { return row.id; }).indexOf(wanted));
    var part = function (name) { return host.querySelector("[data-lab-" + name + "]"); };
    var list = part("list"), timeline = part("timeline"), detail = part("detail"), title = part("title"),
      scores = part("scores");

    if (list) {
      list.textContent = "";
      data.rows.forEach(function (row, i) {
        var button = el("button", { type: "button", class: "lab-item", text: row.label });
        button.addEventListener("click", function () { pick(i); });
        list.appendChild(button);
      });
    }

    function draw() {
      var row = data.rows[selected];
      if (title) title.textContent = row.label;
      if (detail) detail.textContent = row.detail;
      scores.textContent = "";
      data.columns.forEach(function (c) { scores.appendChild(scoreTile(c, row.scores[c.key])); });
      drawTimeline(timeline, row.timeline, Math.max(timeline.clientWidth, 260));
      timeline.setAttribute("role", "img");
      timeline.setAttribute("aria-label", row.label + ". " + row.detail);
    }

    function pick(i) {
      selected = i;
      Array.prototype.forEach.call(list ? list.children : [], function (b, j) {
        b.setAttribute("aria-pressed", String(i === j));
      });
      draw();
    }

    pick(selected);
    return draw;
  }

  /* The home page control: drag the delay and watch the metrics part company. It plays
     once on load, from no delay to the starting value, unless motion is reduced. */
  function scrub(host, data) {
    var part = function (name) { return host.querySelector("[data-lab-" + name + "]"); };
    var input = part("input"), output = part("output"), timeline = part("timeline"),
      scores = part("scores"), note = part("note");
    var index = data.start;
    input.max = data.frames.length - 1;

    function draw() {
      var frame = data.frames[index];
      var text = frame.value.toFixed(2) + " " + data.control.unit;
      input.value = index;
      input.setAttribute("aria-valuetext", text);
      input.style.setProperty("--at", index / (data.frames.length - 1) * 100 + "%");
      output.textContent = text;
      note.textContent = frame.note;
      scores.textContent = "";
      data.columns.forEach(function (c) { scores.appendChild(scoreTile(c, frame.scores[c.key])); });
      drawTimeline(timeline, frame.timeline, Math.max(timeline.clientWidth, 260),
        window.matchMedia("(max-width: 639px)").matches);
      timeline.setAttribute("role", "img");
      timeline.setAttribute("aria-label", "Reference events and detections " + text);
    }

    var playing = null;
    function stop() { if (playing) { cancelAnimationFrame(playing); playing = null; } }
    input.addEventListener("input", function () { stop(); index = Number(input.value); draw(); });
    host.addEventListener("pointerdown", stop);

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      draw();
    } else {
      var began = null;
      index = 0;
      draw();
      playing = requestAnimationFrame(function step(now) {
        began = began || now;
        var t = Math.max(0, Math.min((now - began - 300) / 900, 1));
        var next = Math.round(data.start * t);
        if (next !== index) { index = next; draw(); }
        playing = t < 1 ? requestAnimationFrame(step) : null;
      });
    }
    return draw;
  }

  /* A still frame of one scenario, for a card: its score and its timeline or curve. */
  function thumb(host, data) {
    var id = host.getAttribute("data-scenario");
    var s = data.scenarios.filter(function (item) { return item.id === id; })[0];
    var frame = s.frames[Number(host.getAttribute("data-frame"))];
    var key = host.getAttribute("data-metric");
    var m = s.metrics.filter(function (item) { return item.key === key; })[0];
    var named = Object.assign({}, m, { label: host.getAttribute("data-label") || m.label });
    var head = el("dl", { class: "pen-scores" }, [scoreTile(named, frame.scores[key])]);
    var plot = el("div", { class: host.getAttribute("data-view") === "curve" ? "pen-plot" : "pen-timeline" });
    host.textContent = "";
    host.appendChild(head);
    host.appendChild(plot);

    function draw() {
      var width = Math.max(plot.clientWidth, 240);
      if (host.getAttribute("data-view") === "curve") {
        var spec = Object.assign({ lostArea: data.id !== "brier" }, frame.curve);
        drawChart(plot, spec, width);
      } else {
        drawTimeline(plot, frame.timeline, width, true);
      }
    }

    draw();
    return draw;
  }

  function mount(host) {
    var name = host.getAttribute("data-figure");
    load(name).then(function (data) {
      var layout = host.getAttribute("data-layout");
      var draw = layout === "lab" ? lab(host, data) : layout === "thumb" ? thumb(host, data)
        : layout === "scrub" ? scrub(host, data)
        : name === "matrix" ? matrix(host, data) : figure(host, data);
      var width = host.clientWidth;
      if (window.ResizeObserver) {
        new ResizeObserver(function () {
          if (host.clientWidth !== width) { width = host.clientWidth; draw(); }
        }).observe(host);
      }
      host.setAttribute("data-ready", "");
    }).catch(function (error) {
      console.error("figure " + name + ":", error);
      if (!host.getAttribute("data-layout")) {
        host.textContent = "The interactive figure could not load.";
      }
    });
  }

  function start() { document.querySelectorAll("[data-figure]").forEach(mount); }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
