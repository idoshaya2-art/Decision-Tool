const state = {
  meta: null,
  quarter: "Q4",
  intelligence: null,
  strategyOptimization: null,
  insights: null,
  marketIntelligence: null,
  governanceSessions: [],
  learningLedger: null,
  financeRange: null,
  reportMode: "cumulative",
  actions: [],
  lastSimulation: null,
  agentThreadId: null,
  rulebook: null,
  viewMode: "quarter",
  approvedQuarters: [],
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
const signedSf = value => value == null ? "—" : `${Number(value) > 0 ? "+" : ""}${fmt(value)} SF`;
const signedScore = value => value == null ? "—" : `${Number(value) > 0 ? "+" : ""}${fmt(value, 1)}`;
let menuReturnFocus = null;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || body.message || detail;
      if (typeof detail === "object") detail = detail.message || JSON.stringify(detail);
    } catch (_) {}
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

function latestApprovedQuarter() {
  return [...(state.approvedQuarters || [])]
    .sort((a, b) => quarterNumber(a) - quarterNumber(b))
    .at(-1) || null;
}

function nextPlanningQuarter(actualQuarter) {
  if (!actualQuarter) return state.quarter;
  return `Q${Math.min(9, quarterNumber(actualQuarter) + 1)}`;
}

function actualDataQuarter() {
  return state.intelligence?.financial?.actual_coverage?.data_as_of
    || state.intelligence?.action_review?.actual_as_of
    || latestApprovedQuarter()
    || null;
}

function renderDynamicQuarterContext(readiness = null) {
  const eyebrow = $("#dashboardQuarterEyebrow");
  const context = $("#dashboardContextText");
  const notice = $("#setupNotice");
  const noticeText = $("#setupNoticeText");
  if (!eyebrow || !context || !notice || !noticeText) return;

  const actual = actualDataQuarter();
  const selected = state.quarter;
  if (state.viewMode === "cumulative") {
    eyebrow.textContent = actual ? `מצב מצטבר עד ${actual}` : "מצב מצטבר";
    context.textContent = actual
      ? `Actuals מאושרים עד ${actual}; מגמות, החלטות ותחזית מצטברת עד Q9.`
      : "טרם אושר דוח רבעוני. לאחר האישור יוצגו מגמות ותחזית מצטברת עד Q9.";
  } else {
    eyebrow.textContent = `${selected} · חדר החלטות`;
    context.textContent = actual
      ? `המצב מבוסס על Actuals מאושרים עד ${actual}. ההמלצות מותאמות ל־${selected} ומציגות השפעה עד Q9.`
      : `טרם אושר דוח רבעוני. העלו תוצאות כדי להפעיל המלצות ל־${selected} ותחזית עד Q9.`;
  }

  const onboarding = readiness?.onboarding || {};
  const ready = Boolean(onboarding.ready ?? actual);
  notice.classList.toggle("hidden", ready);
  noticeText.textContent = actual
    ? "השלימו את פרטי האסטרטגיה או הנתונים החסרים המסומנים כדי לאפשר אופטימיזציה מלאה."
    : "העלו ואשרו דוח רבעוני אחד לפחות, ולאחר מכן אשרו את האסטרטגיה והיעדים.";

  const empty = $("#executionBlueprintEmpty");
  if (empty) {
    empty.textContent = actual
      ? `אין עדיין תכנית מספרית ל־${selected}. השלימו את הנתונים החסרים או אשרו את האסטרטגיה.`
      : `אין עדיין תכנית מספרית ל־${selected}. אשרו דוח רבעוני ואסטרטגיה כדי לייצר אותה.`;
  }
}

function renderQuarterPicker() {
  const select = $("#quarterSelect");
  if (!select || !state.meta) return;
  const approved = new Set(state.approvedQuarters || []);
  const options = [
    '<option value="__all__">מצטבר (הכול)</option>',
    ...state.meta.quarters.map(quarter => {
      const label = `${approved.has(quarter) ? "✓ " : ""}${quarter}`;
      return `<option value="${esc(quarter)}">${esc(label)}</option>`;
    }),
  ];
  select.innerHTML = options.join("");
  select.value = state.viewMode === "cumulative" ? "__all__" : state.quarter;
  renderDynamicQuarterContext();
}

function selectedActionDefinition() {
  const code = $("#actionForm [name=code]")?.value;
  return (state.meta?.decision_actions || []).find(item => item.code === code) || null;
}

function configureActionForm() {
  const definition = selectedActionDefinition();
  if (!definition) return;
  const allowed = new Set(definition.fields || []);
  $$('[data-action-field]', $("#actionForm")).forEach(label => {
    const visible = allowed.has(label.dataset.actionField);
    label.classList.toggle("hidden", !visible);
    $$('input,select', label).forEach(input => { input.disabled = !visible; });
  });
  if (definition.product) $("#actionForm [name=product]").value = definition.product;
  if ((definition.areas || []).length === 1) $("#actionForm [name=area]").value = definition.areas[0];
  $("#actionTiming").textContent = `${definition.category} · ${definition.timing}`;
  refreshFieldAdvice();
}

function recommendedTransfer() {
  const plan = state.intelligence?.financial?.liquidity_allocation || {};
  const transfers = plan.transfers || [];
  const form = $("#actionForm");
  const source = form?.elements?.area?.value;
  const target = form?.elements?.target_area?.value;
  return transfers.find(row =>
    (!source || row.source_area === source) &&
    (!target || row.target_area === target)
  ) || transfers[0] || null;
}

function latestOperationForInput(input) {
  const rows = state.intelligence?.latest_operations || [];
  const form = input?.form;
  const area = form?.elements?.area?.value || $("#actionForm [name=area]")?.value;
  const product = form?.elements?.product?.value || $("#actionForm [name=product]")?.value;
  const model = form?.elements?.model?.value || $("#actionForm [name=model]")?.value;
  return rows.find(row =>
    (!area || row.area === area) &&
    (!product || row.product === product) &&
    (!model || row.model === model)
  ) || rows.find(row => (!area || row.area === area) && (!product || row.product === product)) || rows[0] || null;
}

function fieldRecommendation(input) {
  const formId = input.form?.id || "";
  const name = input.name || input.id || "";
  const transfer = recommendedTransfer();
  const operation = latestOperationForInput(input);
  const policy = state.intelligence?.financial?.liquidity_allocation?.policy || {};
  const fallback = {
    value: "לא לנחש",
    reason: "הזינו רק ערך מדוח שאושר, מחקר שוק מאושר או תוצאת סימולציה. אם הנתון חסר, בקשו מה־AI רשימת מידע חסר.",
    source: "כלל אמינות של המערכת",
    confidence: "גבוהה",
  };
  const result = (value, rawValue, reason, source, confidence = "בינונית") => ({
    value, rawValue, reason, source, confidence,
  });

  if (formId === "actionForm") {
    const code = $("#actionForm [name=code]")?.value;
    const form = input.form;
    const area = form?.elements?.area?.value;
    const product = form?.elements?.product?.value;
    const model = form?.elements?.model?.value;
    const blueprintRows = state.intelligence?.execution_blueprint?.rows || [];
    const blueprint = blueprintRows.find(row =>
      row.form_code === code &&
      (!area || row.area === area) &&
      (!product || !row.action?.product || row.action.product === product) &&
      (!model || !row.action?.model || row.action.model === model)
    ) || blueprintRows.find(row => row.form_code === code);
    if (blueprint) {
      const directValue = blueprint.action?.[name];
      const specialValues = {
        study_id: blueprint.raw_value,
        area: blueprint.area,
        target_area: blueprint.target_area,
        amount_sf: blueprint.action?.amount_sf,
        cost_sf: blueprint.cost_sf,
      };
      const rawValue = directValue ?? specialValues[name];
      if (rawValue !== undefined && rawValue !== null && rawValue !== "") {
        const dependencies = (blueprint.dependencies || [])
          .map(item => `שלב ${item.step || "—"} ${item.title}`)
          .join(", ");
        const formatted = typeof rawValue === "number"
          ? (name.endsWith("_sf") ? sf(rawValue) : fmt(rawValue, 2))
          : String(rawValue);
        return result(
          formatted,
          rawValue,
          [
            blueprint.input_instruction,
            blueprint.gate,
            dependencies ? `תלוי ב: ${dependencies}.` : "",
            blueprint.expected_outcome ? `תוצאה צפויה: ${blueprint.expected_outcome}` : "",
          ].filter(Boolean).join(" "),
          blueprint.source || "תכנית הביצוע לרבעון",
          blueprint.confidence || "בינונית",
        );
      }
    }
  }

  if (input.type === "file") {
    return result(
      "הקובץ המקורי המלא",
      null,
      "העדיפו Excel של תוצאות הרבעון. העלו Q1, Q2 ו־Q3 בנפרד; PDF מתאים לחוקים, אסטרטגיה ומחקרים.",
      "תהליך הקליטה המאושר",
      "גבוהה",
    );
  }

  if (formId === "uploadForm" || formId === "agentUploadForm") {
    if (name === "quarter") return result("זיהוי אוטומטי", "Setup", "המערכת קוראת את הרבעון מתוך הקובץ ומונעת שיוך שגוי.", "שם הקובץ ותוכן הדוח", "גבוהה");
    if (name === "category") return result("פלט רבעוני", "פלט רבעוני", "לדוחות Q1–Q9. למסמכי חוקים או אסטרטגיה בחרו את הסוג המדויק.", "סוג המסמך", "גבוהה");
    if (name === "notes") return result("מקור + מטרת הקובץ", null, "לדוגמה: “תוצאות רשמיות Q3, כולל MR24 ו־MR61”. כך קל יותר לאמת את החילוץ.", "נוהל תיעוד", "גבוהה");
  }

  if (formId === "areaFinanceForm") {
    if (name === "fx_to_sf") return result("הערך המופיע בדוח הרבעוני", null, "אין להשתמש בשער אינטרנט או באומדן. זהו תיקון חריג ל־Actual בלבד.", "דוח רשמי — טבלת Currency", "גבוהה");
    return result("הערך המדויק בדוח המאושר", null, "אין לאמוד נתון חשבונאי ידנית. תקנו רק שדה שהחילוץ סימן כשגוי.", "Income Statement / Balance Sheet של האזור", "גבוהה");
  }

  if (formId === "settingsForm") {
    if (name === "cash_buffer_sf") {
      const recommended = policy.recommended_consolidated_cash_buffer_sf;
      return recommended
        ? result(sf(recommended), recommended, "רזרבה ניהולית לפי התחייבויות שוטפות, אזורים פעילים והתחייבויות השקעה. אשרו אותה כמדיניות צוות.", "Actuals מאושרים + מדיניות רזרבה שקופה", "בינונית")
        : result("לפחות 100,000 SF", 100000, "ערך פתיחה בלבד עד לקליטת מאזן והתחייבויות מלאים.", "הנחת ניהול זמנית", "נמוכה");
    }
    if (name === "min_rd_sf") return result("110,000 SF", 110000, "40,000 SF ל־X ועוד 70,000 SF ל־Y כאשר מממנים את שני מסלולי המו״פ.", "Data Log — ספי השקעת מו״פ", "גבוהה");
    if (name === "company_name") return result("שם הקבוצה הרשמי", null, "השתמשו בשם אחד קבוע בכל הדוחות, הגיבויים והחלטות ההנהלה.", "הגדרת צוות", "גבוהה");
    if (name === "startup_quarter") {
      const actual = actualDataQuarter();
      const recommended = nextPlanningQuarter(actual);
      return result(recommended, recommended, actual ? `זהו הרבעון הבא לאחר ה־Actual המאושר האחרון (${actual}).` : "בחרו את הרבעון הראשון שבו הצוות מתכנן החלטות.", actual ? "דוחות Actual מאושרים" : "הגדרת צוות", actual ? "גבוהה" : "בינונית");
    }
  }

  if (formId === "actionForm") {
    const code = formId && $("#actionForm [name=code]")?.value;
    if (code === "A3-1" && transfer) {
      const transferMap = {
        area: [transfer.source_area, transfer.source_area, "זהו האזור בעל עודף מזומן לאחר שמירת הרזרבה.", "Actuals לפי אזור + מנוע נזילות"],
        target_area: [transfer.target_area, transfer.target_area, "זהו האזור בעל פער המימון הדחוף ביותר.", "התחייבויות שוטפות, ספקים ומזומן לפי אזור"],
        amount_sf: [sf(transfer.net_amount_sf), transfer.net_amount_sf, `הסכום נטו סוגר את פער הרזרבה. המקור ישלם ${sf(transfer.gross_source_amount_sf)} כולל עמלת מטבע.`, "מנוע נזילות דטרמיניסטי"],
        currency: [transfer.source_currency, transfer.source_currency, `יש להזין את מטבע המקור; סכום המקור המקומי המשוער הוא ${fmt(transfer.source_amount_lc, 2)}.`, "Actuals + כללי מטבע"],
        target_currency: [transfer.target_currency, transfer.target_currency, `היעד יקבל כ־${fmt(transfer.target_amount_lc, 2)} במטבע המקומי.`, "Actuals + שערי הדוח"],
        cost_sf: [sf(transfer.estimated_fx_fee_sf), transfer.estimated_fx_fee_sf, `עמלת המרה משוערת ${pct(transfer.commission_rate)}. לאחר ההעברה יישארו במקור ${sf(transfer.source_cash_after_sf)}.`, "Data Log — עמלת המרה"],
      };
      if (transferMap[name]) return result(...transferMap[name], "בינונית");
    }
    if (name === "price_lc" && operation?.actual_price_lc != null) return result(fmt(operation.actual_price_lc, 2), operation.actual_price_lc, "זהו מחיר ה־Actual האחרון לאותו אזור/מוצר/דגם — נקודת מוצא לסימולציית תמחור, לא מחיר סופי אוטומטי.", `${operation.quarter} Actual`, "גבוהה");
    if (name === "advertising_lc" && operation?.advertising_lc != null) return result(fmt(operation.advertising_lc, 2), operation.advertising_lc, "התחילו מרמת הפרסום האחרונה ובדקו תרחיש שינוי מול מכירות ומרווח.", `${operation.quarter} Actual`, "בינונית");
    if (name === "units" && operation?.actual_sales != null) {
      const units = Math.max(0, Number(operation.actual_sales) - Number(operation.ending_inventory || 0));
      return result(fmt(units), units, `טיוטת בסיס: מכירות אחרונות ${fmt(operation.actual_sales)} פחות מלאי סיום ${fmt(operation.ending_inventory || 0)}. יש לאמת מול ביקוש, קיבולת וזמן אספקה.`, `${operation.quarter} Actual`, "בינונית");
    }
    if (name === "variable_cost_sf" && operation?.variable_cost_lc != null) {
      const row = (state.intelligence?.financial?.areas || []).find(item => item.area === operation.area);
      const value = Number(operation.variable_cost_lc) * Number(row?.fx_to_sf || 1);
      return result(sf(value), value, "עלות הייצור האחרונה שהומרה ל־SF לפי שער הדוח.", `${operation.quarter} Actual`, "בינונית");
    }
    if (name === "grade" && operation?.grade != null) return result(String(operation.grade), operation.grade, "הרמה הטכנולוגית האחרונה שאושרה לאותו מוצר ואזור.", `${operation.quarter} Actual`, "גבוהה");
    if (name === "x_grade") {
      const xRow = (state.intelligence?.latest_operations || []).find(row => row.area === (operation?.area || $("#actionForm [name=area]")?.value) && row.product === "X");
      if (xRow?.grade != null) return result(String(xRow.grade), xRow.grade, "רמת X זמינה באותו אזור; המערכת תבדוק תאימות לייצור Y.", `${xRow.quarter} Actual + חוק התאמת X–Y`, "גבוהה");
    }
    if (name === "plant_count") return result("0 עד להוכחת פער קיבולת", 0, "הקימו מפעל רק אם תחזית הביקוש והקיבולת המאושרת מצדיקות אותו גם בתרחיש Downside.", "קיבולת Actual + MR24 + בדיקת תקציב", "בינונית");
    if (name === "study_id") return result("המחקר שמסיר את אי־הוודאות בהחלטה", null, "בחרו מחקר רק אם תוצאתו עשויה לשנות את הפעולה; שאלו את ה־AI “איזה MR ישנה את ההחלטה ולמה?”.", "קטלוג מחקרי שוק + Value of Information", "בינונית");
  }

  if (formId === "economicsForm") {
    if (name === "price_lc" && operation?.actual_price_lc != null) return result(fmt(operation.actual_price_lc, 2), operation.actual_price_lc, "מחיר ה־Actual האחרון הוא נקודת הבסיס לסריקת המחירים.", `${operation.quarter} Actual`, "גבוהה");
    if (name === "base_demand_units" && operation?.actual_sales != null) return result(fmt(operation.actual_sales), operation.actual_sales, "השתמשו במכירות ה־Actual האחרונות כביקוש בסיס, ואז בדקו רגישות.", `${operation.quarter} Actual`, "בינונית");
    if (name === "manufacturing_cost_lc" && operation?.variable_cost_lc != null) return result(fmt(operation.variable_cost_lc, 2), operation.variable_cost_lc, "עלות הייצור המשתנה האחרונה שנקלטה.", `${operation.quarter} Actual`, "גבוהה");
    if (name === "available_units" && operation) {
      const value = Number(operation.ending_inventory || 0) + Number(operation.actual_production || 0);
      return result(fmt(value), value, "מלאי סיום ועוד הייצור האחרון כנקודת בדיקה; התאימו לייצור המתוכנן בתרחיש.", `${operation.quarter} Actual`, "בינונית");
    }
    if (name === "elasticity") return result("1.0", 1, "הנחת ניטרלית בלבד. אל תשנו בלי לפחות שתי תצפיות מחיר–מכירות או מחקר שוק רלוונטי.", "הנחת תרחיש שקופה", "נמוכה");
    if (name === "target_operating_margin") return result("20%", 0.2, "יעד ניהולי לבדיקת מחיר; יש להשוות לתרחישי 15% ו־25% ולמגבלת הביקוש.", "הנחת יעד פנימית", "נמוכה");
    if (name === "fixed_cost_lc" || name === "variable_selling_cost_lc") return result("העלות המדויקת מהדוח", null, "אין להזין 0 אלא אם הדוח מאשר שאין עלות. ערך חסר עלול להציג מחיר מומלץ נמוך מדי.", "דוח תפעולי / Data Log", "גבוהה");
  }

  if (formId === "agentForm") return result("שאלה שמחייבת מספרים ומקורות", null, "לדוגמה: “בדוק כל אזור ומטבע; חשב מאיפה להעביר, לאן, כמה נטו וברוטו, עמלה, ויתרת מזומן אחרי ההעברה”.", "כללי הפעלת Decision Agent", "גבוהה");
  if (name === "agentInstructions") return result("כל תשובה: מספרים, מקור, תלויות ו־Downside", null, "הוסיפו רצפת מזומן מאושרת, סדרי עדיפויות וקווים אדומים של הצוות.", "מדיניות הנהלה", "גבוהה");
  if (formId === "decisionForm") return result("החלטה מדידה וניתנת לתחקור", null, "תעדו סכום, אזור, מוצר, רבעון, נימוק, תוצאה צפויה ובעל אחריות — לא כותרת כללית בלבד.", "Decision Log", "גבוהה");
  if (formId === "restoreForm") return result("קובץ ZIP מלא מהמערכת", null, "שחזור מחליף או ממזג נתונים בהתאם לבחירה; הורידו גיבוי לפני הפעולה.", "Manifest של הגיבוי", "גבוהה");

  return fallback;
}

