const state = {
  meta: null,
  quarter: "Q4",
  intelligence: null,
  reportMode: "quarter",
  actions: [],
  lastSimulation: null,
  agentThreadId: null,
  suppressAutosave: false,
  timers: new Map(),
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const num = value => value === "" || value == null ? 0 : Number(value);
const fmt = (value, digits = 0) => value == null ? "—" : Number(value).toLocaleString("he-IL", {maximumFractionDigits: digits});
const sf = value => value == null ? "—" : `${fmt(value)} SF`;
const score = value => value == null ? "—" : fmt(value, 1);
const pct = value => value == null ? "—" : `${fmt(Number(value) * (Math.abs(Number(value)) <= 1 ? 100 : 1), 1)}%`;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  return type.includes("application/json") ? response.json() : response.text();
}

function toast(message, isError = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.className = "toast", 3800);
}

function saveStatus(mode, text) {
  const element = $("#saveState");
  element.className = `status-chip ${mode}`;
  element.textContent = text;
}

function formPayload(form) {
  const result = {};
  new FormData(form).forEach((value, key) => {
    const input = form.elements[key];
    result[key] = input?.type === "number" ? num(value) : value;
  });
  return result;
}

function fillForm(form, data) {
  state.suppressAutosave = true;
  [...form.elements].forEach(input => {
    if (!input.name || input.type === "file" || input.type === "submit") return;
    input.value = data?.[input.name] ?? "";
  });
  state.suppressAutosave = false;
}

function fillSelect(select, values, selected, includeBlank = false) {
  const options = includeBlank ? ["", ...values] : values;
  select.innerHTML = options.map(value => `<option value="${esc(value)}">${esc(value || "הכול")}</option>`).join("");
  if (selected != null) select.value = selected;
}

function openMenu() {
  document.body.classList.add("menu-open");
  $("#sideNav").setAttribute("aria-hidden", "false");
  $("#menuButton").setAttribute("aria-expanded", "true");
  $("#menuButton").setAttribute("aria-label", "סגירת תפריט");
  $("#menuOverlay").hidden = false;
}

function closeMenu() {
  document.body.classList.remove("menu-open");
  $("#sideNav").setAttribute("aria-hidden", "true");
  $("#menuButton").setAttribute("aria-expanded", "false");
  $("#menuButton").setAttribute("aria-label", "פתיחת תפריט");
  $("#menuOverlay").hidden = true;
}

function showSection(name) {
  $$(".page").forEach(page => page.classList.toggle("active", page.id === `section-${name}`));
  $$(".nav-item").forEach(button => button.classList.toggle("active", button.dataset.section === name));
  closeMenu();
  window.scrollTo({top: 0, behavior: "smooth"});
}

function debounceSave(key, task, delay = 650) {
  if (state.suppressAutosave) return;
  clearTimeout(state.timers.get(key));
  saveStatus("saving", "שינויים ממתינים…");
  state.timers.set(key, setTimeout(async () => {
    saveStatus("saving", "שומר בענן…");
    try {
      await task();
      saveStatus("saved", `נשמר ${new Date().toLocaleTimeString("he-IL", {hour:"2-digit", minute:"2-digit"})}`);
      await loadIntelligence();
    } catch (error) {
      saveStatus("error", "השמירה נכשלה");
      toast(error.message, true);
    }
  }, delay));
}

function kpi(label, value, note = "") {
  return `<article class="kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></article>`;
}

