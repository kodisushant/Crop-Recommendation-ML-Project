/* Crop Advisor - front-end logic. Every call goes to the FastAPI backend with fetch(); same-origin, no keys. */
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const FIELDS = {
  N: { l: "Nitrogen (N)", u: "dataset units", min: 0, max: 300, d: 90, i: "fa-flask", t: "Soil nitrogen content", g: "Soil Nutrients" },
  P: { l: "Phosphorus (P)", u: "dataset units", min: 0, max: 300, d: 42, i: "fa-flask", t: "Soil phosphorus content", g: "Soil Nutrients" },
  K: { l: "Potassium (K)", u: "dataset units", min: 0, max: 400, d: 43, i: "fa-flask", t: "Soil potassium content", g: "Soil Nutrients" },
  ph: { l: "Soil pH", u: "0–14", min: 0, max: 14, d: 6.5, i: "fa-droplet", t: "Acidity (7 = neutral)", g: "Soil Properties", step: .1 },
  temperature: { l: "Temperature", u: "°C", min: -5, max: 55, d: 20.9, i: "fa-temperature-half", t: "Average temperature", g: "Weather Conditions", step: .1 },
  humidity: { l: "Humidity", u: "%", min: 0, max: 100, d: 82, i: "fa-cloud", t: "Relative humidity", g: "Weather Conditions", step: .1 },
  rainfall: { l: "Rainfall", u: "mm", min: 0, max: 1000, d: 203, i: "fa-cloud-rain", t: "Rainfall", g: "Weather Conditions", step: .1 }
};
const ICON = { "Soil Nutrients": "fa-seedling", "Soil Properties": "fa-vial", "Weather Conditions": "fa-cloud-sun", "Location Details": "fa-location-dot" };
const COL = ["#174D32", "#4C956C", "#9BC53D", "#DCECCB", "#B7791F", "#5B8E7D", "#8A9A5B", "#C9A227"];
const cap = s => s ? s[0].toUpperCase() + s.slice(1) : s, inr = n => "₹" + Math.round(n).toLocaleString("en-IN");
const charts = {};

function toast(msg, type = "ok") {
  const t = document.createElement("div"); t.className = "toast " + (type === "error" ? "error" : ""); t.setAttribute("role", "status"); t.textContent = msg;
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), 4200);
}
async function api(path, body) {
  let r;
  try { r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined); }
  catch (e) { throw new Error("Cannot reach the server. Check your connection."); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    let m = j.detail; if (Array.isArray(m)) m = m.map(x => `${(x.loc || []).slice(-1)[0]}: ${x.msg}`).join("; ");
    throw new Error(m || "Request failed (" + r.status + ")");
  }
  return j;
}
function chart(id, cfg) {
  const el = document.getElementById(id); if (!el) return; if (charts[id]) charts[id].destroy();
  cfg.options = Object.assign({ responsive: true, maintainAspectRatio: false }, cfg.options || {});
  charts[id] = new Chart(el, cfg);
}
async function submitWith(btn, fn) {
  btn.classList.add("loading"); btn.disabled = true;
  try { await fn(); } catch (e) { toast(e.message, "error"); const r = $("#result"); if (r) r.innerHTML = `<div class="alert bad"><b>Something went wrong.</b> ${e.message}</div>`; }
  finally { btn.classList.remove("loading"); btn.disabled = false; }
}
const btnHTML = (t, icon) => `<button class="btn" type="submit"><span class="spinner"></span><i class="fa-solid ${icon}"></i> ${t}</button>`;
const badge = (s, txt) => `<span class="badge b-${String(s).toLowerCase()}">${txt || s.replace("_", " ")}</span>`;
const last = () => { try { return JSON.parse(localStorage.getItem("ca_last")) || {}; } catch { return {}; } };