function renderFieldAdvice(input, popover) {
  if (!input || !popover) return;
  const advice = fieldRecommendation(input);
  const canApply = advice.rawValue !== undefined && advice.rawValue !== null && input.type !== "file";
  popover.innerHTML = `
    <strong>המלצה להזנה</strong>
    <b>${esc(advice.value)}</b>
    <p>${esc(advice.reason)}</p>
    <small>מקור: ${esc(advice.source)} · ודאות: ${esc(advice.confidence)}</small>
    ${canApply ? '<button type="button" class="field-advice-apply">מילוי ההמלצה</button>' : ""}
  `;
  const apply = $(".field-advice-apply", popover);
  if (apply) apply.addEventListener("click", event => {
    event.preventDefault();
    event.stopPropagation();
    input.value = advice.rawValue;
    input.dispatchEvent(new Event("input", {bubbles: true}));
    input.dispatchEvent(new Event("change", {bubbles: true}));
    input.closest("label")?.classList.remove("advice-open");
  });
}

function refreshFieldAdvice() {
  $$(".field-advice-button").forEach(button => {
    const label = button.closest("label");
    renderFieldAdvice(label?.querySelector("input:not([type=hidden]), select, textarea"), $(".field-advice-popover", label));
  });
}

function installFieldAdvice() {
  $$("form label").forEach(label => {
    const input = label.querySelector("input:not([type=hidden]), select, textarea");
    if (!input || label.querySelector(".field-advice-button")) return;
    label.classList.add("has-field-advice");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "field-advice-button";
    button.setAttribute("aria-label", "הצגת המלצה להזנה");
    button.setAttribute("aria-expanded", "false");
    button.textContent = "✦";
    const popover = document.createElement("div");
    popover.className = "field-advice-popover";
    label.insertBefore(button, input);
    label.insertBefore(popover, input);
    const update = () => renderFieldAdvice(input, popover);
    button.addEventListener("mouseenter", update);
    button.addEventListener("focus", update);
    button.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      const open = !label.classList.contains("advice-open");
      $$(".has-field-advice.advice-open").forEach(item => item.classList.remove("advice-open"));
      label.classList.toggle("advice-open", open);
      button.setAttribute("aria-expanded", String(open));
      update();
    });
  });
  document.addEventListener("click", event => {
    if (!event.target.closest(".has-field-advice")) $$(".has-field-advice.advice-open").forEach(item => item.classList.remove("advice-open"));
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") $$(".has-field-advice.advice-open").forEach(item => item.classList.remove("advice-open"));
  });
  refreshFieldAdvice();
}

function openMenu() {
  menuReturnFocus = document.activeElement;
  document.body.classList.add("menu-open");
  const sideNav = $("#sideNav");
  sideNav.setAttribute("aria-hidden", "false");
  sideNav.inert = false;
  $("#menuButton").setAttribute("aria-expanded", "true");
  $("#menuButton").setAttribute("aria-label", "סגירת תפריט");
  $("#menuOverlay").hidden = false;
  sideNav.querySelector("button:not([disabled]), a[href]")?.focus();
}

function closeMenu() {
  const wasOpen = document.body.classList.contains("menu-open");
  document.body.classList.remove("menu-open");
  const sideNav = $("#sideNav");
  sideNav.setAttribute("aria-hidden", "true");
  sideNav.inert = true;
  $("#menuButton").setAttribute("aria-expanded", "false");
  $("#menuButton").setAttribute("aria-label", "פתיחת תפריט");
  $("#menuOverlay").hidden = true;
  if (wasOpen && menuReturnFocus instanceof HTMLElement) menuReturnFocus.focus();
}

function showSection(name) {
  $$(".page").forEach(page => page.classList.toggle("active", page.id === `section-${name}`));
  $$(".nav-item").forEach(button => button.classList.toggle("active", button.dataset.section === name));
  $$(".primary-tab").forEach(button => button.classList.toggle("active", button.dataset.section === name));
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
  $("#liquidityPosition").textContent = sf(financial.ending_cash_sf);
  $("#liquidityNote").textContent = `רצפה ${sf(financial.cash_buffer_sf)} · פנוי להחלטות ${sf(financial.available_budget_sf)}`;
  const reviewSummary = data?.action_review?.summary || {};
  const blockerCount = num(reviewSummary.blocked_count) + num(reviewSummary.missing_data_count);
  $("#decisionBlockers").textContent = fmt(blockerCount);
  $("#decisionBlockersNote").textContent = blockerCount
    ? `${fmt(reviewSummary.blocked_count || 0)} חסומים · ${fmt(reviewSummary.missing_data_count || 0)} חסרי מידע`
    : "לא זוהו חסמים פתוחים";
  const actualCoverage = data?.financial?.actual_coverage || {};
  const blockingActions = (data?.action_review?.actions || [])
    .filter(row => ["blocked", "missing_data"].includes(row.status))
    .slice(0, 3);
  const gate = $("#decisionGateBanner");
  let gateStatus = "ready";
  let gateTitle = "מוכן לדיון צוות";
  let gateText = "לא זוהו חסמי חוק או מידע ב־5 ההחלטות הקריטיות.";
  if (!actualCoverage.data_as_of) {
    gateStatus = "blocked";
    gateTitle = "חסום — אין Actual מאושר";
    gateText = "העלו ואשרו דוחות רבעוניים לפני הסתמכות על המלצות.";
  } else if (num(reviewSummary.blocked_count) > 0) {
    gateStatus = "blocked";
    gateTitle = "חסום — נדרש תיקון";
    gateText = `${fmt(reviewSummary.blocked_count)} פעולות מפרות חוק או מגבלה.`;
  } else if (num(reviewSummary.missing_data_count) > 0) {
    gateStatus = "conditional";
    gateTitle = "מותנה — חסר מידע";
    gateText = `${fmt(reviewSummary.missing_data_count)} פעולות ממתינות לנתון מאושר.`;
  }
  gate.className = `decision-gate ${gateStatus}`;
  gate.innerHTML = `<div><span>DECISION GATE</span><strong>${esc(gateTitle)}</strong><p>${esc(gateText)}</p></div>${
    blockingActions.length
      ? `<details><summary>הצגת ${fmt(blockingActions.length)} תיקונים ראשונים</summary><ol>${blockingActions.map(row => `<li><bdi dir="ltr">${esc(row.code || "")}</bdi> · ${esc(row.title || row.name || "")}: ${esc(row.gate || row.reason || "נדרש להשלים מידע או לתקן את הפעולה.")}</li>`).join("")}</ol></details>`
      : ""
  }`;
  const evidence = data?.evidence_gate || {};
  const evidenceElement = $("#evidenceGateSummary");
  const evidenceStatus = evidence.status || "unknown";
  const evidenceClass = evidenceStatus === "pass" ? "ready" : evidenceStatus;
  const evidenceTitle = {
    pass: "המספרים ניתנים לשחזור",
    conditional: "יש לאשר הנחות לפני הזנה",
    blocked: "אין להשתמש במספרים המוצעים",
  }[evidenceStatus] || "שער הראיות ממתין לנתונים";
  const evidenceGaps = [...(evidence.contradictions || []), ...(evidence.gaps || [])].slice(0, 5);
  evidenceElement.className = `evidence-gate-summary ${evidenceClass}`;
  evidenceElement.innerHTML = `<div><span>NUMBER EVIDENCE GATE</span><strong>${esc(evidenceTitle)}</strong><p>${esc(evidence.summary || "כל מספר יעבור בדיקת מקור, נוסחה, טווח וודאות.")}</p></div>
    <div class="evidence-gate-counts">
      <span><b>${fmt(evidence.passed_count || 0)}</b> מאושר</span>
      <span><b>${fmt(evidence.conditional_count || 0)}</b> מותנה</span>
      <span><b>${fmt(evidence.blocked_count || 0)}</b> חסום</span>
      <span><b>${fmt(evidence.score == null ? 0 : evidence.score)}</b> ציון ראיות</span>
    </div>
    ${evidenceGaps.length ? `<details><summary>מה חסר כדי לשחרר מספרים?</summary><ul>${evidenceGaps.map(item => `<li>${esc(item)}</li>`).join("")}</ul></details>` : ""}`;
  $("#scenarioBudgetLabel").textContent = `תקציב ${sf(financial.available_budget_sf)}`;
}

const DECISION_CATEGORY_ORDER = [
  {key: "strategy", label: "החלטות אסטרטגיות", labelEn: "STRATEGIC DECISIONS"},
  {key: "finance", label: "מימון", labelEn: "FINANCIAL"},
  {key: "operations", label: "ייצור ותפעול", labelEn: "OPERATION & PRODUCTION"},
  {key: "marketing", label: "שיווק", labelEn: "MARKETING"},
];

function actionStatusIcon(status) {
  return {
    recommended: "✓",
    required: "!",
    blocked: "×",
    missing_data: "?",
    monitor: "◉",
    not_required: "—",
  }[status] || "•";
}

function renderActionReview() {
  const review = state.intelligence?.action_review || {};
  const summary = review.summary || {};
  const categories = review.categories || [];
  const empty = $("#actionReviewEmpty");
  $("#actionReviewHeadline").textContent = summary.headline || "ממתין לנתונים מאושרים לצורך בדיקת כל הפעולות.";
  $("#actionReviewCounts").innerHTML = [
    ["coverage", "כיסוי", summary.coverage_pct == null ? "—" : `${fmt(summary.coverage_pct)}%`],
    ["recommended", "מומלץ", summary.recommended_count || 0],
    ["required", "נדרש", summary.required_count || 0],
    ["blocked", "חסום", summary.blocked_count || 0],
    ["missing_data", "חסר מידע", summary.missing_data_count || 0],
  ].map(([status, label, value]) => `<span class="action-review-count ${status}"><b>${value}</b>${label}</span>`).join("");
  empty.classList.toggle("hidden", categories.length > 0);
  $("#actionReviewCategories").innerHTML = categories.map(category => {
    const actions = category.actions || [];
    const counts = category.counts || {};
    return `<section class="decision-category category-${esc(category.key)}">
      <header class="decision-category-head">
        <div><span>${esc(category.label_en || "")}</span><h3>${esc(category.label)}</h3></div>
        <b>${fmt(actions.length)}</b>
      </header>
      <div class="decision-category-summary">
        <span class="recommended">${fmt(counts.recommended || 0)} מומלצות</span>
        <span class="required">${fmt(counts.required || 0)} מחזוריות</span>
        <span class="attention">${fmt((counts.blocked || 0) + (counts.missing_data || 0))} דורשות טיפול</span>
      </div>
      <div class="decision-action-cards">${actions.map(action => {
        const research = action.research_used || [];
        const rules = action.rules_checked || [];
        const recommended = action.status === "recommended";
        return `<details class="decision-action-card ${esc(action.status)}" ${recommended ? "open" : ""}>
          <summary>
            <span class="action-status-icon" aria-hidden="true">${actionStatusIcon(action.status)}</span>
            <span class="action-card-copy"><bdi class="action-code" dir="ltr">${esc(action.code)}</bdi><strong>${esc(action.title)}</strong></span>
            <span class="action-status-label">${esc(action.status_label)}</span>
          </summary>
          <div class="action-card-detail">
            <div><b>מצב קיים</b><p>${esc(action.current_state || "—")}</p></div>
            <div><b>מסקנת הבדיקה</b><p>${esc(action.reason || "—")}</p></div>
            <div><b>הפעולה הבאה</b><p>${esc(action.next_step || "—")}</p></div>
            <div class="action-evidence-row">
              <span><b>חוקים</b> ${fmt(rules.length)}</span>
              <span><b>מחקרים רלוונטיים</b> ${fmt(research.length)}</span>
              <span><b>Rulebook</b> <bdi dir="ltr">${esc(action.rulebook_version || "—")}</bdi></span>
            </div>
            ${research.length ? `<div class="action-research-evidence">${research.map(item => `<span title="${esc(item.headline || "")}"><bdi dir="ltr">MR${esc(item.study_id)}</bdi> · ${esc(item.source_label || "")}</span>`).join("")}</div>` : '<small class="no-evidence">לא נמצא מחקר מאושר שמשנה החלטה זו.</small>'}
            <p class="action-timing"><b>תזמון:</b> ${esc(action.timing || "—")}</p>
          </div>
        </details>`;
      }).join("")}</div>
    </section>`;
  }).join("");
}