function renderScoreAndForecast() {
  const data = state.intelligence;
  const card = data?.scorecard || {};
  const forecast = data?.forecast_q9 || {};
  const financial = data?.financial?.consolidated || {};
  const scoreRange = forecast.score || {};
  $("#q9Score").textContent = scoreRange.base == null ? "—" : `${score(scoreRange.low)}–${score(scoreRange.high)}`;
  $("#q9Confidence").textContent = `תרחיש בסיס ${score(scoreRange.base)} · ודאות ${forecast.confidence || "—"}`;
  $("#pastScore").textContent = score(card.past?.score);
  $("#futureScore").textContent = score(card.future?.score);
  $("#pastCoverage").textContent = `כיסוי נתונים ${pct(card.past?.coverage)}`;
  $("#futureCoverage").textContent = `כיסוי נתונים ${pct(card.future?.coverage)}`;
  $("#availableBudget").textContent = sf(financial.available_budget_sf);
  $("#scenarioBudgetLabel").textContent = `תקציב ${sf(financial.available_budget_sf)}`;
}

function renderRecommendations() {
  const rows = state.intelligence?.recommendations || [];
  $("#recommendationsList").innerHTML = rows.length ? rows.map((row, index) => `<div class="recommendation">
    <span class="priority">${index + 1}</span><div><strong>${esc(row.title)}</strong><small>${esc(row.rationale)}</small><small class="strategy-note">${esc(row.strategy_alignment || "")}</small></div>
    <button class="button secondary" type="button" data-simulate-recommendation="${index}">סמלץ</button>
  </div>`).join("") : '<div class="empty-copy">אין עדיין מספיק נתונים ליצירת המלצות.</div>';
}

function areaOptions() {
  const areas = state.intelligence?.financial?.areas || [];
  return ["חברה מאוחדת", ...areas.map(row => row.area)];
}

function financeView(name) {
  const data = state.intelligence?.financial;
  if (!data) return {};
  if (name === "חברה מאוחדת") return data.consolidated || {};
  return data.areas?.find(row => row.area === name) || {};
}