/* ---- shared form pieces ---- */
function fieldsHTML(keys, grouped = true, prefix = "f-") {
  const saved = last(), groups = {};
  keys.forEach(k => (groups[grouped ? FIELDS[k].g : "x"] ||= []).push(k));
  return Object.entries(groups).map(([g, ks]) => {
    const inner = ks.map(k => {
      const f = FIELDS[k];
      return `<div><label for="${prefix}${k}"><i class="fa-solid ${f.i}"></i> ${f.l} <small>(${f.u})</small></label>
      <input type="number" id="${prefix}${k}" name="${k}" min="${f.min}" max="${f.max}" step="${f.step || 1}" value="${saved[k] ?? f.d}" required>
      <div class="hint">${f.t} · ${f.min}–${f.max}</div><div class="err" id="e-${prefix}${k}"></div></div>`;
    }).join("");
    return grouped ? `<div class="panel"><h3><i class="fa-solid ${ICON[g]}"></i> ${g}</h3><div class="fg">${inner}</div></div>` : `<div class="fg">${inner}</div>`;
  }).join("");
}
function readFields(keys, prefix = "f-") {
  const out = {}; let ok = true;
  keys.forEach(k => {
    const el = $("#" + prefix + k), f = FIELDS[k], v = parseFloat(el.value), e = $("#e-" + prefix + k);
    const bad = isNaN(v) || v < f.min || v > f.max; el.classList.toggle("bad", bad); e.textContent = bad ? `Enter ${f.min}–${f.max}` : ""; if (bad) ok = false; out[k] = v;
  });
  if (!ok) throw new Error("Please correct the highlighted fields.");
  localStorage.setItem("ca_last", JSON.stringify({ ...last(), ...out }));
  return out;
}
let _crops = null;
async function cropList() { return _crops ||= await api("/crops"); }
async function fillCrops(sel, withBlank) {
  const c = await cropList(); sel.innerHTML = (withBlank ? `<option value="">Select crop…</option>` : "") + c.map(x => `<option value="${x.crop}">${cap(x.crop)}</option>`).join("");
}
async function fillStates(sel) {
  let s; try { s = (await api("/states")).states; } catch { s = []; toast("Could not load states list", "error"); }
  sel.innerHTML = `<option value="">All India</option>` + s.map(x => `<option>${x}</option>`).join("");
}
const stateField = id => `<div class="panel"><h3><i class="fa-solid fa-location-dot"></i> Location Details</h3><label for="${id}">State / UT</label><select id="${id}"></select><div class="hint">Used for market prices only. It is <b>not</b> an input to the ML model (the dataset has no location column).</div></div>`;
const empty = (icon, t) => `<div class="empty"><i class="fa-solid ${icon}"></i>${t}</div>`;

/* ---- pages ---- */
const pages = {};

pages.index = async () => {
  try { const m = await api("/meta"); $("#h-crops").textContent = m.n_crops; $("#h-acc").textContent = (m.test_accuracy * 100).toFixed(1) + "%"; $("#h-model").textContent = m.best_model; } catch { }
};