function renderExecutionBlueprint() {
  const blueprint = state.intelligence?.execution_blueprint || {};
  const rows = blueprint.rows || [];
  const summary = blueprint.summary || {};
  const empty = $("#executionBlueprintEmpty");
  const table = $(".execution-table-wrap");
  $("#executionBlueprintHeadline").textContent = summary.headline || "לא זוהו עדיין מספיק נתונים ליצירת תכנית מספרית.";
  $("#executionBlueprintCounts").innerHTML = [
    ["ready", "מוכן", summary.ready_count || 0],
    ["conditional", "מותנה", summary.conditional_count || 0],
    ["blocked", "חסום", summary.blocked_count || 0],
  ].map(([level, label, value]) => `<span class="execution-count ${level}"><b>${fmt(value)}</b>${label}</span>`).join("");
  empty.classList.toggle("hidden", rows.length > 0);
  table.classList.toggle("hidden", rows.length === 0);
  $("#executionBlueprintRows").innerHTML = rows.map((row, index) => {
    const dependencies = row.dependencies || [];
    const coordinates = row.coordinates_with || [];
    const unlocks = row.unlocks || [];
    const dependencyHtml = dependencies.length
      ? dependencies.map(item => `<span class="dependency-chip ${item.hard ? "hard" : ""}">תלוי בשלב ${fmt(item.step || "—")}: ${esc(item.title)}</span>`).join("")
      : '<span class="dependency-chip clear">ללא תנאי מוקדם</span>';
    const coordinationHtml = coordinates.length
      ? `<small>לתאם עם: ${coordinates.map(item => `שלב ${fmt(item.step || "—")} ${esc(item.title)}`).join(" · ")}</small>`
      : "";
    const unlocksHtml = unlocks.length
      ? `<small class="unlocks">פותח: ${unlocks.map(item => `שלב ${fmt(item.step || "—")} ${esc(item.title)}`).join(" · ")}</small>`
      : "";
    const canSimulate = row.action && !["strategy_review", "cash_protection"].includes(row.action_type);
    return `<tr class="execution-row ${esc(row.status || "conditional")}">
      <td><span class="execution-order">${fmt(row.order || index + 1)}</span><small>${esc(row.phase || "")}</small></td>
      <td><strong class="execution-route"><span>${esc(row.area || "—")}</span>${row.target_area ? `<span class="route-arrow" aria-label="אל">←</span><span>${esc(row.target_area)}</span>` : ""}</strong><bdi class="form-code" dir="ltr">${esc(row.form_code || "—")}</bdi></td>
      <td><strong>${esc(row.field_name || row.action_name || "—")}</strong><small>${esc(row.action_name || "")}</small></td>
      <td><b class="execution-value">${esc(row.recommended_value || "נדרש אישור")}</b><span class="execution-status ${esc(row.status || "conditional")}">${esc(row.status_label || "")} · ${esc(row.decision_type || "")}</span></td>
      <td><div class="dependency-stack">${dependencyHtml}${coordinationHtml}${unlocksHtml}</div><p>${esc(row.gate || "")}</p></td>
      <td><p>${esc(row.expected_outcome || "")}</p><small>${esc(row.input_instruction || "")}</small></td>
      <td><small>${esc(row.source || "")}</small><span class="confidence-label">ודאות ${esc(row.confidence || "בינונית")}</span></td>
      <td>${canSimulate ? `<button class="button secondary compact-button" type="button" data-add-blueprint="${index}">לסימולציה</button>` : ""}</td>
    </tr>`;
  }).join("");
}

function renderRecommendations() {
  renderActionReview();
  renderExecutionBlueprint();
  const rows = state.intelligence?.recommendations || [];
  const actualCoverage = state.intelligence?.financial?.actual_coverage || {};
  if (!actualCoverage.data_as_of) {
    $("#decisionDependencySummary").innerHTML = "";
    $("#recommendationsList").innerHTML = `
      <section class="decision-data-gate" role="status">
        <span class="panel-kicker">DATA GATE</span>
        <h3>אין עדיין בסיס מאושר להמלצות</h3>
        <p>כדי למנוע המלצות שווא על אפסים או נתוני דמו, המערכת לא תציע פעולות לפני אישור דוח Actual אחד לפחות.</p>
        <ol>
          <li>העלו את דוחות Q1, Q2 ו־Q3 בצ'אט AI או במסך הקבצים.</li>
          <li>עברו על תצוגת החילוץ ואשרו כל רבעון.</li>
          <li>חזרו לחדר ההחלטות לקבלת המלצות מספריות, תלויות ותחזית Q9.</li>
        </ol>
        <button class="button primary" type="button" data-go-to-files>להעלאת דוחות</button>
      </section>`;
    return;
  }
  const review = state.intelligence?.action_review || {};
  const graph = state.intelligence?.decision_dependencies || {};
  const sequence = graph.recommended_sequence || [];
  const graphSummary = graph.summary || {};
  const budget = graph.budget_coordination || {};
  $("#decisionDependencySummary").innerHTML = rows.length ? `
    <div class="dependency-summary-head">
      <div><span class="panel-kicker">INTEGRATED MOVE</span><strong>מהלך החלטות מתואם</strong></div>
      <span class="soft-pill">${fmt(graphSummary.dependency_count || 0)} תלויות</span>
    </div>
    <p>${esc(graphSummary.message || "הפעולות נבדקות יחד מול התקציב, התזמון ויעד Q9.")}</p>
    <div class="dependency-sequence" dir="rtl">${sequence.map(item => `<span><b>${fmt(item.step)}</b>${esc(item.title)}</span>`).join("")}</div>
    <small>עלות משולבת ${sf(budget.planned_cost_sf)} · תקציב אפקטיבי ${sf(budget.effective_budget_sf)} · יתרה ${sf(budget.remaining_after_plan_sf)}</small>
  ` : "";
  const reviewedActions = review.actions || [];
  const recommendationCategory = row => {
    const linked = reviewedActions.find(action => (action.recommendation_ids || []).includes(row.id));
    if (linked) return linked.category;
    const domain = String(row.domain || "");
    if (["מימון", "פיננסים"].includes(domain)) return "finance";
    if (["ייצור", "תפעול"].some(token => domain.includes(token))) return "operations";
    if (["תמחור", "שיווק"].some(token => domain.includes(token))) return "marketing";
    return "strategy";
  };
  const ownerForRecommendation = row => {
    const category = recommendationCategory(row);
    return {finance: "CFO", operations: "COO", marketing: "CMO", strategy: "CEO"}[category] || "הנהלה";
  };
  const recommendationCard = (row, index) => {
    const impact = row.economic_impact || {};
    const ai = row.ai_recommendation || {};
    const dependencies = row.dependencies || {};
    const numberGate = row.number_gate || {};
    const numberGateStatus = numberGate.status || "blocked";
    const numberGateLabel = {pass: "מספרים מאושרים", conditional: "מספרים מותנים", blocked: "מספרים חסומים"}[numberGateStatus] || "לא נבדק";
    const displayEvidenceValue = claim => {
      const value = Array.isArray(claim.value) ? claim.value.map(item => `MR${item}`).join(", ") : claim.value;
      if (value == null || value === "") return "—";
      return typeof value === "number" ? `${fmt(value)} ${claim.unit || ""}`.trim() : `${value} ${claim.unit || ""}`.trim();
    };
    const displayRange = claim => {
      const range = claim.range || {};
      if (range.low == null || range.base == null || range.high == null || typeof range.base !== "number") return "—";
      return `${fmt(range.low)} / ${fmt(range.base)} / ${fmt(range.high)} ${claim.unit || ""}`.trim();
    };
    const evidenceClaims = numberGate.claims || [];
    const blueprintRows = (state.intelligence?.execution_blueprint?.rows || [])
      .filter(item => item.recommendation_id === row.id);
    const aiProposal = blueprintRows.length
      ? blueprintRows.slice(0, 3).map(item => `${item.form_code || "טופס"} · ${item.field_name || item.action_name}: ${item.recommended_value || "מותנה"}`).join(" | ")
      : (ai.verdict || "נדרש ניתוח נוסף");
    const teamDecision = (state.decisions || []).find(item =>
      item.quarter === state.quarter && String(item.title || "").trim() === String(row.title || "").trim()
    );
    const teamProposal = teamDecision?.selected_option || "טרם הוגדרה הצעת צוות";
    const decisionStatus = teamDecision?.status || "ממתין לדיון";
    const owner = teamDecision?.owner || ownerForRecommendation(row);
    const dependencyItems = [
      ...(dependencies.prerequisites || []).map(item => `<li><b>תנאי מקדים:</b> ${esc(item.title)} — ${esc(item.reason)}</li>`),
      ...(dependencies.coordinates_with || []).map(item => `<li><b>לקבוע יחד עם:</b> ${esc(item.title)} — ${esc(item.reason)}</li>`),
      ...(dependencies.enables || []).map(item => `<li><b>פותח אפשרות ל:</b> ${esc(item.title)} — ${esc(item.reason)}</li>`),
      ...(dependencies.gaps || []).map(item => `<li class="dependency-warning"><b>חסר:</b> ${esc(item.missing)} — ${esc(item.reason)}</li>`),
      ...(dependencies.conflicts || []).map(item => `<li class="dependency-warning"><b>התנגשות:</b> ${esc(item.reason)}</li>`),
    ];
    return `<article class="recommendation" dir="rtl">
      <span class="priority">${index + 1}</span>
      <div class="recommendation-main">
        <div class="recommendation-meta"><span class="soft-pill">${esc(row.domain)}</span><span class="risk-label">סיכון ${esc(row.risk || "—")}</span><span class="health-badge ${esc(ai.level || "unknown")}">${esc(ai.verdict || "ממתין לניתוח")}</span><span class="number-gate-badge ${esc(numberGateStatus)}">${esc(numberGateLabel)}</span></div>
        <strong>${esc(row.title)}</strong>
        <small>${esc(row.rationale)}</small>
        <div class="impact-horizon"><span>טווח קצר · הרבעון הקרוב</span><span>טווח ארוך · עד Q9</span></div>
        <div class="impact-grid">
          <div><span>עלות</span><strong>${sf(impact.cost_sf)}</strong></div>
          <div><span>שינוי רווח</span><strong class="${num(impact.profit_delta_sf) < 0 ? "negative" : "positive"}">${signedSf(impact.profit_delta_sf)}</strong></div>
          <div><span>שינוי מזומן</span><strong class="${num(impact.cash_delta_sf) < 0 ? "negative" : "positive"}">${signedSf(impact.cash_delta_sf)}</strong></div>
          <div><span>שינוי אומדן Q9</span><strong class="${num(impact.q9_score_delta) < 0 ? "negative" : "positive"}">${signedScore(impact.q9_score_delta)}</strong></div>
        </div>
        <p class="ai-explanation"><b>המלצת AI/מערכת:</b> ${esc(ai.explanation || "נדרשים נתונים נוספים.")} <span>ודאות ${esc(ai.confidence || "נמוכה")}</span></p>
        <details class="number-evidence ${esc(numberGateStatus)}">
          <summary>איך הגענו למספרים? · ${fmt(evidenceClaims.length)} טענות מספריות</summary>
          <div class="number-evidence-body">
            <p class="number-evidence-summary">${esc(numberGate.summary || "המספרים טרם עברו ביקורת ראיות.")}</p>
            ${numberGate.contradictions?.length ? `<div class="evidence-alert critical"><b>סתירות:</b><ul>${numberGate.contradictions.map(item => `<li>${esc(item)}</li>`).join("")}</ul></div>` : ""}
            ${numberGate.gaps?.length ? `<div class="evidence-alert warning"><b>מידע חסר:</b><ul>${numberGate.gaps.map(item => `<li>${esc(item)}</li>`).join("")}</ul></div>` : ""}
            <div class="number-claim-list">${evidenceClaims.map(claim => `<article class="number-claim ${esc(claim.status || "blocked")}">
              <header><strong>${esc(claim.label || claim.metric)}</strong><span>${esc(displayEvidenceValue(claim))}</span><b>${esc(claim.status === "supported" ? "מאושר" : claim.status === "conditional" ? "מותנה" : "חסום")}</b></header>
              <p><b>סוג:</b> ${esc(claim.claim_type || "—")} · <b>ודאות:</b> ${esc(claim.confidence || "low")}</p>
              <p><b>נוסחה:</b> ${esc(claim.formula || "אין נוסחה — נתון ישיר")}</p>
              <p><b>טווח נמוך / בסיס / גבוה:</b> ${esc(displayRange(claim))}</p>
              <p><b>מקור:</b> ${(claim.source_refs || []).length ? claim.source_refs.map(source => `<span class="evidence-source">${esc(source.label || source.id)}</span>`).join(" ") : '<span class="evidence-source missing">לא קיים מקור מאושר</span>'}</p>
            </article>`).join("")}</div>
          </div>
        </details>
        <div class="team-ai-compare">
          <div class="ai-proposal"><span>הצעת AI המספרית</span><strong>${esc(aiProposal)}</strong></div>
          <div class="team-proposal">
            <span>החלטת הצוות</span>
            <input type="text" value="${esc(teamProposal)}" data-team-proposal="${index}" aria-label="החלטת הצוות עבור ${esc(row.title)}">
            <div class="inline-decision-actions">
              <button class="button compact-button primary" type="button" data-adopt-recommendation="${index}" ${numberGateStatus === "blocked" ? "disabled title=\"המספר חסום עד השלמת ראיות\"" : ""}>אימוץ הצעת AI</button>
              <button class="button compact-button secondary" type="button" data-save-team-recommendation="${index}">שמירת טיוטה</button>
            </div>
          </div>
        </div>
        <div class="decision-governance">
          <span><b>Owner</b> ${esc(owner)}</span>
          <span><b>סטטוס</b> ${esc(decisionStatus)}</span>
          <span><b>ודאות</b> ${esc(ai.confidence || "נמוכה")}</span>
        </div>
        <div class="dependency-note">
          <div><b>שלב ${fmt(dependencies.sequence_step || index + 1)} במהלך הכולל</b><span>${dependencyItems.length ? `${dependencyItems.length} קשרים שדורשים תיאום` : "אין תלות מחייבת שזוהתה"}</span></div>
          ${dependencyItems.length ? `<ul>${dependencyItems.join("")}</ul>` : ""}
        </div>
        <small class="strategy-note">${esc(row.strategy_alignment || "")}</small>
      </div>
      <div class="recommendation-actions">
        <button class="button secondary" type="button" data-simulate-recommendation="${index}">סמלץ</button>
        <button class="text-link" type="button" data-ask-recommendation="${index}">שאל AI</button>
        <button class="text-link" type="button" data-log-recommendation="${index}">שמור כהחלטה</button>
      </div>
    </article>`;
  };
  const indexedRows = rows.map((row, index) => ({row, index}));
  const rankedCategories = DECISION_CATEGORY_ORDER.map(category => {
    const matches = indexedRows.filter(item => recommendationCategory(item.row) === category.key);
    return {...category, matches, firstPriority: matches[0]?.index ?? Number.MAX_SAFE_INTEGER};
  }).filter(category => category.matches.length).sort((a, b) => a.firstPriority - b.firstPriority);
  $("#recommendationsList").innerHTML = rows.length ? rankedCategories.map(category => {
    const matches = category.matches;
    return `<section class="recommendation-category-group category-${category.key}">
      <header><div><span>${esc(category.labelEn)}</span><h3>${esc(category.label)}</h3></div><b>${fmt(matches.length)}</b></header>
      <div class="recommendation-list">${matches.map(item => recommendationCard(item.row, item.index)).join("")}</div>
    </section>`;
  }).join("") : '<div class="empty-copy">אין עדיין מספיק נתונים ליצירת המלצות.</div>';
}

function areaOptions() {
  const areas = state.intelligence?.financial?.areas || [];
  return ["חברה מאוחדת", ...areas.map(row => row.area)];
}

function financeView(name, intelligence = state.intelligence) {
  const data = intelligence?.financial;
  if (!data) return {};
  if (name === "חברה מאוחדת") return {...(data.consolidated || {}), health: data.health || data.consolidated?.health};
  return data.areas?.find(row => row.area === name) || {};
}

function quarterNumber(value) {
  const match = String(value || "").match(/^Q(\d+)$/);
  return match ? Number(match[1]) : 0;
}

function areaHistoryRow(row) {
  const fx = num(row.fx_to_sf) || 1;
  return {
    quarter: row.quarter,
    revenue_sf: num(row.revenue_lc) * fx,
    gross_profit_sf: num(row.gross_profit_lc) * fx,
    net_profit_sf: num(row.net_profit_lc) * fx,
    ending_cash_sf: num(row.ending_cash_lc) * fx,
    debt_sf: num(row.debt_lc) * fx,
  };
}

function financeRangeRows(selected) {
  const range = state.financeRange;
  if (!range) return [];
  const from = quarterNumber($("#financeFromSelect").value || "Q1");
  const to = quarterNumber($("#financeToSelect").value || state.quarter);
  const source = selected === "חברה מאוחדת"
    ? (range.report?.finance_history || [])
    : (range.report?.area_finance_history || []).filter(row => row.area === selected).map(areaHistoryRow);
  return source.filter(row => {
    const q = quarterNumber(row.quarter);
    return q >= from && q <= to;
  }).sort((a, b) => quarterNumber(a.quarter) - quarterNumber(b.quarter));
}