function renderDashboardFinance() {
  const selected = $("#dashboardAreaSelect").value || "חברה מאוחדת";
  const row = financeView(selected);
  $("#dashboardFinance").innerHTML = [
    ["מזומן זמין", sf(row.ending_cash_sf)],
    ["תקציב פנוי", sf(row.available_budget_sf)],
    ["רווח נקי", sf(row.net_profit_sf)],
    ["חוב", sf(row.debt_sf)],
    ["הון חוזר", sf(row.working_capital_sf)],
  ].map(([label, value]) => `<div class="metric-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function renderForecastSummary() {
  const forecast = state.intelligence?.forecast_q9 || {};
  $("#forecastSummary").innerHTML = [
    ["הכנסות Q9", sf(forecast.revenue_sf?.base), `טווח ${sf(forecast.revenue_sf?.low)}–${sf(forecast.revenue_sf?.high)}`],
    ["רווח נקי Q9", sf(forecast.net_profit_sf?.base), `טווח ${sf(forecast.net_profit_sf?.low)}–${sf(forecast.net_profit_sf?.high)}`],
    ["מזומן Q9", sf(forecast.ending_cash_sf?.base), `טווח ${sf(forecast.ending_cash_sf?.low)}–${sf(forecast.ending_cash_sf?.high)}`],
  ].map(([label, value, note]) => `<div class="forecast-item"><span>${label}</span><strong>${value}</strong><small>${note}</small></div>`).join("");
}

function renderDashboardResearch() {
  const rows = state.intelligence?.research_results || [];
  $("#dashboardResearch").innerHTML = rows.length ? rows.slice(0, 3).map(row => `<div class="compact-row"><div><strong>${esc(row.title)}</strong><small>${esc(row.key_result || "ללא סיכום מאושר")}</small></div><span class="soft-pill">${esc(row.confidence)}</span></div>`).join("") : '<div class="empty-copy">לא נקלטו מחקרי שוק מאושרים.</div>';
}

async function loadIntelligence() {
  state.intelligence = await api(`/api/intelligence/${state.quarter}`);
  renderScoreAndForecast();
  renderRecommendations();
  renderForecastSummary();
  renderDashboardResearch();
  const options = areaOptions();
  const dashboardSelection = $("#dashboardAreaSelect").value || options[0];
  const financeSelection = $("#financeAreaSelect").value || options[0];
  fillSelect($("#dashboardAreaSelect"), options, options.includes(dashboardSelection) ? dashboardSelection : options[0]);
  fillSelect($("#financeAreaSelect"), options, options.includes(financeSelection) ? financeSelection : options[0]);
  renderDashboardFinance();
  renderFinancePage();
  const readiness = await api(`/api/dashboard/${state.quarter}`);
  $("#setupNotice").classList.toggle("hidden", readiness.onboarding?.ready);
}

function renderFinancePage() {
  const selected = $("#financeAreaSelect").value || "חברה מאוחדת";
  const row = financeView(selected);
  $("#financeKpis").innerHTML = [
    kpi("הכנסות", sf(row.revenue_sf), selected), kpi("רווח נקי", sf(row.net_profit_sf), selected),
    kpi("מזומן", sf(row.ending_cash_sf), selected), kpi("תקציב פנוי", sf(row.available_budget_sf), "לאחר התחייבויות"),
    kpi("חוב", sf(row.debt_sf), selected), kpi("מלאי", sf(row.inventory_value_sf), selected),
    kpi("הון חוזר", sf(row.working_capital_sf), selected), kpi("התחייבויות השקעה", sf(row.capex_commitments_sf), selected),
  ].join("");
  const areas = state.intelligence?.financial?.areas || [];
  $("#areaFinanceBody").innerHTML = areas.length ? areas.map(item => `<tr><td>${esc(item.area)}</td><td>${esc(item.currency)}</td><td>${fmt(item.revenue_sf)}</td><td>${fmt(item.net_profit_sf)}</td><td>${fmt(item.ending_cash_sf)}</td><td>${fmt(item.debt_sf)}</td><td>${fmt(item.inventory_value_sf)}</td><td>${fmt(item.available_budget_sf)}</td></tr>`).join("") : '<tr><td colspan="8" class="empty-copy">לא נקלטו עדיין נתונים לפי מדינה.</td></tr>';
}

async function loadUploads() {
  const [uploads, imports] = await Promise.all([api("/api/uploads"), api("/api/imports")]);
  $("#uploadCount").textContent = `${uploads.length} קבצים`;
  $("#importCount").textContent = `${imports.length} תהליכים`;
  $("#uploadsList").innerHTML = uploads.length ? uploads.map(row => `<div class="file-row"><strong>${esc(row.original_name)}</strong><span>${esc(row.quarter)}</span><span>${esc(row.category)}</span><span>${fmt(row.size_bytes / 1024, 1)} KB</span><div class="file-actions"><a href="/api/uploads/${encodeURIComponent(row.id)}/download">הורדה</a><button class="delete" data-delete-upload="${esc(row.id)}" type="button">מחיקה</button></div></div>`).join("") : '<div class="empty-copy">טרם הועלו קבצים.</div>';
  $("#importsList").innerHTML = imports.length ? imports.map(row => {
    const data = row.extracted_data || {};
    const count = Object.keys(data.finance || {}).length + (data.finance_by_area || []).length + (data.operations || []).length + (data.research_results || []).length + (data.strategy_profile && Object.keys(data.strategy_profile).length ? 1 : 0);
    const issues = (row.issues || []).join(" · ");
    const className = row.committed_at ? "committed" : row.status === "מוכן לאישור" ? "ready" : "";
    return `<div class="import-card ${className}"><div class="import-top"><div><strong>${esc(row.quarter)} · ${esc(row.parser_type)}</strong><p>${count} פריטים זוהו · ודאות ${esc(row.confidence)}</p></div>${row.committed_at ? '<span class="soft-pill">נקלט</span>' : `<button class="button secondary" type="button" data-commit-import="${esc(row.id)}" ${count ? "" : "disabled"}>אישור קליטה</button>`}</div>${issues ? `<p>${esc(issues)}</p>` : ""}</div>`;
  }).join("") : '<div class="empty-copy">לא בוצעו עדיין תהליכי חילוץ.</div>';
  document.querySelectorAll("#importsList .import-card").forEach((card, index) => {
    const data = imports[index]?.extracted_data || {};
    card.insertAdjacentHTML("beforeend", `<details class="extraction-preview"><summary>צפייה בנתונים שחולצו לפני אישור</summary><pre>${esc(JSON.stringify(data, null, 2))}</pre></details>`);
  });
}

async function loadReports() {
  const endpoint = state.reportMode === "quarter" ? "quarter" : "cumulative";
  const data = await api(`/api/reports/${endpoint}/${state.quarter}`);
  $("#reportHeader").innerHTML = `<h2>${state.reportMode === "quarter" ? `דוח ${esc(state.quarter)}` : `דוח מצטבר Q1–${esc(state.quarter)}`}</h2><p>${esc(data.scorecard?.label || "")}</p>`;
  const finance = data.finance || data.finance_history?.at(-1) || {};
  $("#reportKpis").innerHTML = [kpi("הכנסות", sf(finance.revenue_sf)), kpi("רווח נקי", sf(finance.net_profit_sf)), kpi("מזומן", sf(finance.ending_cash_sf)), kpi("תחזית Q9", score(data.forecast_q9?.score?.base), `טווח ${score(data.forecast_q9?.score?.low)}–${score(data.forecast_q9?.score?.high)}`)].join("");
  const recs = data.recommendations || [];
  const missing = data.scorecard?.missing || [];
  $("#reportNarrative").innerHTML = `<div class="report-block"><h3>שורה תחתונה</h3><p>ביצועי עבר: ${score(data.scorecard?.past?.score)} · פוטנציאל עתידי: ${score(data.scorecard?.future?.score)} · תחזית Q9: ${score(data.forecast_q9?.score?.base)}.</p></div><div class="report-block"><h3>פעולות מומלצות</h3><ul>${recs.map(row => `<li>${esc(row.title)}</li>`).join("") || "<li>אין עדיין מספיק נתונים</li>"}</ul></div><div class="report-block"><h3>מידע חסר</h3><p>${missing.length ? esc(missing.join(" · ")) : "לא זוהו פערים מהותיים במודל הפנימי."}</p></div><div class="report-block"><h3>הנחות התחזית</h3><ul>${(data.forecast_q9?.assumptions || []).map(item => `<li>${esc(item)}</li>`).join("")}</ul></div>`;
  let history = data.history || [];
  if (!history.length) {
    const operations = data.operations || [];
    history = [{quarter: state.quarter, revenue_sf: finance.revenue_sf, net_profit_sf: finance.net_profit_sf, ending_cash_sf: finance.ending_cash_sf, units_sold: operations.reduce((sum, row) => sum + num(row.actual_sales), 0), ending_inventory: operations.reduce((sum, row) => sum + num(row.ending_inventory), 0), max_x_grade: Math.max(0, ...operations.filter(row => row.product === "X").map(row => num(row.grade))), max_y_grade: Math.max(0, ...operations.filter(row => row.product === "Y").map(row => num(row.grade)))}];
  }
  $("#trendBody").innerHTML = history.map(row => `<tr><td>${esc(row.quarter)}</td><td>${fmt(row.revenue_sf)}</td><td>${fmt(row.net_profit_sf)}</td><td>${fmt(row.ending_cash_sf)}</td><td>${fmt(row.units_sold)}</td><td>${fmt(row.ending_inventory)}</td><td>X${fmt(row.max_x_grade)} · Y${fmt(row.max_y_grade)}</td></tr>`).join("");
}

async function loadResearch() {
  const domain = $("#researchDomainSelect").value || "";
  const data = await api(`/api/research/relevant/${state.quarter}?domain=${encodeURIComponent(domain)}`);
  $("#researchResults").innerHTML = data.results.length ? data.results.map(row => `<article class="research-card ${row.relevant ? "relevant" : ""}"><div class="research-meta"><span class="soft-pill">${esc(row.quarter)}</span><span class="soft-pill">ודאות ${esc(row.confidence)}</span>${row.area ? `<span class="soft-pill">${esc(row.area)}</span>` : ""}</div><h2>${esc(row.title)}</h2><p>${esc(row.key_result || "טרם הוזן סיכום מובנה למחקר.")}</p><button class="text-link" type="button" data-ask-research="${esc(row.title)}">שאל את ה-Agent על המחקר ←</button></article>`).join("") : '<div class="empty-copy">לא נקלטו מחקרי שוק מאושרים.</div>';
  $("#researchCatalog").innerHTML = data.catalog.map(row => `<div class="compact-row"><div><strong>MR${esc(row.study_id)} · ${esc(row.name)}</strong><small>${esc(row.description)}</small></div><span class="soft-pill">${row.cost_k_sf == null ? "עלות לא ידועה" : `${fmt(row.cost_k_sf)}K SF`}</span></div>`).join("");
}

function renderActionBasket() {
  const labels = {price_change:"שינוי מחיר", production:"שינוי ייצור", advertising:"פרסום", rd:"מו״פ", capacity:"קיבולת", market_research:"מחקר שוק", loan:"מימון", partnership:"שיתוף פעולה", cash_protection:"הגנת מזומן"};
  $("#actionBasket").innerHTML = state.actions.length ? state.actions.map((action, index) => `<div class="action-card"><div><strong>${esc(labels[action.type] || action.type)}</strong><small>${esc(action.area || "כל החברה")} · ${esc(action.product || "כל המוצרים")}</small></div><span>${sf(action.cost_sf)}</span><button type="button" data-remove-action="${index}">הסרה</button></div>`).join("") : '<div class="empty-copy">סל הפעולות ריק.</div>';
}

function simulationPayload() {
  const financial = state.intelligence?.financial?.consolidated || {};
  return {name: `תרחיש ${state.quarter}`, budget_sf: financial.available_budget_sf, cash_buffer_sf: financial.cash_buffer_sf, actions: state.actions};
}

function renderSimulation(result) {
  state.lastSimulation = result;
  const status = result.feasible ? ["ok", "התרחיש עומד במגבלות התקציב והמזומן"] : ["bad", result.violations.join(" ")];
  $("#simulationResult").className = "";
  $("#simulationResult").innerHTML = `<div class="scenario-status ${status[0]}">${esc(status[1])}</div><div class="scenario-cases">${["low","base","high"].map(key => { const row = result.scenarios[key]; const label = {low:"נמוך",base:"בסיס",high:"גבוה"}[key]; return `<div class="scenario-case"><span>${label}</span><strong>Q9: ${score(row.q9_score)}</strong><span>רווח ${sf(row.net_profit_sf)}</span><span>מזומן ${sf(row.ending_cash_sf)}</span></div>`; }).join("")}</div><div class="metric-list"><div class="metric-row"><span>עלות מתוכננת</span><strong>${sf(result.budget.planned_cost_sf)}</strong></div><div class="metric-row"><span>תקציב נותר</span><strong>${sf(result.budget.remaining_sf)}</strong></div></div>`;
}

async function loadSavedScenarios() {
  const rows = await api(`/api/scenario-portfolios?quarter=${encodeURIComponent(state.quarter)}`);
  $("#savedScenarios").innerHTML = rows.length ? rows.map(row => `<div class="compact-row"><div><strong>${esc(row.name)}</strong><small>${esc(row.status)} · ${row.result?.feasible ? "אפשרי" : "דורש תיקון"}</small></div><button class="text-link" type="button" data-delete-portfolio="${esc(row.id)}">מחיקה</button></div>`).join("") : '<div class="empty-copy">אין תרחישים שמורים.</div>';
}

async function loadAgentStatus() {
  const data = await api("/api/agent/status");
  const element = $("#agentStatus");
  if (data.enabled && data.configured) { element.className = "status-chip ok"; element.textContent = `פעיל · ${data.model}`; }
  else { element.className = "status-chip"; element.textContent = "לא הוגדר ב־Render"; }
}

function addAgentBubble(role, content, sources = []) {
  const element = document.createElement("div");
  element.className = `agent-bubble ${role}`;
  element.textContent = content;
  if (sources.length) {
    const source = document.createElement("div");
    source.className = "agent-sources";
    source.textContent = `מקורות: ${sources.join(" · ")}`;
    element.appendChild(source);
  }
  $("#agentMessages").appendChild(element);
  element.scrollIntoView({behavior: "smooth", block: "end"});
}

async function loadSettings() {
  const settings = await api("/api/settings");
  fillForm($("#settingsForm"), settings);
  if (settings.selected_quarter) state.quarter = settings.selected_quarter;
  return settings;
}

function bindNavigation() {
  $("#menuButton").addEventListener("click", () => document.body.classList.contains("menu-open") ? closeMenu() : openMenu());
  $("#menuOverlay").addEventListener("click", closeMenu);
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeMenu(); });
  $$(".nav-item").forEach(button => button.addEventListener("click", () => showSection(button.dataset.section)));
  $$('[data-go]').forEach(button => button.addEventListener("click", () => showSection(button.dataset.go)));
}

function bindSettingsAndQuarter() {
  $("#settingsForm").addEventListener("input", () => debounceSave("settings", () => api("/api/settings", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(formPayload($("#settingsForm")))})));
  $("#quarterSelect").addEventListener("change", async event => {
    state.quarter = event.target.value;
    await api("/api/settings", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({selected_quarter: state.quarter})});
    await loadCurrentQuarter();
  });
}

function bindFiles() {
  $("#uploadFile").addEventListener("change", event => $("#fileChoice").textContent = event.target.files[0]?.name || "לא נבחר קובץ");
  $("#uploadForm").addEventListener("submit", async event => {
    event.preventDefault();
    const button = $("button[type=submit]", event.target);
    button.disabled = true; button.textContent = "מעלה ומפענח…";
    try { await api("/api/uploads", {method:"POST", body:new FormData(event.target)}); event.target.reset(); $("#fileChoice").textContent = "Excel, CSV, PDF, תמונה או מסמך"; toast("הקובץ נשמר והפענוח הושלם"); await loadUploads(); }
    catch (error) { toast(error.message, true); }
    finally { button.disabled = false; button.textContent = "העלאה ופענוח"; }
  });
  $("#importsList").addEventListener("click", async event => {
    const id = event.target.dataset.commitImport;
    if (!id) return;
    try { const result = await api(`/api/imports/${encodeURIComponent(id)}/commit`, {method:"POST"}); toast(`נקלטו ${Object.values(result.counts || {}).reduce((a,b) => a + b, 0)} פריטים`); await Promise.all([loadUploads(), loadIntelligence(), loadReports()]); }
    catch (error) { toast(error.message, true); }
  });
  $("#uploadsList").addEventListener("click", async event => {
    const id = event.target.dataset.deleteUpload;
    if (!id || !confirm("למחוק את הקובץ ואת נתוני החילוץ שלו?")) return;
    try { await api(`/api/uploads/${encodeURIComponent(id)}`, {method:"DELETE"}); await loadUploads(); toast("הקובץ נמחק"); }
    catch (error) { toast(error.message, true); }
  });
}

function bindFinance() {
  $("#dashboardAreaSelect").addEventListener("change", renderDashboardFinance);
  $("#financeAreaSelect").addEventListener("change", renderFinancePage);
  $("#areaFinanceForm").addEventListener("submit", async event => {
    event.preventDefault();
    const payload = formPayload(event.target);
    const area = payload.area;
    delete payload.area;
    try { await api(`/api/finance/${state.quarter}/areas/${encodeURIComponent(area)}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)}); toast("התיקון נשמר"); await loadIntelligence(); }
    catch (error) { toast(error.message, true); }
  });
}