pages.recommendation = async () => {
  $("#fields").innerHTML = fieldsHTML(Object.keys(FIELDS)) + stateField("state");
  fillStates($("#state"));
  $("#fill-example").onclick = () => { Object.entries(FIELDS).forEach(([k, f]) => $("#f-" + k).value = f.d); toast("Example values loaded (typical rice conditions)"); };
  $("#predict-form").onsubmit = e => {
    e.preventDefault(); submitWith($("#go"), async () => {
      const v = readFields(Object.keys(FIELDS)); v.state = $("#state").value || null;
      const r = await api("/predict", v); renderPrediction(r);
      const h = JSON.parse(localStorage.getItem("ca_hist") || "[]"); h.unshift({ t: Date.now(), crop: r.crop, status: r.status, p: r.top_k[0]?.probability }); localStorage.setItem("ca_hist", JSON.stringify(h.slice(0, 6)));
      $("#result").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };
};
function renderPrediction(r) {
  const st = r.status, cls = { OK: "ok", LOW_CONFIDENCE: "low", OUT_OF_RANGE: "out" }[st];
  let h = "";
  if (st === "OUT_OF_RANGE") h += `<div class="alert bad"><b><i class="fa-solid fa-triangle-exclamation"></i> Out of range – no crop recommended.</b><p>These values are unlike anything the model was trained on, so any answer would be unreliable.</p><ul>${r.reasons.map(x => `<li>${x}</li>`).join("")}</ul></div>`;
  else {
    const t = r.top_k[0];
    h += `<div class="result-top"><span class="badge b-${cls === "ok" ? "ok" : "low"}">${st.replace("_", " ")}</span><div style="margin-top:8px;opacity:.85">Recommended crop</div><h2>${t.crop}</h2>
    <div class="meter"><i style="width:${t.probability * 100}%"></i></div><div>Model probability ${(t.probability * 100).toFixed(1)}% · Confidence <b>${r.confidence_label}</b></div></div>`;
    if (r.reasons.length) h += `<div class="alert"><b>Why the confidence is not high</b><ul>${r.reasons.map(x => `<li>${x}</li>`).join("")}</ul><div>Treat the top 3 below as a shortlist.</div></div>`;
    h += `<div class="panel"><h3><i class="fa-solid fa-ranking-star"></i> Top 3 crops</h3><div class="chart-box" style="height:200px"><canvas id="c-top"></canvas></div></div>
    <div class="panel"><h3><i class="fa-solid fa-magnifying-glass-chart"></i> What drove this prediction</h3><div class="chart-box" style="height:260px"><canvas id="c-exp"></canvas></div><div class="note">Positive = pushes towards ${t.crop}. Estimated by replacing each feature with random training values and measuring the drop in probability (model-agnostic).</div></div>`;
  }
  h += `<div class="kv"><div><b>${r.normalized_entropy}</b><span>Normalised entropy (0 sure – 1 unsure)</span></div><div><b>${(r.margin * 100).toFixed(1)}%</b><span>Margin top-2</span></div><div><b>${(r.stability_change_rate * 100).toFixed(0)}%</b><span>Changed in ${r.stability_runs} noisy re-runs</span></div><div><b>${r.out_of_range_check.distance}</b><span>Unusualness (limit ${r.out_of_range_check.threshold})</span></div></div>
  <div class="inl"><a class="btn ghost sm" href="/what-if"><i class="fa-solid fa-sliders"></i> Try what-if</a><a class="btn ghost sm" href="/land-check"><i class="fa-solid fa-map"></i> Check land suitability</a><a class="btn ghost sm" href="/fertilizer"><i class="fa-solid fa-flask"></i> Fertilizer plan</a></div>
  <p class="note">${r.note} Out-of-range detection is statistical and can miss combinations where every value looks normal.</p>`;
  $("#result").innerHTML = h;
  if (st !== "OUT_OF_RANGE") {
    chart("c-top", { type: "bar", data: { labels: r.top_k.map(x => cap(x.crop)), datasets: [{ data: r.top_k.map(x => x.probability * 100), backgroundColor: COL }] }, options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { max: 100, title: { display: true, text: "Probability %" } } } } });
    chart("c-exp", { type: "bar", data: { labels: r.explanation.map(x => `${x.feature} = ${x.value}`), datasets: [{ data: r.explanation.map(x => x.effect), backgroundColor: r.explanation.map(x => x.effect >= 0 ? "#4C956C" : "#B3392F") }] }, options: { indexAxis: "y", plugins: { legend: { display: false } } } });
  }
}

pages.dashboard = async () => {
  const [m, mt] = await Promise.all([api("/meta"), api("/metrics")]);
  $("#d-crops").textContent = m.n_crops; $("#d-model").textContent = m.best_model; $("#d-acc").textContent = (m.test_accuracy * 100).toFixed(1) + "%"; $("#d-rows").textContent = m.rows;
  chart("c-models", { type: "bar", data: { labels: mt.comparison.map(x => x.Model), datasets: [{ label: "CV accuracy", data: mt.comparison.map(x => x["CV Accuracy"] * 100), backgroundColor: "#174D32" }, { label: "Test accuracy", data: mt.comparison.map(x => x["Test Accuracy"] * 100), backgroundColor: "#4C956C" }] }, options: { scales: { y: { min: 90, max: 100, title: { display: true, text: "%" } } } } });
  const h = JSON.parse(localStorage.getItem("ca_hist") || "[]");
  $("#hist").innerHTML = h.length ? h.map(x => `<tr><td>${new Date(x.t).toLocaleString()}</td><td>${x.crop ? cap(x.crop) : "–"}</td><td>${badge(x.status === "OK" ? "ok" : x.status === "LOW_CONFIDENCE" ? "low" : "out", x.status.replace("_", " "))}</td></tr>`).join("") : `<tr><td colspan="3">${empty("fa-clock-rotate-left", "No predictions yet. Run one on the recommendation page.")}</td></tr>`;
  $("#clear-hist").onclick = () => { localStorage.removeItem("ca_hist"); toast("History cleared"); pages.dashboard(); };
};