function financeRangeView(selected) {
  const range = state.financeRange;
  if (!range) return null;
  const current = financeView(selected, range.intelligence);
  if ($("#financeModeSelect").value !== "cumulative") return current;
  const rows = financeRangeRows(selected);
  if (!rows.length) return current;
  const revenue = rows.reduce((sum, row) => sum + num(row.revenue_sf), 0);
  const gross = rows.reduce((sum, row) => sum + num(row.gross_profit_sf), 0);
  const profit = rows.reduce((sum, row) => sum + num(row.net_profit_sf), 0);
  return {
    ...current,
    revenue_sf: revenue,
    gross_profit_sf: gross,
    net_profit_sf: profit,
    health: current.health,
    _range_ratios: {
      gross_margin: revenue ? gross / revenue : null,
      net_margin: revenue ? profit / revenue : null,
    },
  };
}

function renderHealthBadge(element, health) {
  if (!element) return;
  element.className = `health-badge ${health?.level || "unknown"}`;
  element.textContent = health?.score == null ? (health?.status || "אין מספיק נתונים") : `${health.status} · ${fmt(health.score)}/100`;
}

function renderDashboardFinance() {
  const selected = $("#dashboardAreaSelect").value || "חברה מאוחדת";
  const row = financeView(selected);
  renderHealthBadge($("#dashboardHealthBadge"), row.health);
  $("#dashboardHealthHeadline").textContent = row.health?.headline || "יש לאשר נתונים כספיים לצורך אבחון.";
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
  $("#dashboardResearch").innerHTML = rows.length ? rows.slice(0, 3).map(row => `<div class="compact-row research-dashboard-row"><div><strong>${esc(row.title)}</strong><small>${esc(row.headline || row.key_result || "ללא סיכום מאושר")}</small><p>${esc(row.recommendation || "")}</p></div><span class="soft-pill">${esc(row.confidence)}</span></div>`).join("") : '<div class="empty-copy">לא נקלטו מחקרי שוק מאושרים.</div>';
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
  refreshFieldAdvice();
  const readiness = await api(`/api/dashboard/${state.quarter}`);
  renderDynamicQuarterContext(readiness);
}