function bindReportsAndResearch() {
  $("#quarterReportButton").addEventListener("click", async () => { state.reportMode = "quarter"; $("#quarterReportButton").classList.add("active"); $("#cumulativeReportButton").classList.remove("active"); await loadReports(); });
  $("#cumulativeReportButton").addEventListener("click", async () => { state.reportMode = "cumulative"; $("#cumulativeReportButton").classList.add("active"); $("#quarterReportButton").classList.remove("active"); await loadReports(); });
  $("#researchDomainSelect").addEventListener("change", loadResearch);
  $("#researchResults").addEventListener("click", event => { if (!event.target.dataset.askResearch) return; showSection("agent"); $("#agentForm [name=question]").value = `מה למדנו מהמחקר ${event.target.dataset.askResearch}, ולאילו החלטות הוא רלוונטי?`; });
}

function bindSimulation() {
  $("#actionForm").addEventListener("submit", event => {
    event.preventDefault();
    const action = formPayload(event.target);
    action.change_pct = num(action.change_pct) / 100;
    state.actions.push(action);
    renderActionBasket();
  });
  $("#actionBasket").addEventListener("click", event => { const index = event.target.dataset.removeAction; if (index == null) return; state.actions.splice(Number(index), 1); renderActionBasket(); });
  $("#recommendationsList").addEventListener("click", event => { const index = event.target.dataset.simulateRecommendation; if (index == null) return; const row = state.intelligence.recommendations[Number(index)]; state.actions.push({...row.action_template}); renderActionBasket(); showSection("simulation"); });
  $("#runSimulationButton").addEventListener("click", async () => { try { const result = await api(`/api/simulation/${state.quarter}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(simulationPayload())}); renderSimulation(result); } catch (error) { toast(error.message, true); } });
  $("#saveScenarioButton").addEventListener("click", async () => { if (!state.actions.length) return toast("יש להוסיף לפחות פעולה אחת", true); const name = prompt("שם התרחיש:", `תרחיש ${state.quarter}`); if (!name) return; try { await api("/api/scenario-portfolios", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({...simulationPayload(), name, quarter:state.quarter})}); toast("התרחיש נשמר"); await loadSavedScenarios(); } catch (error) { toast(error.message, true); } });
  $("#savedScenarios").addEventListener("click", async event => { const id = event.target.dataset.deletePortfolio; if (!id) return; await api(`/api/scenario-portfolios/${encodeURIComponent(id)}`, {method:"DELETE"}); await loadSavedScenarios(); });
}

function bindEconomics() {
  $("#economicsForm").addEventListener("submit", async event => {
    event.preventDefault();
    try {
      const result = await api("/api/economics/calculate", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(formPayload(event.target))});
      const values = {"מחיר מומלץ":result.recommendation?.recommended_price_lc,"טווח בטוח נמוך":result.recommendation?.safe_range_low_lc,"טווח בטוח גבוה":result.recommendation?.safe_range_high_lc,"רווח תפעולי צפוי":result.recommendation?.expected_operating_profit_lc,"מכירות צפויות":result.recommendation?.expected_units_sold,"מלאי סופי":result.recommendation?.expected_ending_inventory,"רצפת מזומן":result.price_floors?.cash_floor_lc,"מחיר איזון":result.price_floors?.operating_break_even_price_lc,"מחיר יעד":result.price_floors?.target_margin_price_lc};
      $("#economicsResult").className = "metric-list";
      $("#economicsResult").innerHTML = Object.entries(values).map(([label,value]) => `<div class="metric-row"><span>${label}</span><strong>${fmt(value,2)}</strong></div>`).join("");
    } catch (error) { toast(error.message, true); }
  });
}

function bindAgent() {
  $("#agentForm").addEventListener("submit", async event => {
    event.preventDefault();
    const question = String(new FormData(event.target).get("question") || "").trim();
    if (!question) return;
    addAgentBubble("user", question);
    event.target.reset();
    const button = $("button", event.target); button.disabled = true; button.textContent = "מנתח…";
    try { const result = await api("/api/agent/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({question, quarter:state.quarter, thread_id:state.agentThreadId})}); state.agentThreadId = result.thread_id; addAgentBubble("assistant", result.answer, result.sources || []); }
    catch (error) { addAgentBubble("assistant", `לא ניתן להפעיל את ה-Agent: ${error.message}`); }
    finally { button.disabled = false; button.textContent = "שליחה"; }
  });
}

function bindBackup() {
  $("#restoreForm").addEventListener("submit", async event => { event.preventDefault(); const data = new FormData(event.target); const mode = data.get("mode"); if (!confirm(mode === "replace" ? "השחזור יחליף את מצב המערכת. להמשיך?" : "למזג את הגיבוי?")) return; if (mode === "replace") data.set("confirmation", "RESTORE"); try { await api("/api/restore", {method:"POST", body:data}); toast("השחזור הושלם"); setTimeout(() => location.reload(), 800); } catch (error) { toast(error.message, true); } });
  $("#resetButton").addEventListener("click", async () => { const confirmation = prompt("הקלידו RESET כדי למחוק את נתוני החברה והקבצים:"); if (confirmation !== "RESET") return; try { await api("/api/admin/reset", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({confirmation})}); location.reload(); } catch (error) { toast(error.message, true); } });
}

async function loadHealth() {
  const element = $("#cloudState");
  try { const result = await api("/api/health"); element.className = "status-chip ok"; element.innerHTML = `<i></i> ענן מחובר · ${esc(result.storage_bucket)}`; }
  catch (error) { element.className = "status-chip error"; element.innerHTML = "<i></i> חיבור ענן נכשל"; toast(error.message, true); }
}

async function loadCurrentQuarter() {
  saveStatus("saving", "מעדכן…");
  try { await Promise.all([loadIntelligence(), loadUploads(), loadReports(), loadResearch(), loadSavedScenarios()]); saveStatus("saved", "מחובר ונשמר בענן"); }
  catch (error) { saveStatus("error", "טעינת הנתונים נכשלה"); toast(error.message, true); }
}

async function initialize() {
  bindNavigation(); bindSettingsAndQuarter(); bindFiles(); bindFinance(); bindReportsAndResearch(); bindSimulation(); bindEconomics(); bindAgent(); bindBackup();
  $("#refreshButton").addEventListener("click", loadCurrentQuarter);
  try {
    await loadHealth();
    state.meta = await api("/api/meta");
    const settings = await loadSettings();
    fillSelect($("#quarterSelect"), state.meta.quarters, state.quarter);
    fillSelect($("#settingsForm [name=startup_quarter]"), state.meta.quarters, settings.startup_quarter || "Q4");
    fillSelect($("#uploadForm [name=quarter]"), ["Q1","Q2","Q3",...state.meta.quarters.filter(item => !["Q1","Q2","Q3"].includes(item)),"Setup"], "Q1");
    fillSelect($("#uploadForm [name=category]"), state.meta.upload_categories, "פלט רבעוני");
    fillSelect($("#actionForm [name=area]"), state.meta.areas, "", true);
    fillSelect($("#actionForm [name=product]"), state.meta.products, "", true);
    fillSelect($("#actionForm [name=model]"), state.meta.models, "", true);
    renderActionBasket();
    await Promise.all([loadCurrentQuarter(), loadAgentStatus()]);
  } catch (error) {
    saveStatus("error", "המערכת אינה מוכנה");
    toast(error.message, true);
  }
}

document.addEventListener("DOMContentLoaded", initialize);