pages.ideal_conditions = async () => {
  const list = await cropList(); const all = await Promise.all(list.map(c => api("/crops/" + c.crop)));
  const draw = () => {
    const q = $("#q").value.toLowerCase(), s = $("#season").value;
    const f = all.filter(c => c.crop.includes(q) && (!s || c.seasons.includes(s)));
    $("#cards").innerHTML = f.length ? f.map(c => `<div class="card crop-card"><h3>${c.crop}<span class="badge b-ideal">${c.duration_days} days</span></h3>
      <div class="tags"><span>${c.seasons}</span><span>${c.family}</span><span>${c.soil}</span></div>
      <table class="rng"><tr><th>Feature</th><th>Ideal</th><th>Acceptable</th></tr>${Object.entries(c.ranges).map(([k, r]) => `<tr><td>${FIELDS[k].l.replace(/ \(.*/, "")}</td><td>${r.ideal[0]}–${r.ideal[1]}</td><td>${r.acceptable[0]}–${r.acceptable[1]}</td></tr>`).join("")}</table>
      <div class="note">Ref. price ${inr(c.ref_price)}/q · yield ${c.yield_q_ha} q/ha · cost ${inr(c.cost_ha)}/ha · N-P₂O₅-K₂O ${c.N}-${c.P2O5}-${c.K2O} kg/ha</div></div>`).join("") : empty("fa-leaf", "No crops match your filter.");
  };
  $("#q").oninput = $("#season").onchange = draw; draw();
};

pages.land_check = async () => {
  await fillCrops($("#crop")); $("#fields").innerHTML = fieldsHTML(Object.keys(FIELDS), false);
  $("#form").onsubmit = e => {
    e.preventDefault(); submitWith($("#go"), async () => {
      const r = await api("/land-check", { crop: $("#crop").value, conditions: readFields(Object.keys(FIELDS)) });
      $("#result").innerHTML = `<div class="panel" style="text-align:center"><div class="gauge" style="--p:${r.score}"><span>${r.score}</span></div><p style="margin:12px 0 0">Fit score for <b>${cap(r.crop)}</b></p>${badge(r.verdict)}</div>
    <div class="panel tw"><table><tr><th>Feature</th><th>Your value</th><th>Ideal</th><th>Status</th></tr>${r.features.map(f => `<tr><td>${FIELDS[f.feature].l}</td><td>${f.value}</td><td>${f.ideal.join("–")}</td><td>${badge(f.status)}</td></tr>`).join("")}</table></div>
    <div class="panel"><h3><i class="fa-solid fa-screwdriver-wrench"></i> What to improve</h3>${r.improvements.length ? `<ul>${r.improvements.map(x => `<li>${x}</li>`).join("")}</ul>` : "All conditions are within the ideal range."}</div>
    <div class="panel"><h3><i class="fa-solid fa-brain"></i> What the ML model thinks</h3>${r.ml.status === "OUT_OF_RANGE" ? `<div class="alert bad">Inputs are out of the model's range – no ML opinion.</div>` : `<p>Model's top crop for this land: <b>${cap(r.ml.predicted_crop)}</b> (${badge(r.ml.status === "OK" ? "ok" : "low", r.ml.status.replace("_", " "))}). Probability for <b>${cap(r.crop)}</b>: <b>${((r.ml.probability_for_selected_crop || 0) * 100).toFixed(1)}%</b>.</p>`}<div class="note">${r.note}</div></div>`;
    });
  };
};

pages.fertilizer = async () => {
  await fillCrops($("#crop")); $("#fields").innerHTML = fieldsHTML(["N", "P", "K"], false);
  $("#form").onsubmit = e => {
    e.preventDefault(); submitWith($("#go"), async () => {
      const s = readFields(["N", "P", "K"]); const a = parseFloat($("#area").value); if (!(a > 0)) throw new Error("Area must be above 0");
      const r = await api("/fertilizer", { crop: $("#crop").value, ...s, area_ha: a }), q = r.quantity;
      $("#result").innerHTML = `<div class="kv"><div><b>${Math.round(q.urea_kg)} kg</b><span>Urea</span></div><div><b>${Math.round(q.dap_kg)} kg</b><span>DAP</span></div><div><b>${Math.round(q.mop_kg)} kg</b><span>MOP</span></div><div><b>${inr(r.estimated_cost_inr)}</b><span>Estimated cost</span></div></div>
    <div class="panel tw"><h3><i class="fa-solid fa-gauge-high"></i> Nutrient requirement (kg/ha)</h3><table><tr><th>Nutrient</th><th>Soil class</th><th>Crop dose</th><th>Adjusted need</th></tr>
    ${[["N", "N"], ["P2O5", "P"], ["K2O", "K"]].map(([n, k]) => `<tr><td>${n.replace("2O5", "₂O₅").replace("2O", "₂O")}</td><td>${badge(r.soil_class[k] === "LOW" ? "low" : r.soil_class[k] === "HIGH" ? "ideal" : "medium", r.soil_class[k])}</td><td>${r.recommended_dose_kg_ha[n]}</td><td>${r.nutrient_need_kg_ha[n]} (${r.adjustment[k]})</td></tr>`).join("")}</table></div>
    <div class="panel"><h3><i class="fa-solid fa-calendar-days"></i> Application schedule (for ${r.area_ha} ha)</h3><p><b>Basal:</b> ${r.basal.urea_kg} kg urea + ${r.basal.dap_kg} kg DAP + ${r.basal.mop_kg} kg MOP</p>${r.top_dressing.map(t => `<p><b>Top-dressing:</b> ${t.urea_kg} kg urea at ${t.when}</p>`).join("")}</div>
    <div class="sponsor"><span class="badge b-low">SPONSORED</span> ${r.sponsored.items.map(i => `<p style="margin:6px 0"><b>${i.name}</b> – ${i.product}</p>`).join("")}<div class="note">${r.sponsored.note}</div></div>
    <div class="note"><b>Assumptions:</b><ul>${r.assumptions.map(x => `<li>${x}</li>`).join("")}</ul></div>`;
    });
  };
};

pages.market = async () => {
  await fillCrops($("#crop")); await fillStates($("#state"));
  $("#form").onsubmit = e => {
    e.preventDefault(); submitWith($("#go"), async () => {
      const st = $("#state").value, r = await api(`/market/${$("#crop").value}` + (st ? `?state=${encodeURIComponent(st)}` : ""));
      let h = `<div class="panel"><div class="inl" style="justify-content:space-between">${badge(r.type === "live" ? "live" : "ref", r.type === "live" ? "LIVE MANDI PRICES" : "REFERENCE PRICE (not live)")}<span class="note">Retrieved ${r.retrieved_on}${r.latest_market_date ? " · latest market date " + r.latest_market_date : ""}${r.cached ? " · cached (6 h)" : ""}</span></div><p>${r.message}</p>`;
      if (r.type === "live") {
        h += `<div class="chart-box"><canvas id="c-mk"></canvas></div></div><div class="panel tw"><table><tr><th>State</th><th>Market</th><th>Date</th><th>Min</th><th>Max</th><th>Modal</th></tr>${r.records.map(x => `<tr><td>${x.state}</td><td>${x.market}</td><td>${x.date}</td><td>${x.min}</td><td>${x.max}</td><td><b>${x.modal}</b></td></tr>`).join("")}</table><div class="note">Rs per quintal. Source: Agmarknet via data.gov.in.</div></div>`;
        $("#result").innerHTML = h;
        const rs = r.records.slice(0, 15); chart("c-mk", { type: "bar", data: { labels: rs.map(x => x.market), datasets: [{ label: "Min", data: rs.map(x => x.min), backgroundColor: "#DCECCB" }, { label: "Modal", data: rs.map(x => x.modal), backgroundColor: "#4C956C" }, { label: "Max", data: rs.map(x => x.max), backgroundColor: "#174D32" }] } });
      } else { h += `<div class="kv"><div><b>${inr(r.reference_price)}</b><span>Reference price per quintal</span></div></div><div class="note">No historical series is available without the live API, so no trend chart is shown.</div></div>`; $("#result").innerHTML = h; }
    });
  };
};

pages.profit = async () => {
  await fillCrops($("#crop")); await fillStates($("#state"));
  const hint = async () => { const c = await api("/crops/" + $("#crop").value); $("#price").placeholder = c.ref_price; $("#yld").placeholder = c.yield_q_ha; $("#cost").placeholder = c.cost_ha; $("#dur").placeholder = c.duration_days; };
  $("#crop").onchange = hint; hint();
  $("#form").onsubmit = e => {
    e.preventDefault(); submitWith($("#go"), async () => {
      const b = { crop: $("#crop").value, area_ha: parseFloat($("#area").value), state: $("#state").value || null };
      [["price", "price_per_q"], ["yld", "yield_q_ha"], ["cost", "cost_per_ha"], ["dur", "duration_days"]].forEach(([id, k]) => { const v = parseFloat($("#" + id).value); if (!isNaN(v)) b[k] = v; });
      const r = await api("/profit", b), s = r.scenarios;
      $("#result").innerHTML = `<div class="kv"><div><b>${inr(r.price_per_q)}</b><span>Price/q (${r.price_source})</span></div><div><b>${inr(r.total_cost)}</b><span>Total cost</span></div><div><b>${r.break_even_yield_q_ha} q/ha</b><span>Break-even yield</span></div><div><b>${inr(r.break_even_price_per_q)}</b><span>Break-even price/q</span></div></div>
    <div class="panel tw"><table><tr><th>Scenario</th><th>Yield q/ha</th><th>Revenue</th><th>Profit</th><th>Profit / month</th></tr>${Object.entries(s).map(([k, v]) => `<tr><td>${cap(k)}</td><td>${v.yield_q_ha}</td><td>${inr(v.revenue)}</td><td><b style="color:${v.profit < 0 ? "#B3392F" : "#12623a"}">${inr(v.profit)}</b></td><td>${inr(v.profit_per_month)}</td></tr>`).join("")}</table></div>
    <div class="panel"><div class="chart-box" style="height:240px"><canvas id="c-pf"></canvas></div><div class="note">${r.note} Crop duration ${r.duration_days} days.</div></div>`;
      chart("c-pf", { type: "bar", data: { labels: Object.keys(s).map(cap), datasets: [{ label: "Revenue", data: Object.values(s).map(v => v.revenue), backgroundColor: "#4C956C" }, { label: "Profit", data: Object.values(s).map(v => v.profit), backgroundColor: "#174D32" }] } });
    });
  };
};

pages.what_if = async () => {
  const keys = Object.keys(FIELDS); $("#fields").innerHTML = fieldsHTML(keys, false);
  const fsel = keys.map(k => `<option value="${k}">${FIELDS[k].l}</option>`).join(""); $("#sw-f").innerHTML = fsel;
  const addRow = () => {
    const d = document.createElement("div"); d.className = "inl chg"; d.style.marginBottom = "8px";
    d.innerHTML = `<div><label>Feature</label><select class="c-f">${fsel}</select></div><div><label>Mode</label><select class="c-m"><option value="set">Set to</option><option value="add">Add</option><option value="pct">Change by %</option></select></div><div><label>Value</label><input type="number" class="c-v" step="any" value="0"></div><button type="button" class="btn ghost sm" aria-label="Remove change"><i class="fa-solid fa-xmark"></i></button>`;
    d.querySelector("button").onclick = () => d.remove(); $("#changes").appendChild(d);
  };
  addRow(); $("#add-change").onclick = addRow;
  const base = () => readFields(keys);
  $("#form").onsubmit = e => {
    e.preventDefault(); submitWith($("#go"), async () => {
      const ch = {}; $$(".chg").forEach(r => { const v = parseFloat($(".c-v", r).value); if (!isNaN(v)) ch[$(".c-f", r).value] = { mode: $(".c-m", r).value, value: v }; });
      if (!Object.keys(ch).length) throw new Error("Add at least one change.");
      const r = await api("/what-if", { base: base(), changes: ch }), o = r.original, m = r.modified, row = x => x.crop ? `<b>${cap(x.crop)}</b> (${(x.top_k[0].probability * 100).toFixed(0)}%)` : "No recommendation";
      $("#result").innerHTML = `<div class="grid g2"><div class="card"><div class="note">Original</div><h3>${row(o)}</h3>${badge(o.status === "OK" ? "ok" : o.status === "OUT_OF_RANGE" ? "out" : "low", o.status.replace("_", " "))}</div><div class="card"><div class="note">Modified</div><h3>${row(m)}</h3>${badge(m.status === "OK" ? "ok" : m.status === "OUT_OF_RANGE" ? "out" : "low", m.status.replace("_", " "))}</div></div>
    ${r.top_crop_changed ? `<div class="alert"><b>The top crop changed.</b></div>` : ""}
    <div class="panel"><h3><i class="fa-solid fa-chart-column"></i> Probability change</h3><div class="chart-box"><canvas id="c-wi"></canvas></div></div>
    <div class="panel tw"><table><tr><th>Changed feature</th><th>From</th><th>To</th></tr>${r.influential_changes.map(x => `<tr><td>${FIELDS[x.feature].l}</td><td>${x.from}</td><td>${x.to}</td></tr>`).join("")}</table><div class="note">${r.note}</div></div>`;
      chart("c-wi", { type: "bar", data: { labels: r.probability_changes.map(x => cap(x.crop)), datasets: [{ label: "Before %", data: r.probability_changes.map(x => x.before * 100), backgroundColor: "#DCECCB" }, { label: "After %", data: r.probability_changes.map(x => x.after * 100), backgroundColor: "#174D32" }] } });
    });
  };
  $("#sweep-form").onsubmit = e => {
    e.preventDefault(); submitWith($("#sw-go"), async () => {
      const r = await api("/what-if/sweep", { base: base(), feature: $("#sw-f").value, start: parseFloat($("#sw-a").value), end: parseFloat($("#sw-b").value), steps: parseInt($("#sw-n").value) });
      const tops = [...new Set(r.points.map(p => p.top_crop))];
      $("#sweep-result").innerHTML = `<div class="panel"><h3><i class="fa-solid fa-chart-line"></i> Sweep of ${FIELDS[r.feature].l}</h3><div class="chart-box"><canvas id="c-sw"></canvas></div>
    ${r.tipping_points.length ? `<div class="alert"><b>Tipping points</b><ul>${r.tipping_points.map(t => `<li>Between ${t.between[0]} and ${t.between[1]}: ${cap(t.from)} → ${cap(t.to)}</li>`).join("")}</ul></div>` : `<p class="note">The top crop does not change over this range.</p>`}</div>`;
      chart("c-sw", { type: "line", data: { labels: r.points.map(p => p.value), datasets: tops.map((c, i) => ({ label: cap(c), data: r.points.map(p => p.probabilities[c] * 100), borderColor: COL[i % COL.length], backgroundColor: COL[i % COL.length], tension: .25 })) }, options: { scales: { y: { title: { display: true, text: "Probability %" } }, x: { title: { display: true, text: FIELDS[r.feature].l } } } } });
    });
  };
  const pre = () => { const f = FIELDS[$("#sw-f").value]; $("#sw-a").value = f.min === 0 ? 0 : f.min; $("#sw-b").value = Math.min(f.max, f.d * 2 || f.max); }; $("#sw-f").onchange = pre; $("#sw-f").value = "rainfall"; pre();
};

pages.rotation = async () => {
  await fillCrops($("#crop")); $("#fields").innerHTML = fieldsHTML(Object.keys(FIELDS), false);
  $("#use-ml").onchange = () => $("#ml-box").hidden = !$("#use-ml").checked;
  $("#form").onsubmit = e => {
    e.preventDefault(); submitWith($("#go"), async () => {
      const b = { previous_crop: $("#crop").value, next_season: $("#season").value || null };
      if ($("#use-ml").checked) b.conditions = readFields(Object.keys(FIELDS));
      const r = await api("/rotation", b);
      $("#result").innerHTML = r.suggestions.length ? r.suggestions.map((s, i) => `<div class="card" style="margin-bottom:14px"><h3 style="text-transform:capitalize">${i + 1}. ${s.crop} <span class="badge b-ideal">score ${s.score}</span></h3><div class="tags"><span>${s.seasons}</span><span>${s.duration_days} days</span></div><ul>${s.reasons.map(x => `<li>${x}</li>`).join("")}</ul></div>`).join("") + `<div class="note">${r.disclaimer}</div>` : empty("fa-rotate", "No suitable crops for that season. Try another.");
    });
  };
};

pages.model_performance = async () => {
  const [m, cw, rb, dr] = await Promise.all([api("/metrics"), api("/metrics/classwise"), api("/metrics/robustness"), api("/metrics/decision-rules")]);
  $("#best").innerHTML = `${m.best_model} <small>(selected among ${m.tied_models.join(", ")} – statistically tied within ${m.tie_tolerance} CV accuracy)</small>`;
  $("#cmp").innerHTML = `<tr><th>Model</th><th>CV Accuracy</th><th>Test Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th><th>Macro F1</th><th>Top-3</th></tr>` + m.comparison.map(x => `<tr${x.Model === m.best_model ? ' style="background:#eef6e8;font-weight:600"' : ""}><td>${x.Model}</td><td>${(x["CV Accuracy"] * 100).toFixed(2)}% ± ${(x["CV Std"] * 100).toFixed(2)}</td><td>${(x["Test Accuracy"] * 100).toFixed(2)}%</td><td>${x.Precision.toFixed(4)}</td><td>${x.Recall.toFixed(4)}</td><td>${x["F1-score"].toFixed(4)}</td><td>${x["Macro F1"].toFixed(4)}</td><td>${(x["Top-3 Accuracy"] * 100).toFixed(1)}%</td></tr>`).join("");
  const cl = Object.keys(cw).filter(k => !["accuracy", "macro avg", "weighted avg"].includes(k));
  chart("c-cw", { type: "bar", data: { labels: cl.map(cap), datasets: [{ label: "F1-score", data: cl.map(k => cw[k]["f1-score"]), backgroundColor: "#4C956C" }] }, options: { scales: { y: { min: .9, max: 1.01 } }, plugins: { legend: { display: false } } } });
  chart("c-rb", { type: "bar", data: { labels: Object.keys(rb.single_feature).map(k => FIELDS[k].l.replace(/ \(.*/, "")), datasets: [{ label: "Noise on one feature", data: Object.values(rb.single_feature).map(v => v * 100), backgroundColor: "#174D32" }, { label: "Feature missing (mean-filled)", data: Object.values(rb.missing_feature).map(v => v * 100), backgroundColor: "#B7791F" }] }, options: { scales: { y: { title: { display: true, text: "% predictions changed" } } } } });
  $("#rb-all").textContent = Object.entries(rb.all_features).map(([k, v]) => `${k} noise → ${(v * 100).toFixed(1)}% change`).join(" · ");
  $("#rules").textContent = dr.rules;
};

/* ---- boot ---- */
document.addEventListener("DOMContentLoaded", () => {
  $(".burger")?.addEventListener("click", () => $(".menu").classList.toggle("open"));
  $(".dd>button")?.addEventListener("click", e => e.currentTarget.parentElement.classList.toggle("open"));
  const p = pages[document.body.dataset.page];
  if (p) Promise.resolve(p()).catch(e => toast(e.message, "error"));
});