function renderStrategyOptimization() {
  const data = state.strategyOptimization || {};
  const position = data.current_position || {};
  const source = data.source_strategy || {};
  const emphasis = data.recommended_emphasis || {};
  const plan = data.recommended_plan || {};
  const scenarios = data.scenarios || [];
  const recommended = scenarios.find(item => item.key === "recommended") || {};
  const statusLabels = {
    ready: ["ok", "התכנית מוכנה לדיון"],
    needs_data: ["error", "נדרש Actual מאושר"],
    needs_strategy: ["error", "נדרשת אסטרטגיה מאושרת"],
    blocked: ["error", "התכנית חסומה עד לתיקון"],
  };
  const [statusClass, statusText] = statusLabels[data.status] || ["", "מחשב תכנית…"];
  const statusElement = $("#strategyOptimizationStatus");
  statusElement.className = `status-chip ${statusClass}`;
  statusElement.textContent = statusText;

  $("#strategyActualAsOf").textContent = data.actual_as_of || "—";
  $("#strategyHorizon").textContent = data.horizon?.length ? `${data.horizon[0]}–Q9` : "—";
  $("#strategyCurrentScore").textContent = score(position.combined_score);
  $("#strategyOptimizedScore").textContent = score(recommended.q9_score?.base);
  $("#strategyScoreUplift").textContent = recommended.q9_score_uplift == null
    ? "אין מספיק נתונים לחישוב שינוי"
    : `שינוי צפוי ${signedScore(recommended.q9_score_uplift)}`;

  const notice = $("#strategyOptimizationNotice");
  if (data.status === "ready") {
    notice.classList.add("hidden");
    notice.innerHTML = "";
  } else {
    notice.classList.remove("hidden");
    const messages = {
      needs_data: "יש להעלות ולאשר לפחות פלט רבעוני אחד. האופטימיזציה תתחיל אוטומטית מהרבעון הבא.",
      needs_strategy: "נתוני הרבעון קיימים, אך לא אושרה אסטרטגיה ראשונית. העלו ואשרו אותה במרכז הקבצים.",
      blocked: "אחת הפעולות המוצעות מפרה מגבלת תקציב, תזמון או חוק. התנאים לתיקון מפורטים למטה.",
    };
    notice.innerHTML = `<strong>לא ניתן לאשר את הטיוטה עדיין:</strong> ${esc(messages[data.status] || "חסרים נתונים.")}`;
  }

  const goals = source.goals || [];
  const constraints = source.constraints || [];
  const priorities = source.priorities || [];
  $("#strategyOriginal").innerHTML = `
    <p class="strategy-thesis">${esc(source.thesis || "לא קיימת תזה מאושרת.")}</p>
    <div class="strategy-list-group"><strong>יעדי Q9</strong>${goals.length ? `<ul>${goals.map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : '<small>לא נקלטו יעדים מאושרים.</small>'}</div>
    <div class="strategy-list-group"><strong>עדיפויות</strong>${priorities.length ? `<ul>${priorities.map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : '<small>לא נקלטו עדיפויות.</small>'}</div>
    <div class="strategy-list-group"><strong>קווים אדומים</strong>${constraints.length ? `<ul>${constraints.map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : '<small>לא נקלטו קווים אדומים.</small>'}</div>
  `;

  const sequence = plan.sequence || [];
  const bottlenecks = emphasis.bottlenecks || [];
  $("#strategyRecommended").innerHTML = `
    <div class="strategy-emphasis"><span>מוקד האופטימיזציה</span><strong>${esc(emphasis.title || "ממתין לנתונים")}</strong><p>${esc(emphasis.reason || "")}</p></div>
    <div class="bottleneck-list">${bottlenecks.map(item => `<span>${esc(item.metric)} <b>${score(item.score)}</b></span>`).join("")}</div>
    <div class="strategy-list-group"><strong>סדר הפעולות המומלץ</strong>${sequence.length ? `<ol>${sequence.map(item => `<li><b>${esc(item.action?.title || item.action?.type || "פעולה")}</b><small>${sf(item.cost_sf)} · ${esc(item.timing || "")}</small></li>`).join("")}</ol>` : '<small>אין עדיין פעולה מספרית שניתן להמליץ עליה בביטחון. יש להשלים את תנאי המעבר.</small>'}</div>
  `;

  $("#strategyScenarioGrid").innerHTML = scenarios.length ? scenarios.map(item => {
    const range = item.q9_score || {};
    const budget = item.budget || {};
    const actionCount = (item.actions || []).length;
    return `<article class="strategy-scenario ${item.recommended ? "selected" : ""} ${item.feasible ? "" : "blocked"}">
      <div class="scenario-title"><div><span>${item.recommended ? "המלצת המערכת" : "חלופה"}</span><h3>${esc(item.label)}</h3></div><span class="health-badge ${item.feasible ? "good" : "critical"}">${item.feasible ? "אפשרי" : "חסום"}</span></div>
      <p>${esc(item.description)}</p>
      <div class="scenario-score"><span>אומדן Q9</span><strong>${score(range.base)}</strong><small>טווח ${score(range.low)}–${score(range.high)}</small></div>
      <div class="scenario-metrics"><span>שינוי בציון <b>${signedScore(item.q9_score_uplift)}</b></span><span>פעולות <b>${fmt(actionCount)}</b></span><span>עלות <b>${sf(budget.planned_cost_sf || 0)}</b></span><span>יתרה <b>${sf(budget.remaining_sf)}</b></span></div>
      ${item.violations?.length ? `<div class="scenario-violation">${esc(item.violations[0])}</div>` : ""}
    </article>`;
  }).join("") : '<div class="empty-copy">אין מספיק נתונים להשוואת חלופות.</div>';

  const optimizer = data.integrated_optimization || {};
  const winner = optimizer.winner || null;
  const robustness = $("#q9OptimizerRobustness");
  robustness.className = `status-chip ${winner ? (optimizer.robust_to_weight_sensitivity ? "ok" : "") : "error"}`;
  robustness.textContent = !winner ? "אין סל אפשרי" : optimizer.robust_to_weight_sensitivity ? "יציב לשינוי משקלים" : "רגיש למשקלי הציון";
  $("#q9OptimizerSummary").innerHTML = winner ? [
    `<div><span>חלופות שנבדקו</span><strong>${fmt(optimizer.evaluated_portfolios)}</strong><small>${fmt(optimizer.feasible_portfolios)} אפשריות</small></div>`,
    `<div><span>אומדן Q9</span><strong>${score(winner.q9_score?.base)}</strong><small>${score(winner.q9_score?.low)}–${score(winner.q9_score?.high)}</small></div>`,
    `<div><span>עלות הסל</span><strong>${sf(winner.budget?.planned_cost_sf || 0)}</strong><small>יתרה ${sf(winner.budget?.remaining_sf)}</small></div>`,
    `<div><span>פעולות</span><strong>${fmt(winner.action_count)}</strong><small>נבחרו יחד, לא בנפרד</small></div>`,
  ].join("") : '<div class="empty-copy">לא נמצא סל שעומד יחד בחוקי המשחק, בתקציב, ברצפת המזומן ובתלויות.</div>';
  const orderedActions = winner?.sequence?.length
    ? winner.sequence
    : (winner?.actions || []).map((action, index) => ({step: index + 1, action, depends_on: []}));
  $("#q9OptimizerActions").innerHTML = orderedActions.length ? orderedActions.map(item => {
    const action = item.action || item;
    const dependencies = item.depends_on || action.depends_on || [];
    return `<div class="strategy-gate good"><span>${fmt(item.step || 1)}</span><div><strong>${esc(action.title || action.code || action.type || "פעולה")}</strong><p>${sf(action.cost_sf || item.cost_sf || 0)}${dependencies.length ? ` · תלוי ב־${esc(dependencies.join(", "))}` : " · ללא קדם־תנאי פתוח"}</p></div></div>`;
  }).join("") : '<div class="empty-copy">הסל המיטבי כרגע הוא להימנע מפעולה חדשה עד השלמת ראיות או תקציב.</div>';
  $("#q9OptimizerSensitivity").innerHTML = (optimizer.weight_sensitivity || []).map(item => {
    const same = winner && item.winner_id === winner.id;
    return `<div class="compact-row"><div><strong>${fmt(item.past_weight * 100)}% כסף / ${fmt(item.future_weight * 100)}% פוטנציאל</strong><small>${same ? "אותו סל נשאר ראשון" : "הסל המוביל משתנה"}</small></div><span class="health-badge ${same ? "good" : "watch"}">${same ? "יציב" : "רגיש"}</span></div>`;
  }).join("") || '<div class="empty-copy">אין מספיק חלופות אפשריות לניתוח רגישות.</div>';

  $("#strategyDeltas").innerHTML = (data.strategy_deltas || []).length ? data.strategy_deltas.map(item => `
    <div class="strategy-delta">
      <strong>${esc(item.dimension)}</strong>
      <div><span>מקור</span><p>${esc(item.original)}</p></div>
      <div class="delta-recommended"><span>מומלץ</span><p>${esc(item.recommended)}</p></div>
      <small>${esc(item.reason)}</small>
    </div>
  `).join("") : '<div class="empty-copy">אין עדיין בסיס להשוואה.</div>';

  $("#strategyGates").innerHTML = (plan.decision_gates || []).length ? plan.decision_gates.map(item => `
    <div class="strategy-gate ${esc(item.level || "warning")}"><span></span><div><strong>${esc(item.title)}</strong><p>${esc(item.reason)}</p></div></div>
  `).join("") : '<div class="strategy-gate good"><span></span><div><strong>לא זוהה חסם מהותי</strong><p>עדיין יש לאשר את הפעולות כצוות לפני יצירת חבילת החלטות.</p></div></div>';

  $("#strategyRoadmap").innerHTML = (plan.roadmap || []).length ? plan.roadmap.map(item => `
    <article class="roadmap-quarter ${item.quarter === data.next_decision_quarter ? "active" : ""}">
      <div class="roadmap-head"><strong>${esc(item.quarter)}</strong><span>${esc(item.theme)}</span></div>
      <div class="roadmap-actions">${item.actions?.length ? item.actions.map(action => `<div><b>${fmt(action.step)}</b><span>${esc(action.title)}</span><small>${sf(action.cost_sf)}</small></div>`).join("") : '<small>פעולות ייקבעו לאחר קבלת ה־Actual הקודם.</small>'}</div>
      <p>${esc(item.gate)}</p>
      <small>${esc(item.review)}</small>
    </article>
  `).join("") : '<div class="empty-copy">אין אופק זמין עד אישור נתוני הרבעון.</div>';

  const evidence = data.evidence || {};
  const evidenceRows = [
    ...(evidence.score_sources || []).map(item => ["נתוני ציון", item]),
    ...(evidence.financial_sources || []).map(item => ["נתונים כספיים", item]),
    ...(evidence.research_results || []).map(item => ["מחקר שוק", item.title || item.key_result]),
  ];
  $("#strategyEvidence").innerHTML = evidenceRows.length ? evidenceRows.slice(0, 12).map(([kind, text]) => `<div class="compact-row"><div><strong>${esc(kind)}</strong><small>${esc(text)}</small></div></div>`).join("") : '<div class="empty-copy">לא קיימות עדיין ראיות מאושרות.</div>';
  $("#strategyLimits").innerHTML = (data.model_limits || []).map(item => `<div class="compact-row"><div><strong>✓</strong><small>${esc(item)}</small></div></div>`).join("");
}

async function loadStrategyOptimization() {
  state.strategyOptimization = await api(`/api/strategy-optimization/${encodeURIComponent(state.quarter)}`);
  renderStrategyOptimization();
}

function renderFinancePage() {
  const selected = $("#financeAreaSelect").value || "חברה מאוחדת";
  const row = financeRangeView(selected) || financeView(selected);
  const health = row.health || {};
  const ratios = {...(health.ratios || {}), ...(row._range_ratios || {})};
  const financial = state.financeRange?.intelligence?.financial || state.intelligence?.financial || {};
  const coverage = financial.actual_coverage || {};
  const statusElement = $("#financeDataStatus");
  statusElement.className = `data-status-card ${coverage.level || "critical"}`;
  statusElement.textContent = coverage.message || "לא אושר עדיין דוח Actual. אין להסתמך על המסך לקבלת החלטות.";
  renderHealthBadge($("#financeHealthBadge"), health);
  $("#financeHealthHeadline").textContent = health.headline || "יש לאשר נתונים כספיים לצורך אבחון.";
  $("#financeHealthChecks").innerHTML = (health.checks || []).length ? health.checks.map(item => `<div class="health-check ${esc(item.level)}"><span class="health-dot"></span><div><strong>${esc(item.label)}</strong><small>${esc(item.explanation)}</small></div><b>${esc(item.value)}</b></div>`).join("") : '<div class="empty-copy">לא קיימים מספיק נתונים לבדיקת נזילות, רווחיות ומינוף.</div>';
  $("#financeKpis").innerHTML = [
    kpi("הכנסות", sf(row.revenue_sf), selected), kpi("רווח נקי", sf(row.net_profit_sf), selected),
    kpi("מזומן", sf(row.ending_cash_sf), selected), kpi("תקציב פנוי", sf(row.available_budget_sf), "לאחר התחייבויות"),
    kpi("חוב", sf(row.debt_sf), selected), kpi("מלאי", sf(row.inventory_value_sf), selected),
    kpi("הון חוזר", sf(row.working_capital_sf), selected), kpi("התחייבויות השקעה", sf(row.capex_commitments_sf), selected),
  ].join("");
  $("#pnlSummary").innerHTML = [
    ["הכנסות", sf(row.revenue_sf)], ["רווח גולמי", sf(row.gross_profit_sf)],
    ["שיעור רווח גולמי", pct(ratios.gross_margin)], ["רווח נקי", sf(row.net_profit_sf)],
    ["ROS / שיעור רווח נקי", pct(ratios.net_margin)],
  ].map(([label, value]) => `<div class="metric-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
  $("#balanceSummary").innerHTML = [
    ["נכסים שוטפים", sf(row.current_assets_sf)], ["מלאי", sf(row.inventory_value_sf)],
    ["התחייבויות שוטפות", sf(row.current_liabilities_sf)], ["חוב", sf(row.debt_sf)],
    ["הון עצמי", sf(row.equity_sf)], ["יחס חוב להון", ratios.debt_to_equity == null ? "—" : fmt(ratios.debt_to_equity, 2)],
  ].map(([label, value]) => `<div class="metric-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
  $("#liquiditySummary").innerHTML = [
    ["מזומן", sf(row.ending_cash_sf)], ["תזרים מפעילות שוטפת", row.operating_cash_flow_sf == null ? "לא זמין בדוח" : sf(row.operating_cash_flow_sf)],
    ["הון חוזר", sf(row.working_capital_sf)], ["יחס שוטף", ratios.current_ratio == null ? "—" : fmt(ratios.current_ratio, 2)],
    ["רצפת מזומן", row.cash_buffer_configured === false ? "לא הוגדרה" : sf(row.cash_buffer_sf)], ["תקציב פנוי להחלטות", sf(row.available_budget_sf)],
  ].map(([label, value]) => `<div class="metric-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
  const areas = state.financeRange?.intelligence?.financial?.areas || state.intelligence?.financial?.areas || [];
  $("#areaFinanceBody").innerHTML = areas.length ? areas.map(item => `<tr><td>${esc(item.area)}</td><td><span class="health-badge ${esc(item.health?.level || "unknown")}">${esc(item.health?.status || "—")}</span></td><td>${esc(item.currency)}</td><td>${fmt(item.revenue_sf)}</td><td>${fmt(item.net_profit_sf)}</td><td>${fmt(item.ending_cash_sf)}</td><td>${fmt(item.debt_sf)}</td><td>${fmt(item.inventory_value_sf)}</td><td>${fmt(item.available_budget_sf)}</td></tr>`).join("") : '<tr><td colspan="9" class="empty-copy">לא נקלטו עדיין נתונים לפי מדינה.</td></tr>';
  renderFinanceRangeExtras(selected);
}

function renderFinanceRangeExtras(selected) {
  const rows = financeRangeRows(selected);
  const mode = $("#financeModeSelect").value || "quarter";
  const from = $("#financeFromSelect").value || state.quarter;
  const to = $("#financeToSelect").value || state.quarter;
  const coverage = state.financeRange?.intelligence?.financial?.actual_coverage
    || state.intelligence?.financial?.actual_coverage
    || {};
  const actualTo = coverage.data_as_of
    && quarterNumber(coverage.data_as_of) < quarterNumber(to)
    ? coverage.data_as_of
    : to;
  const displayedRange = mode === "cumulative"
    ? `${from}–${actualTo}`
    : `Actual ${actualTo}`;
  const rangeRow = financeRangeView(selected) || {};
  $("#financeRangeSummary").innerHTML = [
    kpi("טווח מוצג", displayedRange, selected),
    kpi("הכנסות בטווח", sf(rangeRow.revenue_sf), mode === "cumulative" ? "סכום הרבעונים" : "הרבעון הנבחר"),
    kpi("רווח נקי בטווח", sf(rangeRow.net_profit_sf), mode === "cumulative" ? "סכום הרבעונים" : "הרבעון הנבחר"),
    kpi("מזומן בסוף הטווח", sf(rangeRow.ending_cash_sf), actualTo),
  ].join("");
  $("#financeTrendBody").innerHTML = rows.length ? rows.map(row => {
    const margin = num(row.revenue_sf) ? num(row.net_profit_sf) / num(row.revenue_sf) : null;
    return `<tr><td>${esc(row.quarter)}</td><td>${fmt(row.revenue_sf)}</td><td>${fmt(row.gross_profit_sf)}</td><td>${fmt(row.net_profit_sf)}</td><td>${fmt(row.ending_cash_sf)}</td><td>${fmt(row.debt_sf)}</td><td>${pct(margin)}</td></tr>`;
  }).join("") : '<tr><td colspan="7" class="empty-copy">לא קיימים נתונים בטווח שנבחר.</td></tr>';
}

async function loadFinanceRange() {
  const to = $("#financeToSelect").value || state.quarter;
  const [report, intelligence] = await Promise.all([
    api(`/api/reports/cumulative/${encodeURIComponent(to)}`),
    api(`/api/intelligence/${encodeURIComponent(to)}`),
  ]);
  state.financeRange = {report, intelligence};
  renderFinancePage();
}

async function loadUploads() {
  const [uploads, imports] = await Promise.all([api("/api/uploads"), api("/api/imports")]);
  state.approvedQuarters = [...new Set(
    imports
      .filter(row => row.committed_at && /^Q[1-9]$/.test(String(row.quarter || "")))
      .map(row => String(row.quarter))
  )].sort((a, b) => quarterNumber(a) - quarterNumber(b));
  renderQuarterPicker();
  renderDynamicQuarterContext();
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
  renderAgentImportStatus(imports);
}

function importItemCount(row) {
  const data = row?.extracted_data || {};
  return Object.keys(data.finance || {}).length
    + (data.finance_by_area || []).length
    + (data.operations || []).length
    + (data.research_results || []).length
    + (data.strategy_profile && Object.keys(data.strategy_profile).length ? 1 : 0);
}

function renderAgentImportStatus(imports = []) {
  const element = $("#agentImportStatus");
  if (!element) return;
  const row = imports[0];
  if (!row) {
    element.innerHTML = '<span class="empty-copy">לא הועלה עדיין קובץ דרך הצ׳אט.</span>';
    return;
  }
  const count = importItemCount(row);
  if (row.committed_at) {
    element.innerHTML = `<div class="agent-import-card committed"><div><strong>${esc(row.quarter)} · הקובץ האחרון אושר</strong><small>${count} פריטי מידע זמינים כעת לניתוח ולהמלצות.</small></div><span class="health-badge good">נקלט</span></div>`;
    return;
  }
  element.innerHTML = `<div class="agent-import-card"><div><strong>${esc(row.quarter)} · ${esc(row.parser_type)}</strong><small>${count} פריטים זוהו · ודאות ${esc(row.confidence || "—")}. בדקו ואשרו כדי שה-AI ישתמש בהם.</small></div><button class="button secondary" type="button" data-agent-commit-import="${esc(row.id)}" ${count ? "" : "disabled"}>אישור הנתונים</button></div>`;
}

async function loadReports() {
  const endpoint = state.reportMode === "quarter" ? "quarter" : "cumulative";
  const data = await api(`/api/reports/${endpoint}/${state.quarter}`);
  const cumulativeThrough = data.data_as_of || state.quarter;
  const planningNote = data.planning_quarter ? ` · משמש לתכנון ${esc(data.planning_quarter)}` : "";
  $("#reportHeader").innerHTML = `<h2>${state.reportMode === "quarter" ? `דוח ${esc(state.quarter)}` : `דוח מצטבר Q1–${esc(cumulativeThrough)}`}</h2><p>${esc(data.scorecard?.label || "")}${planningNote}</p>`;
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

function trendIcon(direction) {
  return direction === "up" ? "↗" : direction === "down" ? "↘" : "→";
}

function researchValue(value) {
  if (value == null || value === "") return "—";
  if (typeof value === "number") return fmt(value, 1);
  return String(value);
}

function researchTable(table) {
  const columns = table?.columns || [];
  const rows = table?.rows || [];
  if (!columns.length || !rows.length) return '<div class="empty-copy">לא נמצאה טבלה מספרית במקור.</div>';
  return `<div class="table-wrap research-table"><table><thead><tr>${columns.map(column => `<th>${esc(column.label)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${columns.map(column => `<td>${esc(researchValue(row[column.key]))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function renderResearchInsights() {
  const domain = ($("#insightResearchDomainSelect").value || "").toLowerCase();
  const rows = (state.insights?.research || []).filter(row => {
    if (!domain) return true;
    const haystack = `${row.title || ""} ${row.decision_area || ""} ${(row.relevance_domains || []).join(" ")} ${row.recommendation || ""}`.toLowerCase();
    return haystack.includes(domain);
  });
  $("#insightResearchResults").innerHTML = rows.length ? rows.map(row => {
    const metrics = (row.exact_metrics || []).map(item => `<div><span>${esc(item.label)}</span><strong>${esc(researchValue(item.value))}</strong></div>`).join("");
    const opportunities = (row.opportunities || []).map(item => `<li>${esc(item)}</li>`).join("");
    const risks = (row.risks || []).map(item => `<li>${esc(item)}</li>`).join("");
    return `<article class="research-insight-card">
      <div class="research-insight-head">
        <div><div class="research-meta"><span class="soft-pill">${esc(row.source_label || row.quarter)}</span><span class="soft-pill">ודאות ${esc(row.confidence || "—")}</span><span class="soft-pill">${esc(row.decision_area || "מחקר שוק")}</span></div><h3>${esc(row.title)}</h3><p>${esc(row.headline || row.key_result || "")}</p></div>
        <button class="text-link" type="button" data-ask-research="${esc(row.title)}">שאלו את ה-AI</button>
      </div>
      <div class="research-metrics">${metrics}</div>
      <div class="research-recommendation"><span>המלצה בעקבות התוצאה</span><strong>${esc(row.recommendation || "נדרש ניתוח נוסף.")}</strong></div>
      ${opportunities ? `<div class="research-signals good"><b>הזדמנויות</b><ul>${opportunities}</ul></div>` : ""}
      ${risks ? `<div class="research-signals warning"><b>סיכונים ופערים</b><ul>${risks}</ul></div>` : ""}
      <details><summary>הצגת התוצאות המספריות המדויקות</summary>${researchTable(row.table)}<p class="source-note">מקור: ${esc(row.source_name || "דוח רבעוני מאושר")} · ${esc(row.source_label || "")}</p></details>
    </article>`;
  }).join("") : '<div class="empty-copy">לא נמצאו מחקרי שוק בתחום שנבחר.</div>';
}

function renderLearningLedger() {
  const ledger = state.learningLedger || {};
  const summary = ledger.summary || {};
  const latestForecast = (ledger.forecasts || [])[0] || {};
  const q9Score = latestForecast.result?.q9?.score?.base;
  $("#learningSummary").innerHTML = [
    `<div><span>תחזיות שננעלו</span><strong>${fmt(summary.forecast_snapshots || 0)}</strong><small>נשמרות לפני קבלת Actual</small></div>`,
    `<div><span>דיוק ממוצע</span><strong>${summary.average_accuracy_score == null ? "—" : `${fmt(summary.average_accuracy_score, 1)}%`}</strong><small>משוקלל על המדדים שנמדדו</small></div>`,
    `<div><span>כיולים מאושרים</span><strong>${fmt(summary.approved_calibrations || 0)}</strong><small>${fmt(summary.pending_calibrations || 0)} ממתינים לבדיקת הצוות</small></div>`,
    `<div><span>אומדן Q9 נוכחי</span><strong>${score(q9Score)}</strong><small>מהתחזית הפתוחה האחרונה · לא ציון רשמי</small></div>`,
  ].join("");

  const evaluations = ledger.evaluations || [];
  $("#learningEvaluations").innerHTML = evaluations.length ? evaluations.map(row => {
    const result = row.summary || {};
    const metricRows = Object.values(row.metric_errors || {}).sort((a, b) => Math.abs(num(b.percentage_error)) - Math.abs(num(a.percentage_error))).slice(0, 5);
    const metrics = metricRows.map(metric => `<div class="learning-metric ${metric.within_range ? "within" : "miss"}"><span>${esc(metric.label)}</span><strong><bdi dir="ltr">${fmt(metric.forecast, 1)} → ${fmt(metric.actual, 1)}</bdi></strong><small>${metric.percentage_error == null ? "—" : `${num(metric.percentage_error) > 0 ? "+" : ""}${fmt(num(metric.percentage_error) * 100, 1)}%`} · ${metric.within_range ? "בתוך הטווח" : "מחוץ לטווח"}</small></div>`).join("");
    const drivers = (row.driver_analysis || []).map(driver => `<li class="${esc(driver.severity || "low")}"><strong>${esc(driver.finding)}</strong><small>Driver: ${esc(driver.driver)}</small></li>`).join("");
    return `<article class="learning-evaluation-card"><div class="learning-evaluation-head"><div><span class="soft-pill"><bdi dir="ltr">${esc(row.source_actual_quarter || "—")} → ${esc(row.target_quarter)}</bdi></span><h3>תחקיר התחזית של ${esc(row.target_quarter)}</h3></div><div class="accuracy-orb ${num(result.accuracy_score) >= 75 ? "good" : num(result.accuracy_score) >= 50 ? "warning" : "critical"}"><strong>${result.accuracy_score == null ? "—" : fmt(result.accuracy_score, 0)}</strong><span>דיוק</span></div></div><div class="learning-metrics">${metrics}</div><div class="driver-analysis"><h4>למה טעינו או צדקנו</h4><ul>${drivers || "<li>אין מספיק מדדים לאבחון.</li>"}</ul></div></article>`;
  }).join("") : '<div class="empty-copy">לא הושלמה עדיין השוואת Forecast→Actual. נועלים תחזית לפני הרבעון, ולאחר אישור הדוח הבא מתקבל כאן תחקיר אוטומטי.</div>';

  const proposals = (ledger.calibration_proposals || []).filter(row => row.status === "draft");
  $("#calibrationProposals").innerHTML = proposals.length ? proposals.map(row => `<article class="calibration-card"><div><span class="soft-pill">ודאות ${esc(row.confidence)}</span><h4>${esc(row.parameter_key)}</h4><p>${esc(row.reason)}</p><strong><bdi dir="ltr">${fmt(row.previous_value, 3)} → ${fmt(row.proposed_value, 3)}</bdi></strong></div><div class="calibration-actions"><button class="button secondary" type="button" data-calibration-status="rejected" data-calibration-id="${esc(row.id)}">דחייה</button><button class="button primary" type="button" data-calibration-status="approved" data-calibration-id="${esc(row.id)}">אישור לכיולים עתידיים</button></div></article>`).join("") : '<div class="empty-copy">אין כרגע הצעות כיול שממתינות להחלטה.</div>';
}

async function loadLearningLedger() {
  state.learningLedger = await api(`/api/learning-ledger?quarter=${encodeURIComponent(state.quarter)}`);
  renderLearningLedger();
}

function renderInsights() {
  const trends = state.insights?.trends || {};
  const cards = [...(trends.cards || []), ...(trends.cross_research || [])];
  $("#insightCards").innerHTML = cards.length ? cards.map(item => `<article class="insight-card ${esc(item.direction || "flat")}"><span class="trend-arrow">${trendIcon(item.direction)}</span><div><small>${esc(item.quarter || `עד ${state.quarter}`)} · ודאות ${esc(item.confidence || "גבוהה")}</small><h2>${esc(item.title)}</h2><p>${esc(item.evidence)}</p><strong>${esc(item.recommendation)}</strong></div></article>`).join("") : '<div class="empty-copy">נדרשים לפחות שני רבעונים מאושרים לניתוח מגמות.</div>';
  $("#pricingInsights").innerHTML = (trends.pricing || []).length ? trends.pricing.map(item => `<div class="compact-row insight-row"><div><strong>${esc(item.segment)}</strong><small><bdi dir="ltr">${esc(item.from_quarter)} → ${esc(item.to_quarter)}</bdi> · מחיר ${signedSf(item.price_delta).replace(" SF", "")} · מכירות ${item.sales_delta > 0 ? "+" : ""}${fmt(item.sales_delta)} · מלאי ${item.inventory_delta > 0 ? "+" : ""}${fmt(item.inventory_delta)}</small><p>${esc(item.signal)}. ${esc(item.recommendation)}</p></div></div>`).join("") : '<div class="empty-copy">אין עדיין מספיק תצפיות מחיר ומכירות.</div>';
  $("#competitorInsights").innerHTML = (trends.competitors || []).length ? trends.competitors.map(item => `<div class="compact-row insight-row"><span class="trend-mini ${esc(item.direction)}">${trendIcon(item.direction)}</span><div><strong>${esc(item.segment)}</strong><small>חציון מתחרים: <bdi dir="ltr">${fmt(item.median_from)} → ${fmt(item.median_to)}</bdi> · ${item.observations} תצפיות</small></div></div>`).join("") : '<div class="empty-copy">לא קיימות עדיין מספיק תוצאות MR28 להשוואה בין רבעונים.</div>';
  renderResearchInsights();
  $("#dashboardChanges").innerHTML = cards.length ? cards.slice(0, 4).map(item => `<div class="compact-row"><span class="trend-mini ${esc(item.direction || "flat")}">${trendIcon(item.direction)}</span><div><strong>${esc(item.title)}</strong><small>${esc(item.evidence)}</small></div></div>`).join("") : '<div class="empty-copy">לא קיימות עדיין מספיק תוצאות מאושרות להשוואה.</div>';
}

async function loadInsights() {
  state.insights = await api(`/api/insights/${state.quarter}`);
  renderInsights();
}

async function loadResearch() {
  const domain = $("#researchDomainSelect").value || "";
  const [researchResult, intelligenceResult] = await Promise.allSettled([
    api(`/api/research/relevant/${state.quarter}?domain=${encodeURIComponent(domain)}`),
    api(`/api/market-intelligence/${state.quarter}`),
  ]);
  if (researchResult.status === "rejected") throw researchResult.reason;
  const data = researchResult.value;
  const intelligence = intelligenceResult.status === "fulfilled" ? intelligenceResult.value : {
    recommended_research: [], calibration_signals: [], cannot_conclude: ["היסטוריית ניתוחי השוק אינה זמינה כרגע; תוצאות המחקר המאושרות עדיין מוצגות."], mapping_coverage: {},
  };
  state.marketIntelligence = intelligence;
  $("#researchResults").innerHTML = data.results.length ? data.results.map(row => `<article class="research-card ${row.relevant ? "relevant" : ""}"><div class="research-meta"><span class="soft-pill">${esc(row.quarter)}</span><span class="soft-pill">ודאות ${esc(row.confidence)}</span>${row.area ? `<span class="soft-pill">${esc(row.area)}</span>` : ""}</div><h2>${esc(row.title)}</h2><p>${esc(row.key_result || "טרם הוזן סיכום מובנה למחקר.")}</p><button class="text-link rtl-next-link" type="button" data-ask-research="${esc(row.title)}">שאל את ה-Agent על המחקר</button></article>`).join("") : '<div class="empty-copy">לא נקלטו מחקרי שוק מאושרים.</div>';
  $("#researchCatalog").innerHTML = data.catalog.map(row => `<div class="compact-row"><div><strong>MR${esc(row.study_id)} · ${esc(row.name)}</strong><small>${esc(row.description)}</small></div><span class="soft-pill">${row.cost_k_sf == null ? "עלות לא ידועה" : `${fmt(row.cost_k_sf)}K SF`}</span></div>`).join("");
  const voi = intelligence.recommended_research || [];
  $("#voiRecommendations").innerHTML = voi.length ? voi.map((row, index) => `<div class="compact-row"><div><strong>${index + 1}. ${esc(row.label)} · ${esc(row.name)}</strong><small>עלות ${sf(row.cost_sf)} · הסתברות שינוי החלטה ${pct(row.decision_change_probability)} · פעולות ${esc((row.affected_actions || []).join(", "))}</small><p>${row.value_status === "quantified" ? `VOI נטו משוער: ${signedSf(row.net_voi_sf)}` : "אין חשיפה כספית מאושרת—הדירוג איכותני בלבד."}</p></div><span class="soft-pill">${esc(row.confidence)}</span></div>`).join("") : '<div class="empty-copy">אין כרגע מחקר נוסף בעל קשר מוכח להחלטה פתוחה.</div>';
  const calibrations = intelligence.calibration_signals || [];
  $("#researchCalibrations").innerHTML = calibrations.length ? calibrations.map(row => `<div class="compact-row"><div><strong>${esc(row.segment)}</strong><small>${row.observation_count} תצפיות · ${row.independent_price_changes} שינויי מחיר מהותיים</small><p>${row.elasticity_estimate == null ? esc(row.warning) : `אלסטיות טיוטה ${fmt(row.elasticity_estimate, 3)} · טווח ${fmt(row.range?.[0], 3)}–${fmt(row.range?.[1], 3)}. ${esc(row.warning)}`}</p></div><span class="soft-pill">${row.status === "sufficient_for_draft" ? "טיוטת הסקה" : "לא מספיק מידע"}</span></div>`).join("") : '<div class="empty-copy">אין עדיין תצפיות מחיר–מכירות תקינות לכיול.</div>';
  $("#researchUnknowns").innerHTML = (intelligence.cannot_conclude || []).map(text => `<div class="compact-row"><div><strong>גבול ידע</strong><small>${esc(text)}</small></div></div>`).join("") || '<div class="empty-copy">לא זוהו פערי ידע קריטיים.</div>';
  const coverage = intelligence.mapping_coverage || {};
  $("#researchCoverage").textContent = `מיפוי ${fmt(coverage.percent, 1)}% · ${coverage.mapped || 0}/${coverage.catalog_total || 0}`;
}

function renderDecisionLog(rows) {
  const quarter = $("#decisionLogQuarter").value || "";
  const status = $("#decisionLogStatus").value || "";
  const filtered = rows.filter(row => (!quarter || row.quarter === quarter) && (!status || row.status === status));
  const approved = rows.filter(row => ["אושר", "בוצע", "נסגר"].includes(row.status)).length;
  const completed = rows.filter(row => ["בוצע", "נסגר"].includes(row.status)).length;
  const learned = rows.filter(row => String(row.actual_result || "").trim()).length;
  $("#decisionLogSummary").innerHTML = [
    `<div><span>סה״כ החלטות</span><strong>${rows.length}</strong><small>עד ${esc(state.quarter)}</small></div>`,
    `<div><span>אושרו</span><strong>${approved}</strong><small>כולל החלטות שבוצעו</small></div>`,
    `<div><span>בוצעו</span><strong>${completed}</strong><small>ממתינות לתוצאה או נסגרו</small></div>`,
    `<div><span>כוללות למידה בפועל</span><strong>${learned}</strong><small>תחזית מול ביצוע</small></div>`,
  ].join("");
  $("#decisionLogList").innerHTML = filtered.length ? filtered.map(row => `<article class="decision-log-card" data-decision-id="${esc(row.id)}">
    <div class="decision-log-head"><div><span class="soft-pill">${esc(row.quarter)}</span><span class="soft-pill">${esc(row.domain || "אסטרטגיה")}</span><h3>${esc(row.title)}</h3></div><label>סטטוס<select data-decision-field="status"><option ${row.status === "טיוטה" ? "selected" : ""}>טיוטה</option><option ${row.status === "מוכן לאישור" ? "selected" : ""}>מוכן לאישור</option><option ${row.status === "אושר" ? "selected" : ""}>אושר</option><option ${row.status === "בוצע" ? "selected" : ""}>בוצע</option><option ${row.status === "נסגר" ? "selected" : ""}>נסגר</option></select></label></div>
    <div class="decision-log-grid"><div><span>מה הוחלט</span><p>${esc(row.selected_option || "טרם תועד")}</p></div><div><span>הנימוק בזמן ההחלטה</span><p>${esc(row.rationale || "טרם תועד")}</p></div><div><span>תוצאה צפויה</span><p>${esc(row.expected_result || "טרם תועדה")}</p></div><label><span>מה קרה בפועל / מה למדנו</span><textarea data-decision-field="actual_result" rows="3">${esc(row.actual_result || "")}</textarea></label></div>
    <div class="decision-log-foot"><small>בעל אחריות: ${esc(row.owner || "לא הוגדר")} · ודאות ${esc(row.confidence || "—")}</small><button class="button secondary" type="button" data-save-decision="${esc(row.id)}">שמירת עדכון</button></div>
  </article>`).join("") : '<div class="empty-copy">אין החלטות התואמות את הסינון. אפשר לשמור המלצה ישירות מחדר ההחלטות.</div>';
}

async function loadDecisionLog() {
  const [decisionsResult, sessionsResult] = await Promise.allSettled([
    api("/api/decisions"),
    api(`/api/governance/sessions?quarter=${encodeURIComponent(state.quarter)}`),
  ]);
  if (decisionsResult.status === "rejected") throw decisionsResult.reason;
  const rows = decisionsResult.value;
  const sessions = sessionsResult.status === "fulfilled" ? sessionsResult.value : [];
  state.decisions = rows;
  state.governanceSessions = sessions;
  renderDecisionLog(rows);
  renderGovernanceSession();
  if (state.intelligence) renderRecommendations();
}

function renderGovernanceSession() {
  const session = (state.governanceSessions || [])[0];
  const status = $("#governanceStatus");
  const form = $("#governanceVoteForm");
  const approve = $("#approveGovernanceSession");
  if (!session) {
    status.className = "status-chip";
    status.textContent = "אין ישיבה פעילה";
    $("#governanceMachineGate").innerHTML = '<div class="empty-copy">פתחו ישיבה מהסל המומלץ לאחר השלמת אופטימיזציית Q9.</div>';
    $("#governanceRoles").innerHTML = "";
    form.classList.add("hidden");
    approve.disabled = true;
    return;
  }
  const gate = session.governance_gate || {};
  const labels = {
    approved: "אושר וננעל", ready_to_approve: "מוכן לאישור", awaiting_roles: "ממתין לתפקידים",
    awaiting_consensus: "ממתין להסכמה", changes_requested: "נדרשים שינויים", blocked_by_controls: "חסום בבקרות",
  };
  const locked = Boolean(session.locked);
  status.className = `status-chip ${locked || gate.can_approve ? "ok" : gate.failed_machine_checks?.length ? "error" : ""}`;
  status.textContent = labels[session.status] || labels[gate.status] || session.status;
  const checkLabels = {
    optimizer_feasible: "סל אפשרי", evidence_pass: "ראיות מספריות", rules_pass: "חוקי המשחק",
    budget_pass: "תקציב ורצפת מזומן", dependencies_pass: "תלויות והתנגשויות", timing_pass: "תזמון",
  };
  $("#governanceMachineGate").innerHTML = Object.entries(gate.machine_checks || {}).map(([key, passed]) => `<div class="governance-check ${passed ? "pass" : "fail"}"><span>${passed ? "✓" : "!"}</span><div><strong>${esc(checkLabels[key] || key)}</strong><small>${passed ? "עבר" : "חוסם אישור"}</small></div></div>`).join("");
  const votes = Object.fromEntries((session.votes || []).map(row => [row.role, row]));
  $("#governanceRoles").innerHTML = (session.roles || []).map(item => {
    const vote = votes[item.role];
    const voteLabel = vote?.vote === "approve" ? "מאושר" : vote?.vote === "reject" ? "מבקש שינוי" : vote?.vote === "abstain" ? "נמנע" : "ממתין";
    return `<article class="governance-role ${esc(vote?.vote || "pending")}"><span>${vote?.vote === "approve" ? "✓" : vote?.vote === "reject" ? "!" : "○"}</span><div><strong>${esc(item.label)}</strong><small>${vote ? `${esc(vote.voter_name)} · ${voteLabel}` : voteLabel}</small>${vote?.rationale ? `<p>${esc(vote.rationale)}</p>` : ""}</div></article>`;
  }).join("");
  form.classList.toggle("hidden", locked);
  approve.disabled = locked || !gate.can_approve;
  approve.textContent = locked ? "הישיבה אושרה וננעלה" : "אישור ונעילת הישיבה";
  $("#governancePolicy").textContent = locked
    ? `אושר על ידי ${(session.approved_by || []).join(", ")} · האישור אינו שליחה ל־INTOPIA.`
    : `${gate.approval_count || 0}/5 אישורים · נדרשות עמדות מכל התפקידים, לפחות ארבעה אישורים וללא התנגדות מתפקיד חוסם.`;
}

function renderActionBasket() {
  $("#actionBasket").innerHTML = state.actions.length ? state.actions.map((action, index) => `<div class="action-card"><div><strong>${esc(action.code ? `${action.code} · ${action.title}` : action.title || action.type)}</strong><small>${esc(action.area || "כל החברה")} · ${esc(action.product || "כל המוצרים")}</small></div><span>${sf(action.cost_sf)}</span><button type="button" data-remove-action="${index}">הסרה</button></div>`).join("") : '<div class="empty-copy">סל הפעולות ריק.</div>';
}

function simulationPayload() {
  const financial = state.intelligence?.financial?.consolidated || {};
  return {name: `תרחיש ${state.quarter}`, budget_sf: financial.available_budget_sf, cash_buffer_sf: financial.cash_buffer_sf, actions: state.actions};
}

function renderSimulation(result) {
  state.lastSimulation = result;
  const status = result.feasible ? ["ok", "התרחיש עומד במגבלות התקציב והמזומן"] : ["bad", result.violations.join(" ")];
  $("#simulationResult").className = "";
  const warnings = result.warnings || [];
  const sequence = result.recommended_sequence || [];
  const rules = result.applied_rules || [];
  const dependencies = result.dependency_analysis || {};
  $("#simulationResult").innerHTML = `<div class="scenario-status ${status[0]}">${esc(status[1])}</div><div class="scenario-cases">${["low","base","high"].map(key => { const row = result.scenarios[key]; const label = {low:"נמוך",base:"בסיס",high:"גבוה"}[key]; return `<div class="scenario-case"><span>${label}</span><strong>Q9: ${score(row.q9_score)}</strong><span>50% עבר: ${score(row.past_performance_score)}</span><span>50% עתיד: ${score(row.future_potential_score)}</span><span>רווח ${sf(row.net_profit_sf)}</span><span>מזומן ${sf(row.ending_cash_sf)}</span></div>`; }).join("")}</div><div class="metric-list"><div class="metric-row"><span>עלות מתוכננת</span><strong>${sf(result.budget.planned_cost_sf)}</strong></div><div class="metric-row"><span>תקציב נותר</span><strong>${sf(result.budget.remaining_sf)}</strong></div><div class="metric-row"><span>שינוי קיבולת</span><strong>${fmt(result.operating_effects?.capacity_delta_units)} יחידות</strong></div><div class="metric-row"><span>שינוי מלאי</span><strong>${fmt(result.operating_effects?.inventory_delta_units)} יחידות</strong></div></div>${rules.length ? `<div class="simulation-notes"><strong>חוקים שנבדקו · v${esc(result.rulebook_version)}</strong><ul>${rules.map(item => `<li>${esc(item.rule_id)} · ${esc(item.source)} עמ׳ ${esc(item.source_page || "—")}</li>`).join("")}</ul></div>` : ""}${warnings.length ? `<div class="simulation-notes"><strong>תזמון וסיכונים</strong><ul>${warnings.map(item => `<li>${esc(item)}</li>`).join("")}</ul></div>` : ""}${sequence.length ? `<div class="simulation-notes"><strong>סדר פעולות מומלץ תחת התקציב</strong><ol>${sequence.map(item => `<li>${esc(item.action.code || item.action.type)} · ${esc(item.action.title || "")} — ${sf(item.cost_sf)} · תרומה ${score(item.expected_score_delta)}</li>`).join("")}</ol></div>` : ""}`;
  const dependencyEdges = dependencies.edges || [];
  const dependencyGaps = dependencies.gaps || [];
  const dependencyConflicts = dependencies.conflicts || [];
  if (dependencyEdges.length || dependencyGaps.length || dependencyConflicts.length) {
    const nodeNames = Object.fromEntries((dependencies.nodes || []).map(item => [item.id, item.title]));
    $("#simulationResult").insertAdjacentHTML("beforeend", `
      <div class="simulation-notes dependency-results">
        <strong>תלויות ותיאום בין החלטות</strong>
        <ul>
          ${dependencyEdges.map(item => `<li><b>קודם: ${esc(nodeNames[item.from] || item.from)}</b> · אחר כך: <b>${esc(nodeNames[item.to] || item.to)}</b> — ${esc(item.reason)}</li>`).join("")}
          ${dependencyGaps.map(item => `<li class="dependency-warning"><b>תנאי חסר:</b> ${esc(item.missing)} — ${esc(item.reason)}</li>`).join("")}
          ${dependencyConflicts.map(item => `<li class="dependency-warning"><b>התנגשות:</b> ${esc(item.reason)}</li>`).join("")}
        </ul>
      </div>
    `);
  }
  const twin = result.digital_twin?.base;
  const twinTimeline = twin?.timeline || [];
  if (twinTimeline.length) {
    const baselineQuarter = result.digital_twin?.baseline?.as_of_quarter || "—";
    const eventLabel = kind => ({
      cash_cost: "תשלום", funding: "מימון", economic_effect: "השפעה כלכלית",
      inventory_produced: "ייצור למלאי", inventory_sold: "מכירה מהמלאי",
      capacity_online: "קיבולת זמינה", technology_available: "טכנולוגיה זמינה",
      rd_investment: "מו״פ", receivables_collected: "גביית לקוחות",
      confidence_update: "מידע חדש",
    }[kind] || kind);
    $("#simulationResult").insertAdjacentHTML("beforeend", `
      <section class="twin-panel" aria-label="Digital Twin">
        <div class="twin-heading">
          <div><span class="soft-pill">Digital Twin · Base</span><h3>כך חבילת ההחלטות משנה את החברה עד Q9</h3></div>
          <small>מצב אמת נעול עד ${esc(baselineQuarter)} · הסימולציה אינה משנה Actuals</small>
        </div>
        <div class="twin-timeline">
          ${twinTimeline.map(item => {
            const financial = item.state?.consolidated || {};
            const technology = item.state?.technology || {};
            const inventory = (item.state?.segments || []).reduce((sum, row) => sum + Number(row.inventory_units || 0), 0);
            const capacity = (item.state?.segments || []).reduce((sum, row) => sum + Number(row.capacity_units || 0), 0);
            return `<article class="twin-quarter">
              <div class="twin-quarter-head"><strong>${esc(item.quarter)}</strong><span>${(item.events || []).length} מעברים</span></div>
              <dl>
                <div><dt>מזומן</dt><dd>${sf(financial.cash_sf)}</dd></div>
                <div><dt>חוב</dt><dd>${sf(financial.debt_sf)}</dd></div>
                <div><dt>מלאי</dt><dd>${fmt(inventory)} יח׳</dd></div>
                <div><dt>קיבולת</dt><dd>${fmt(capacity)} יח׳</dd></div>
                <div><dt>טכנולוגיה</dt><dd><bdi dir="ltr">X${fmt(technology.max_x_grade)} · Y${fmt(technology.max_y_grade)}</bdi></dd></div>
              </dl>
              <div class="twin-events">${(item.events || []).length ? item.events.map(event => `<span>${esc(eventLabel(event.kind))}${event.code ? ` · ${esc(event.code)}` : ""}</span>`).join("") : "<span>אין מעבר חדש</span>"}</div>
            </article>`;
          }).join("")}
        </div>
        <details class="twin-assumptions"><summary>הנחות המודל</summary><ul>${(twin.assumptions || []).map(item => `<li>${esc(item)}</li>`).join("")}</ul></details>
      </section>
    `);
  }
}

async function loadSavedScenarios() {
  const rows = await api(`/api/scenario-portfolios?quarter=${encodeURIComponent(state.quarter)}`);
  $("#savedScenarios").innerHTML = rows.length ? rows.map(row => `<div class="compact-row"><div><strong>${esc(row.name)}</strong><small>${esc(row.status)} · ${row.result?.feasible ? "אפשרי" : "דורש תיקון"}</small></div><button class="text-link" type="button" data-delete-portfolio="${esc(row.id)}">מחיקה</button></div>`).join("") : '<div class="empty-copy">אין תרחישים שמורים.</div>';
}

function renderRulebook(data) {
  state.rulebook = data;
  const summary = data.summary || {};
  $("#rulebookVersion").className = "status-chip ok";
  $("#rulebookVersion").textContent = `Rulebook v${summary.version || "—"}`;
  $("#rulebookSummary").innerHTML = [
    `<div><span>חוקים רשומים</span><strong>${fmt(summary.total_rules)}</strong><small>${fmt(summary.approved_rules)} מאושרים</small></div>`,
    `<div><span>חוקים חוסמים</span><strong>${fmt(summary.blocking_rules)}</strong><small>מונעים חבילת החלטות לא חוקית</small></div>`,
    `<div><span>מקורות</span><strong>${fmt(summary.source_count)}</strong><small>לפי סדר עדיפות מאושר</small></div>`,
    `<div><span>סתירות פתוחות</span><strong>${fmt((data.conflicts || []).length)}</strong><small>מחייבות אישור אנושי</small></div>`,
  ].join("");
  $("#rulebookList").innerHTML = (data.rules || []).length ? data.rules.map(row => `<article class="rule-card ${row.is_blocking ? "blocking" : ""}">
    <div class="rule-card-head"><div><span class="soft-pill">${esc(row.rule_id)}</span><span class="soft-pill">${esc(row.knowledge_type)}</span></div><span class="health-badge ${row.is_blocking ? "critical" : "good"}">${row.is_blocking ? "חוסם" : "מתריע/מחשב"}</span></div>
    <h3>${esc(row.name_he || row.name_en)}</h3><p>${esc(row.description || row.name_en)}</p>
    <small>${esc(row.source_id)} · עמ׳ ${esc(row.source_page || "—")} · גרסה ${esc(row.version)} · ודאות ${esc(row.confidence)}</small>
  </article>`).join("") : '<div class="empty-copy">לא נמצאו חוקים התואמים לחיפוש.</div>';
  const conflicts = data.conflicts || [];
  $("#ruleSources").innerHTML = (data.sources || []).map(row => `<div class="compact-row"><div><strong>${esc(row.priority)}. ${esc(row.name)}</strong><small>${esc(row.source_type)} · ${esc(row.status)} · ${esc(row.version_label)}</small></div></div>`).join("") +
    (conflicts.length ? `<div class="notice"><strong>${conflicts.length} מועמדי חוק/סתירות ממתינים לאישור</strong><small>אישור מסמן מועמד לגרסה הבאה; הוא אינו משנה את Rulebook הפעיל.</small></div>${conflicts.map(row => {
      const candidate = row.candidate_value || {};
      return `<div class="conflict-card">
        <strong>${esc(candidate.name || row.rule_id)}</strong>
        <small>${esc(candidate.candidate_kind || "candidate")} · ${esc(row.candidate_source_id || "")} · ${esc(candidate.confidence || "—")}</small>
        <p>${esc(candidate.explicit_value_or_action || row.description || "")}</p>
        <div class="action-row">
          <button class="text-link" type="button" data-resolve-conflict="${esc(row.id)}" data-conflict-status="approved_for_next_version">אשר לגרסה הבאה</button>
          <button class="text-link" type="button" data-resolve-conflict="${esc(row.id)}" data-conflict-status="rejected">דחה</button>
          <button class="text-link" type="button" data-resolve-conflict="${esc(row.id)}" data-conflict-status="deferred">דחה לבדיקה</button>
        </div>
      </div>`;
    }).join("")}` : '<div class="notice success"><strong>אין סתירות חוקים פתוחות.</strong></div>');
}

async function loadRulebook(query = "") {
  const data = await api(`/api/rulebook${query ? `?${query}` : ""}`);
  renderRulebook(data);
}

function renderRuleCheck(result) {
  const checks = result.checks || [];
  const violations = result.violations || [];
  $("#ruleCheckResult").className = `rule-check-result ${result.allowed ? "allowed" : "blocked"}`;
  $("#ruleCheckResult").innerHTML = `
    <div class="scenario-status ${result.allowed ? "ok" : "bad"}">${result.allowed ? "הפעולה חוקית לפי המידע שהוזן" : "הפעולה חסומה עד לתיקון"}</div>
    <p>נבדק מול Rulebook v${esc(result.rulebook_version)} עבור ${esc(result.quarter)}.</p>
    ${violations.length ? `<div class="simulation-notes"><strong>מה צריך לתקן</strong><ul>${violations.map(item => `<li><strong>${esc(item.rule_id)}</strong> · ${esc(item.message)}${item.remediation ? `<br><small>${esc(item.remediation)}</small>` : ""}</li>`).join("")}</ul></div>` : ""}
    ${checks.length ? `<div class="simulation-notes"><strong>ראיות וחוקים שהופעלו</strong><ul>${checks.map(item => {
      const citation = item.citation || {};
      return `<li><span class="health-badge ${item.status === "fail" ? "critical" : "good"}">${item.status === "fail" ? "נכשל" : "עבר"}</span> <strong>${esc(item.rule_id)}</strong> · ${esc(item.message)}<br><small>${esc(citation.source || citation.source_id || "")}${citation.page ? ` · עמ׳ ${esc(citation.page)}` : ""}${citation.version ? ` · גרסה ${esc(citation.version)}` : ""}</small></li>`;
    }).join("")}</ul></div>` : '<div class="notice">לא הופעל חוק ספציפי. יש להשלים שדות או לבחור קוד טופס רשמי כדי לבצע בדיקה מלאה.</div>'}`;
}

function bindRules() {
  $("#ruleSearchForm").addEventListener("submit", async event => {
    event.preventDefault();
    const values = formPayload(event.target);
    const query = new URLSearchParams();
    Object.entries(values).forEach(([key, value]) => {
      if (value !== "" && value != null) query.set(key, String(value));
    });
    try { await loadRulebook(query.toString()); }
    catch (error) { toast(error.message, true); }
  });
  $("#ruleCheckForm").addEventListener("submit", async event => {
    event.preventDefault();
    const action = formPayload(event.target);
    Object.keys(action).forEach(key => {
      if (action[key] === "" || action[key] == null) delete action[key];
    });
    try {
      const result = await api("/api/rulebook/check", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({quarter: state.quarter, action, strict: false}),
      });
      renderRuleCheck(result);
    } catch (error) { toast(error.message, true); }
  });
  $("#ruleSources").addEventListener("click", async event => {
    const button = event.target.closest("[data-resolve-conflict]");
    if (!button) return;
    const status = button.dataset.conflictStatus;
    const defaultNote = status === "approved_for_next_version"
      ? "אושר כמועמד לגרסת Rulebook הבאה לאחר אימות המקור."
      : status === "rejected" ? "נדחה לאחר בדיקה אנושית." : "נדרש מידע נוסף.";
    const resolution = window.prompt("הוסיפו נימוק להחלטה", defaultNote);
    if (resolution == null) return;
    try {
      await api(`/api/rulebook/conflicts/${encodeURIComponent(button.dataset.resolveConflict)}/resolve`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({status, resolution}),
      });
      toast("המועמד עודכן ותועד.");
      await loadRulebook();
    } catch (error) { toast(error.message, true); }
  });
}

async function loadAgentStatus() {
  const data = await api("/api/agent/status");
  const element = $("#agentStatus");
  if (data.ready) { element.className = "status-chip ok"; element.textContent = `פעיל · ${data.model}`; element.title = data.reason; }
  else {
    element.className = "status-chip error";
    element.textContent = data.missing?.includes("OPENAI_API_KEY") ? "נדרש חיבור OpenAI" : "נדרשת הגדרה";
    element.title = data.reason || "";
  }
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
  $("#sideNav").inert = true;
  $("#menuButton").addEventListener("click", () => document.body.classList.contains("menu-open") ? closeMenu() : openMenu());
  $("#menuOverlay").addEventListener("click", closeMenu);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeMenu();
    if (event.key !== "Tab" || !document.body.classList.contains("menu-open")) return;
    const focusable = $$('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', $("#sideNav"));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  $$(".nav-item").forEach(button => button.addEventListener("click", () => showSection(button.dataset.section)));
  $$('[data-go]').forEach(button => button.addEventListener("click", () => showSection(button.dataset.go)));
}

function bindStrategyOptimization() {
  $("#refreshStrategyOptimization").addEventListener("click", async event => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "מחשב מחדש…";
    try {
      state.strategyOptimization = await api(`/api/q9-optimization/${encodeURIComponent(state.quarter)}/refresh`, {method:"POST"});
      renderStrategyOptimization();
      toast("טיוטת האסטרטגיה עודכנה לפי הנתונים המאושרים");
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = "חישוב מחדש";
    }
  });
  $("#askStrategyAI").addEventListener("click", () => {
    const prompt = state.strategyOptimization?.agent_prompt
      || "נתח את האסטרטגיה המקורית מול התוצאות שאושרו והצע Rolling Plan ממומן עד Q9.";
    showSection("agent");
    const question = $("#agentForm [name=question]");
    question.value = prompt;
    question.focus();
  });
}

function bindSettingsAndQuarter() {
  $("#settingsForm").addEventListener("input", () => debounceSave("settings", () => api("/api/settings", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(formPayload($("#settingsForm")))})));
  $("#quarterSelect").addEventListener("change", async event => {
    if (event.target.value === "__all__") {
      state.viewMode = "cumulative";
      state.reportMode = "cumulative";
      state.quarter = nextPlanningQuarter(latestApprovedQuarter());
      $("#financeModeSelect").value = "cumulative";
      $("#financeFromSelect").disabled = false;
      $("#financeFromSelect").value = "Q1";
      $("#quarterReportButton").classList.remove("active");
      $("#cumulativeReportButton").classList.add("active");
    } else {
      state.viewMode = "quarter";
      state.quarter = event.target.value;
      state.reportMode = "quarter";
      $("#financeModeSelect").value = "quarter";
      $("#financeFromSelect").disabled = true;
      $("#quarterReportButton").classList.add("active");
      $("#cumulativeReportButton").classList.remove("active");
    }
    await api("/api/settings", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({selected_quarter: state.quarter})});
    await loadCurrentQuarter();
    renderQuarterPicker();
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
    try { const result = await api(`/api/imports/${encodeURIComponent(id)}/commit`, {method:"POST"}); toast(`נקלטו ${Object.values(result.counts || {}).reduce((a,b) => a + b, 0)} פריטים`); await Promise.all([loadUploads(), loadIntelligence(), loadReports(), loadInsights(), loadLearningLedger()]); }
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
  $("#applyFinanceFilter").addEventListener("click", loadFinanceRange);
  $("#financeModeSelect").addEventListener("change", async event => {
    $("#financeFromSelect").disabled = event.target.value !== "cumulative";
    await loadFinanceRange();
  });
  $("#financeFromSelect").addEventListener("change", event => {
    if (quarterNumber(event.target.value) > quarterNumber($("#financeToSelect").value)) {
      $("#financeToSelect").value = event.target.value;
    }
  });
  $("#financeToSelect").addEventListener("change", event => {
    if (quarterNumber(event.target.value) < quarterNumber($("#financeFromSelect").value)) {
      $("#financeFromSelect").value = event.target.value;
    }
  });
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
  $("#refreshMarketIntelligence").addEventListener("click", async () => {
    try {
      await api(`/api/market-intelligence/${state.quarter}/refresh`, {method: "POST"});
      await loadResearch();
      toast("ניתוח מחקרי השוק עודכן ונשמר");
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("#researchResults").addEventListener("click", event => { if (!event.target.dataset.askResearch) return; showSection("agent"); $("#agentForm [name=question]").value = `מה למדנו מהמחקר ${event.target.dataset.askResearch}, ולאילו החלטות הוא רלוונטי?`; });
  $("#insightResearchDomainSelect").addEventListener("change", renderResearchInsights);
  $("#freezeForecastButton").addEventListener("click", async event => {
    event.target.disabled = true;
    try {
      const result = await api(`/api/learning/forecasts/${encodeURIComponent(state.quarter)}`, {method:"POST"});
      toast(`תחזית ${result.target_quarter || state.quarter} ננעלה ונשמרה להשוואה עתידית`);
      await loadLearningLedger();
    } catch (error) {
      toast(error.message, true);
    } finally {
      event.target.disabled = false;
    }
  });
  $("#calibrationProposals").addEventListener("click", async event => {
    const id = event.target.dataset.calibrationId;
    const status = event.target.dataset.calibrationStatus;
    if (!id || !status) return;
    event.target.disabled = true;
    try {
      await api(`/api/calibration-proposals/${encodeURIComponent(id)}`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({status})});
      toast(status === "approved" ? "הכיול אושר ויחול רק על תחזיות עתידיות" : "הצעת הכיול נדחתה");
      await loadLearningLedger();
    } catch (error) {
      toast(error.message, true);
      event.target.disabled = false;
    }
  });
  $("#insightResearchResults").addEventListener("click", event => {
    const title = event.target.dataset.askResearch;
    if (!title) return;
    showSection("agent");
    const question = $("#agentForm [name=question]");
    question.value = `נתח לעומק את תוצאות המחקר ${title}. הסבר את המספרים המדויקים, המשמעות לחברה, הסיכון, והמלץ על פעולות במסגרת התקציב עד Q9.`;
    question.focus();
  });
}

function bindSimulation() {
  $("#actionForm [name=code]").addEventListener("change", configureActionForm);
  $("#executionBlueprintRows").addEventListener("click", event => {
    const index = event.target.dataset.addBlueprint;
    if (index == null) return;
    const row = state.intelligence?.execution_blueprint?.rows?.[Number(index)];
    if (!row?.action) return;
    state.actions.push({...row.action, title: row.action_name || row.action.title});
    renderActionBasket();
    showSection("simulation");
    toast(`שלב ${row.order}: ${row.action_name} נוסף לסימולציה`);
  });
  $("#actionForm").addEventListener("submit", event => {
    event.preventDefault();
    const action = formPayload(event.target);
    const definition = selectedActionDefinition();
    if (!definition) return;
    action.type = definition.type;
    action.title = definition.title;
    if (definition.product) action.product = definition.product;
    if (!action.area && (definition.areas || []).length === 1) action.area = definition.areas[0];
    if (action.interest_rate) action.interest_rate = num(action.interest_rate) / 100;
    if (action.restricted != null) action.restricted = action.restricted === true || action.restricted === "true";
    state.actions.push(action);
    renderActionBasket();
  });
  $("#actionBasket").addEventListener("click", event => { const index = event.target.dataset.removeAction; if (index == null) return; state.actions.splice(Number(index), 1); renderActionBasket(); });
  $("#recommendationsList").addEventListener("click", event => {
    if (event.target.closest("[data-go-to-files]")) {
      showSection("files");
      return;
    }
    const simulateIndex = event.target.dataset.simulateRecommendation;
    const askIndex = event.target.dataset.askRecommendation;
    const logIndex = event.target.dataset.logRecommendation;
    const adoptIndex = event.target.dataset.adoptRecommendation;
    const saveTeamIndex = event.target.dataset.saveTeamRecommendation;
    if (simulateIndex != null) {
      const row = state.intelligence.recommendations[Number(simulateIndex)];
      state.actions.push({...row.action_template, title: row.title});
      renderActionBasket();
      showSection("simulation");
    }
    if (askIndex != null) {
      const row = state.intelligence.recommendations[Number(askIndex)];
      showSection("agent");
      $("#agentForm [name=question]").value = row.agent_prompt || `נתח את ההחלטה ${row.title} והשווה חלופות במסגרת התקציב.`;
      $("#agentForm [name=question]").focus();
    }
    if (adoptIndex != null || saveTeamIndex != null) {
      const index = Number(adoptIndex ?? saveTeamIndex);
      const row = state.intelligence.recommendations[index];
      const impact = row.economic_impact || {};
      const ai = row.ai_recommendation || {};
      const blueprintRows = (state.intelligence?.execution_blueprint?.rows || [])
        .filter(item => item.recommendation_id === row.id);
      const aiProposal = blueprintRows.length
        ? blueprintRows.slice(0, 3).map(item => `${item.form_code || "טופס"} · ${item.field_name || item.action_name}: ${item.recommended_value || "מותנה"}`).join(" | ")
        : (ai.verdict || "נדרש ניתוח נוסף");
      const input = $(`[data-team-proposal="${index}"]`, $("#recommendationsList"));
      const selectedOption = adoptIndex != null ? aiProposal : String(input?.value || "").trim();
      if (!selectedOption) return toast("יש להזין החלטת צוות", true);
      if (adoptIndex != null && input) input.value = aiProposal;
      const payload = {
        quarter: state.quarter,
        domain: row.domain || "אסטרטגיה",
        title: row.title,
        question: row.title,
        selected_option: selectedOption,
        rationale: adoptIndex != null
          ? `הצוות אימץ את הצעת ה-AI. ${ai.explanation || ""}`.trim()
          : "טיוטת צוות שנשמרה ישירות מחדר ההחלטות.",
        status: adoptIndex != null ? "מוכן לאישור" : "טיוטה",
        expected_result: `עלות ${sf(impact.cost_sf)}; שינוי רווח ${signedSf(impact.profit_delta_sf)}; שינוי מזומן ${signedSf(impact.cash_delta_sf)}; שינוי אומדן Q9 ${signedScore(impact.q9_score_delta)}.`,
        confidence: ai.confidence || "בינונית",
      };
      api("/api/decisions", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)})
        .then(async () => {
          toast(adoptIndex != null ? "הצעת ה-AI אומצה וממתינה לאישור בעל תפקיד" : "טיוטת הצוות נשמרה");
          await loadDecisionLog();
        })
        .catch(error => toast(error.message, true));
      return;
    }
    if (logIndex != null) {
      const row = state.intelligence.recommendations[Number(logIndex)];
      const impact = row.economic_impact || {};
      const ai = row.ai_recommendation || {};
      const payload = {
        quarter: state.quarter,
        domain: row.domain || "אסטרטגיה",
        title: row.title,
        question: row.title,
        selected_option: `המלצת המערכת: ${ai.verdict || "לבחינה"}`,
        rationale: [row.rationale, ai.explanation].filter(Boolean).join(" "),
        status: "טיוטה",
        expected_result: `עלות ${sf(impact.cost_sf)}; שינוי רווח ${signedSf(impact.profit_delta_sf)}; שינוי מזומן ${signedSf(impact.cash_delta_sf)}; שינוי אומדן Q9 ${signedScore(impact.q9_score_delta)}.`,
        confidence: ai.confidence || "בינונית",
      };
      api("/api/decisions", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)})
        .then(async () => { toast("ההמלצה נשמרה בטיוטת יומן ההחלטות"); await loadDecisionLog(); showSection("decisionlog"); })
        .catch(error => toast(error.message, true));
    }
  });
  $("#runSimulationButton").addEventListener("click", async () => { try { const result = await api(`/api/simulation/${state.quarter}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(simulationPayload())}); renderSimulation(result); } catch (error) { toast(error.message, true); } });
  $("#saveScenarioButton").addEventListener("click", async () => { if (!state.actions.length) return toast("יש להוסיף לפחות פעולה אחת", true); const name = prompt("שם התרחיש:", `תרחיש ${state.quarter}`); if (!name) return; try { await api("/api/scenario-portfolios", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({...simulationPayload(), name, quarter:state.quarter})}); toast("התרחיש נשמר"); await loadSavedScenarios(); } catch (error) { toast(error.message, true); } });
  $("#createDecisionPackButton").addEventListener("click", async () => {
    if (!state.actions.length) return toast("יש להוסיף לפחות פעולה אחת לחבילת ההחלטות", true);
    const name = prompt("שם חבילת ההחלטות:", `${state.quarter} · חבילת החלטות`);
    if (!name) return;
    try {
      const pack = await api("/api/decision-packs", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          quarter: state.quarter,
          name,
          actions: state.actions,
          recommendation: "טיוטה לבדיקת הצוות; אין שליחה אוטומטית ל-INTOPIA.",
        }),
      });
      const ready = pack.status === "ready_for_team_review";
      const readiness = pack.validation?.readiness || {};
      const requiredFixes = readiness.required_fixes || [];
      const link = `<a class="button ghost" href="/api/decision-packs/${encodeURIComponent(pack.id)}/export">הורדת חבילת JSON</a>`;
      $("#simulationResult").className = "";
      $("#simulationResult").innerHTML = `<div class="scenario-status ${ready ? "ok" : "bad"}">${esc(readiness.label || (ready ? "מוכן לבדיקת הצוות" : "חסום — נדרש תיקון"))}</div><p>Rulebook v${esc(pack.rulebook_version)} · ${esc(pack.quarter)} · ${esc(pack.name)}</p><div class="action-row">${link}</div>${requiredFixes.length ? `<div class="simulation-notes readiness-fixes"><strong>מה בדיוק לתקן לפני אישור</strong><ol>${requiredFixes.map(item => `<li>${esc(item)}</li>`).join("")}</ol></div>` : ""}${pack.validation?.violations?.length ? `<div class="simulation-notes"><strong>הפרות חוסמות</strong><ul>${pack.validation.violations.map(item => `<li>${esc(item.rule_id)} · ${esc(item.message)}</li>`).join("")}</ul></div>` : ""}`;
      toast(ready ? "חבילת ההחלטות מוכנה לבדיקת הצוות" : "החבילה חסומה; פירוט התיקונים מוצג", !ready);
    } catch (error) { toast(error.message, true); }
  });
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
  const instructions = $("#agentInstructions");
  instructions.value = localStorage.getItem("intopia-agent-instructions") || "";
  instructions.addEventListener("input", () => localStorage.setItem("intopia-agent-instructions", instructions.value));
  $$(".quick-prompts [data-agent-prompt]").forEach(button => button.addEventListener("click", () => {
    const question = $("#agentForm [name=question]");
    question.value = button.dataset.agentPrompt;
    question.focus();
  }));
  $("#agentUploadForm").addEventListener("submit", async event => {
    event.preventDefault();
    const button = $("button[type=submit]", event.target);
    button.disabled = true;
    button.textContent = "מעלה ומפענח…";
    try {
      const result = await api("/api/uploads", {method:"POST", body:new FormData(event.target)});
      event.target.reset();
      $("#agentUploadForm [name=quarter]").value = "Setup";
      toast("הקובץ פוענח. יש לאשר את הנתונים לפני שה-AI ישתמש בהם.");
      await loadUploads();
      const importRow = result.import_run;
      if (importRow) renderAgentImportStatus([importRow]);
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
      button.textContent = "העלאה ופענוח";
    }
  });
  $("#agentImportStatus").addEventListener("click", async event => {
    const id = event.target.dataset.agentCommitImport;
    if (!id) return;
    event.target.disabled = true;
    event.target.textContent = "מאשר…";
    try {
      const result = await api(`/api/imports/${encodeURIComponent(id)}/commit`, {method:"POST"});
      const count = Object.values(result.counts || {}).reduce((sum, value) => sum + Number(value || 0), 0);
      toast(`${count} פריטי מידע אושרו ונוספו למודל`);
      await loadCurrentQuarter();
      addAgentBubble("assistant", "הנתונים החדשים אושרו. אפשר לשאול אותי על המסמך, ההשפעה שלו על המצב ועל ההחלטות עד Q9.");
    } catch (error) {
      toast(error.message, true);
      await loadUploads();
    }
  });
  $("#agentForm").addEventListener("submit", async event => {
    event.preventDefault();
    const question = String(new FormData(event.target).get("question") || "").trim();
    if (!question) return;
    addAgentBubble("user", question);
    event.target.reset();
    const button = $("button", event.target); button.disabled = true; button.textContent = "מנתח…";
    try { const result = await api("/api/agent/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({question, quarter:state.quarter, thread_id:state.agentThreadId, manager_instructions: instructions.value.trim()})}); state.agentThreadId = result.thread_id; addAgentBubble("assistant", result.answer, result.sources || []); }
    catch (error) { addAgentBubble("assistant", `לא ניתן להפעיל את ה-Agent: ${error.message}`); }
    finally { button.disabled = false; button.textContent = "שליחה"; }
  });
}

function bindDecisionLog() {
  $("#decisionLogQuarter").addEventListener("change", () => renderDecisionLog(state.decisions || []));
  $("#decisionLogStatus").addEventListener("change", () => renderDecisionLog(state.decisions || []));
  $("#createGovernanceSession").addEventListener("click", async event => {
    event.currentTarget.disabled = true;
    try {
      const session = await api(`/api/governance/sessions/${encodeURIComponent(state.quarter)}`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({})});
      state.governanceSessions = [session, ...(state.governanceSessions || [])];
      renderGovernanceSession();
      toast("ישיבת ההחלטה נפתחה עם Snapshot של הנתונים והסל המומלץ");
    } catch (error) { toast(error.message, true); }
    finally { event.currentTarget.disabled = false; }
  });
  $("#governanceVoteForm").addEventListener("submit", async event => {
    event.preventDefault();
    const session = (state.governanceSessions || [])[0];
    if (!session) return;
    try {
      const updated = await api(`/api/governance/sessions/${encodeURIComponent(session.id)}/votes`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(formPayload(event.target))});
      state.governanceSessions[0] = updated;
      renderGovernanceSession();
      toast("עמדת הצוות נשמרה");
    } catch (error) { toast(error.message, true); }
  });
  $("#approveGovernanceSession").addEventListener("click", async () => {
    const session = (state.governanceSessions || [])[0];
    if (!session || !confirm("לאשר ולנעול את Snapshot הישיבה? הפעולה אינה שולחת החלטות ל־INTOPIA.")) return;
    try {
      const updated = await api(`/api/governance/sessions/${encodeURIComponent(session.id)}/approve`, {method:"POST"});
      state.governanceSessions[0] = updated;
      renderGovernanceSession();
      toast("הישיבה אושרה וננעלה לתיעוד");
    } catch (error) { toast(error.message, true); }
  });
  $("#newDecisionButton").addEventListener("click", () => {
    $("#manualDecisionPanel").open = true;
    $("#decisionForm [name=title]").focus();
  });
  $("#decisionForm").addEventListener("submit", async event => {
    event.preventDefault();
    const payload = formPayload(event.target);
    payload.quarter = payload.quarter || state.quarter;
    try {
      await api("/api/decisions", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
      event.target.reset();
      $("#decisionForm [name=quarter]").value = state.quarter;
      $("#manualDecisionPanel").open = false;
      toast("ההחלטה נוספה ליומן");
      await loadDecisionLog();
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("#decisionLogList").addEventListener("click", async event => {
    const id = event.target.dataset.saveDecision;
    if (!id) return;
    const card = event.target.closest("[data-decision-id]");
    const payload = {};
    $$("[data-decision-field]", card).forEach(input => { payload[input.dataset.decisionField] = input.value; });
    event.target.disabled = true;
    event.target.textContent = "שומר…";
    try {
      await api(`/api/decisions/${encodeURIComponent(id)}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
      toast("עדכון ההחלטה נשמר");
      await loadDecisionLog();
    } catch (error) {
      toast(error.message, true);
      event.target.disabled = false;
      event.target.textContent = "שמירת עדכון";
    }
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
  $("#financeToSelect").value = state.quarter;
  const modules = [
    ["חדר החלטות", loadIntelligence],
    ["אופטימיזציית אסטרטגיה", loadStrategyOptimization],
    ["קבצים וקליטות", loadUploads],
    ["דוחות", loadReports],
    ["מחקרי שוק", loadResearch],
    ["תרחישים שמורים", loadSavedScenarios],
    ["תובנות", loadInsights],
    ["יומן למידה", loadLearningLedger],
    ["לוג החלטות ואישור קבוצתי", loadDecisionLog],
    ["מצב פיננסי", loadFinanceRange],
  ];
  const results = await Promise.allSettled(modules.map(([, loader]) => loader()));
  const failures = results
    .map((result, index) => ({result, label: modules[index][0]}))
    .filter(({result}) => result.status === "rejected");
  if (!failures.length) {
    saveStatus("saved", "מחובר ונשמר בענן");
    return;
  }
  const failedLabels = failures.map(({label}) => label).join(", ");
  const firstMessage = failures[0].result.reason?.message || "שגיאת שרת לא מזוהה";
  saveStatus("error", `טעינה חלקית · ${failures.length} רכיבים נכשלו`);
  console.error("Quarter modules failed", failures);
  toast(`לא נטענו: ${failedLabels}. ${firstMessage}`, true);
}

async function initialize() {
  bindNavigation(); bindStrategyOptimization(); bindSettingsAndQuarter(); bindFiles(); bindFinance(); bindReportsAndResearch(); bindSimulation(); bindEconomics(); bindAgent(); bindDecisionLog(); bindBackup(); bindRules();
  $("#refreshButton").addEventListener("click", loadCurrentQuarter);
  try {
    await loadHealth();
    state.meta = await api("/api/meta");
    const settings = await loadSettings();
    renderQuarterPicker();
    fillSelect($("#settingsForm [name=startup_quarter]"), state.meta.quarters, settings.startup_quarter || "Q4");
    fillSelect($("#uploadForm [name=quarter]"), ["Setup", ...state.meta.quarters], "Setup");
    $("#uploadForm [name=quarter] option[value=Setup]").textContent = "זיהוי רבעון אוטומטי";
    fillSelect($("#uploadForm [name=category]"), state.meta.upload_categories, "פלט רבעוני");
    fillSelect($("#agentUploadForm [name=category]"), state.meta.upload_categories, "פלט רבעוני");
    fillSelect($("#financeFromSelect"), state.meta.quarters, "Q1");
    fillSelect($("#financeToSelect"), state.meta.quarters, state.quarter);
    $("#financeFromSelect").disabled = true;
    fillSelect($("#decisionLogQuarter"), state.meta.quarters, "", true);
    $("#decisionLogQuarter option[value='']").textContent = "כל הרבעונים";
    fillSelect($("#decisionForm [name=quarter]"), state.meta.quarters, state.quarter);
    fillSelect($("#actionForm [name=area]"), state.meta.areas, "", true);
    fillSelect($("#actionForm [name=target_area]"), state.meta.areas, "", true);
    fillSelect($("#actionForm [name=product]"), state.meta.products, "", true);
    fillSelect($("#actionForm [name=model]"), state.meta.models, "", true);
    fillSelect($("#actionForm [name=payment_quarter]"), state.meta.quarters, "Q9", true);
    const actionSelect = $("#actionForm [name=code]");
    actionSelect.innerHTML = (state.meta.decision_actions || []).map(item => `<option value="${esc(item.code)}">${esc(item.code)} · ${esc(item.title)} — ${esc(item.category)}</option>`).join("");
    configureActionForm();
    installFieldAdvice();
    renderActionBasket();
    await Promise.all([loadCurrentQuarter(), loadAgentStatus(), loadRulebook()]);
  } catch (error) {
    saveStatus("error", "המערכת אינה מוכנה");
    toast(error.message, true);
  }
}

document.addEventListener("DOMContentLoaded", initialize);
