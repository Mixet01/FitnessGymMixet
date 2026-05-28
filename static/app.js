(function () {
  const state = {
    me: null,
    activityLevels: [],
    dietGoals: [],
    macroPresets: [],
    profile: {},
    latestPlan: null,
    plans: [],
    checkins: [],
    activeScreen: "screen-dashboard",
    preview: null,
    googleInitialized: false,
    refreshPromise: null,
    toastTimer: null,
  };

  const defaultDraft = {
    sex: "male",
    age_years: "30",
    height_cm: "175",
    weight_kg: "74",
    activity_key: "moderate",
    bf_method: "auto",
    body_fat_manual: "",
    waist_cm: "",
    neck_cm: "",
    hips_cm: "",
    diet_goal: "maintenance",
    ideal_weight_kg: "",
    target_body_fat_percent: "",
    macro_preset: "balanced",
    protein_g_per_kg: "1.8",
    fat_g_per_kg: "0.8",
    goal_note: "",
  };

  const els = {
    body: document.body,
    bootSplash: document.getElementById("boot-splash"),
    authGate: document.getElementById("auth-gate"),
    appShell: document.getElementById("app-shell"),
    googleSignin: document.getElementById("google-signin"),
    devName: document.getElementById("dev-name"),
    devEmail: document.getElementById("dev-email"),
    devLogin: document.getElementById("dev-login"),
    welcomeName: document.getElementById("welcome-name"),
    headerSubtitle: document.getElementById("header-subtitle"),
    syncChip: document.getElementById("sync-chip"),
    generateFromHeader: document.getElementById("generate-from-header"),
    calcSaveBtn: document.getElementById("calc-save-btn"),
    metricBmi: document.getElementById("metric-bmi"),
    metricBmiNote: document.getElementById("metric-bmi-note"),
    metricBmr: document.getElementById("metric-bmr"),
    metricTdee: document.getElementById("metric-tdee"),
    metricBf: document.getElementById("metric-bf"),
    metricIdealWeight: document.getElementById("metric-ideal-weight"),
    metricCalories: document.getElementById("metric-calories"),
    metricTargetBf: document.getElementById("metric-target-bf"),
    bfMethodChip: document.getElementById("bf-method-chip"),
    planSummary: document.getElementById("plan-summary"),
    activityChip: document.getElementById("activity-chip"),
    dietStatusChip: document.getElementById("diet-status-chip"),
    dietProtein: document.getElementById("diet-protein"),
    dietProteinNote: document.getElementById("diet-protein-note"),
    dietFat: document.getElementById("diet-fat"),
    dietFatNote: document.getElementById("diet-fat-note"),
    dietCarbs: document.getElementById("diet-carbs"),
    dietCarbsNote: document.getElementById("diet-carbs-note"),
    dietGoal: document.getElementById("diet-goal"),
    dietGoalNote: document.getElementById("diet-goal-note"),
    warningList: document.getElementById("warning-list"),
    profileAvatar: document.getElementById("profile-avatar"),
    profileName: document.getElementById("profile-name"),
    profileEmail: document.getElementById("profile-email"),
    profileWeight: document.getElementById("profile-weight"),
    profileBf: document.getElementById("profile-bf"),
    profileTarget: document.getElementById("profile-target"),
    profileActivity: document.getElementById("profile-activity"),
    checkinDateInput: document.getElementById("checkin-date-input"),
    checkinWeightInput: document.getElementById("checkin-weight-input"),
    checkinBfInput: document.getElementById("checkin-bf-input"),
    checkinNoteInput: document.getElementById("checkin-note-input"),
    saveCheckinBtn: document.getElementById("save-checkin-btn"),
    exportCsvBtn: document.getElementById("export-csv-btn"),
    logoutBtn: document.getElementById("logout-btn"),
    planHistoryList: document.getElementById("plan-history-list"),
    checkinList: document.getElementById("checkin-list"),
    bfHint: document.getElementById("bf-hint"),
    bfManualBlock: document.getElementById("bf-manual-block"),
    bfNavyBlock: document.getElementById("bf-navy-block"),
    activitySelect: document.getElementById("activity-select"),
    dietGoalSelect: document.getElementById("diet-goal-select"),
    bfMethodSelect: document.getElementById("bf-method-select"),
    bodyFatManualInput: document.getElementById("body-fat-manual-input"),
    waistInput: document.getElementById("waist-input"),
    neckInput: document.getElementById("neck-input"),
    hipsInput: document.getElementById("hips-input"),
    targetBfInput: document.getElementById("target-bf-input"),
    idealWeightInput: document.getElementById("ideal-weight-input"),
    macroPresetSelect: document.getElementById("macro-preset-select"),
    proteinInput: document.getElementById("protein-input"),
    fatInput: document.getElementById("fat-input"),
    goalNoteInput: document.getElementById("goal-note-input"),
    sexSelect: document.getElementById("sex-select"),
    ageInput: document.getElementById("age-input"),
    heightInput: document.getElementById("height-input"),
    weightInput: document.getElementById("weight-input"),
    navButtons: Array.from(document.querySelectorAll(".nav-btn")),
    screens: Array.from(document.querySelectorAll(".screen")),
    fabCalc: document.getElementById("fab-calc"),
    toast: document.getElementById("toast"),
  };

  const googleClientId = (els.body.dataset.googleClientId || "").trim();
  const appName = (els.body.dataset.pwaAppName || "Fitness Gym Mixet").trim();
  const assetVersion = (els.body.dataset.assetVersion || "2026-05-28-fit-2").trim();
  const currencyFormatter = new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 });
  const oneDecimalFormatter = new Intl.NumberFormat("it-IT", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const twoDecimalFormatter = new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const shortDateFormatter = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "2-digit", year: "numeric" });
  const dateTimeFormatter = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatNumber(value, decimals = 1) {
    const num = Number(value || 0);
    if (decimals === 0) return currencyFormatter.format(num);
    if (decimals === 2) return twoDecimalFormatter.format(num);
    return oneDecimalFormatter.format(num);
  }

  function formatWeight(value) { return `${formatNumber(value, 1)} kg`; }
  function formatPercent(value) { return `${formatNumber(value, 1)}%`; }
  function formatCalories(value) { return `${formatNumber(value, 0)} kcal`; }

  function formatDate(value) {
    if (!value) return "-";
    const dateObj = new Date(`${value}T12:00:00`);
    if (Number.isNaN(dateObj.getTime())) return String(value);
    return shortDateFormatter.format(dateObj);
  }

  function formatDateTime(value) {
    if (!value) return "-";
    const normalized = String(value).includes("T") ? value : `${value}T00:00:00`;
    const dateObj = new Date(normalized);
    if (Number.isNaN(dateObj.getTime())) return String(value);
    return dateTimeFormatter.format(dateObj);
  }

  function avatarText(user) {
    const base = String((user && (user.name || user.email)) || appName).trim();
    const cleaned = base.replace(/[^A-Za-z0-9 ]/g, " ").trim();
    const initials = cleaned
      .split(/\s+/)
      .filter(Boolean)
      .map((part) => part[0])
      .join("");
    return (initials.slice(0, 3) || cleaned.slice(0, 2) || "FG").toUpperCase();
  }

  function api(url, options = {}) {
    const timeoutMs = Number(options.timeoutMs || 12000);
    const fetchOptions = { ...options, cache: "no-store" };
    delete fetchOptions.timeoutMs;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    fetchOptions.signal = controller.signal;
    return fetch(url, fetchOptions)
      .then(async (response) => {
        window.clearTimeout(timeoutId);
        let data = null;
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) data = await response.json();
        if (!response.ok) {
          if (response.status === 401) {
            state.me = null;
            showGate("auth");
            initGoogleSignIn();
          }
          throw new Error((data && data.message) || "Operazione non riuscita.");
        }
        return data;
      })
      .catch((err) => {
        window.clearTimeout(timeoutId);
        if (err && err.name === "AbortError") {
          throw new Error("La richiesta ha impiegato troppo tempo. Riprova tra poco.");
        }
        throw err;
      });
  }

  function showToast(message, tone = "info") {
    if (!els.toast) return;
    clearTimeout(state.toastTimer);
    els.toast.textContent = message;
    els.toast.classList.remove("hidden", "success", "warn", "danger");
    els.toast.classList.add(tone);
    state.toastTimer = window.setTimeout(() => els.toast.classList.add("hidden"), 3200);
  }

  function showGate(mode) {
    els.authGate.classList.toggle("hidden", mode !== "auth");
    els.appShell.classList.toggle("hidden", mode !== "app");
  }

  function hideBootSplash() { els.bootSplash.classList.add("hidden"); }

  function setActiveScreen(screenId) {
    state.activeScreen = screenId;
    els.screens.forEach((screen) => screen.classList.toggle("active", screen.id === screenId));
    els.navButtons.forEach((button) => button.classList.toggle("active", button.dataset.screen === screenId));
  }

  function persistDraft() {
    localStorage.setItem("fitness-gym-mixet-draft", JSON.stringify(readFormDraft()));
  }

  function loadDraft() {
    try {
      const raw = localStorage.getItem("fitness-gym-mixet-draft") || localStorage.getItem("fit-mixet-draft");
      if (!raw) return { ...defaultDraft };
      return { ...defaultDraft, ...JSON.parse(raw) };
    } catch (_) {
      return { ...defaultDraft };
    }
  }

  function profileToDraft(profile) {
    if (!profile || typeof profile !== "object") return {};
    return {
      sex: profile.sex || defaultDraft.sex,
      age_years: profile.age_years != null ? String(profile.age_years) : defaultDraft.age_years,
      height_cm: profile.height_cm != null ? String(profile.height_cm) : defaultDraft.height_cm,
      weight_kg: profile.weight_kg != null ? String(profile.weight_kg) : defaultDraft.weight_kg,
      activity_key: profile.activity_key || defaultDraft.activity_key,
      bf_method: profile.bf_method || defaultDraft.bf_method,
      body_fat_manual: profile.body_fat_manual != null ? String(profile.body_fat_manual) : defaultDraft.body_fat_manual,
      waist_cm: profile.waist_cm != null ? String(profile.waist_cm) : defaultDraft.waist_cm,
      neck_cm: profile.neck_cm != null ? String(profile.neck_cm) : defaultDraft.neck_cm,
      hips_cm: profile.hips_cm != null ? String(profile.hips_cm) : defaultDraft.hips_cm,
      diet_goal: profile.diet_goal || defaultDraft.diet_goal,
      ideal_weight_kg: profile.ideal_weight_kg != null ? String(profile.ideal_weight_kg) : defaultDraft.ideal_weight_kg,
      target_body_fat_percent: profile.target_body_fat_percent != null ? String(profile.target_body_fat_percent) : defaultDraft.target_body_fat_percent,
      macro_preset: profile.macro_preset || defaultDraft.macro_preset,
      protein_g_per_kg: profile.protein_g_per_kg != null ? String(profile.protein_g_per_kg) : defaultDraft.protein_g_per_kg,
      fat_g_per_kg: profile.fat_g_per_kg != null ? String(profile.fat_g_per_kg) : defaultDraft.fat_g_per_kg,
      goal_note: profile.goal_note || defaultDraft.goal_note,
    };
  }

  function readFormDraft() {
    return {
      sex: els.sexSelect.value,
      age_years: els.ageInput.value.trim(),
      height_cm: els.heightInput.value.trim(),
      weight_kg: els.weightInput.value.trim(),
      activity_key: els.activitySelect.value,
      bf_method: els.bfMethodSelect.value,
      body_fat_manual: els.bodyFatManualInput.value.trim(),
      waist_cm: els.waistInput.value.trim(),
      neck_cm: els.neckInput.value.trim(),
      hips_cm: els.hipsInput.value.trim(),
      diet_goal: els.dietGoalSelect.value,
      ideal_weight_kg: els.idealWeightInput.value.trim(),
      target_body_fat_percent: els.targetBfInput.value.trim(),
      macro_preset: els.macroPresetSelect.value,
      protein_g_per_kg: els.proteinInput.value.trim(),
      fat_g_per_kg: els.fatInput.value.trim(),
      goal_note: els.goalNoteInput.value.trim(),
    };
  }

  function applyDraftToForm(draft) {
    const data = { ...defaultDraft, ...draft };
    els.sexSelect.value = data.sex || "male";
    els.ageInput.value = data.age_years || "";
    els.heightInput.value = data.height_cm || "";
    els.weightInput.value = data.weight_kg || "";
    els.activitySelect.value = data.activity_key || "moderate";
    els.bfMethodSelect.value = data.bf_method || "auto";
    els.bodyFatManualInput.value = data.body_fat_manual || "";
    els.waistInput.value = data.waist_cm || "";
    els.neckInput.value = data.neck_cm || "";
    els.hipsInput.value = data.hips_cm || "";
    els.dietGoalSelect.value = data.diet_goal || "maintenance";
    els.idealWeightInput.value = data.ideal_weight_kg || "";
    els.targetBfInput.value = data.target_body_fat_percent || "";
    els.macroPresetSelect.value = data.macro_preset || "balanced";
    els.proteinInput.value = data.protein_g_per_kg || "";
    els.fatInput.value = data.fat_g_per_kg || "";
    els.goalNoteInput.value = data.goal_note || "";
    updateBfVisibility();
    updateActivityChip();
  }

  function populateSelect(select, items, getter, labeler = null) {
    select.innerHTML = items.map((item) => {
      const value = getter(item);
      const label = labeler ? labeler(item, value) : item.label || item.name || value;
      return `<option value="${escapeHtml(String(value))}">${escapeHtml(label)}</option>`;
    }).join("");
  }

  function updateActivitySelect() {
    populateSelect(
      els.activitySelect,
      state.activityLevels,
      (item) => item.key,
      (item) => `${item.label} (${item.factor.toFixed(3)})`
    );
    const current = state.profile.activity_key || loadDraft().activity_key || "moderate";
    els.activitySelect.value = current;
  }

  function updateDietGoalSelect() {
    populateSelect(
      els.dietGoalSelect,
      state.dietGoals,
      (item) => item.key,
      (item) => `${item.label} (${item.adjustment_percent > 0 ? "+" : ""}${item.adjustment_percent}%)`
    );
    const current = state.profile.diet_goal || loadDraft().diet_goal || "maintenance";
    els.dietGoalSelect.value = current;
  }

  function updateMacroPresetSelect() {
    populateSelect(els.macroPresetSelect, state.macroPresets, (item) => item.key);
    const current = state.profile.macro_preset || loadDraft().macro_preset || "balanced";
    els.macroPresetSelect.value = current;
  }

  function updateMacroPresetFields(force = true) {
    const preset = state.macroPresets.find((item) => item.key === els.macroPresetSelect.value) || state.macroPresets[0];
    if (!preset) return;
    if (force || !els.proteinInput.value.trim()) els.proteinInput.value = preset.protein_g_per_kg;
    if (force || !els.fatInput.value.trim()) els.fatInput.value = preset.fat_g_per_kg;
  }

  function updateActivityChip() {
    const selected = state.activityLevels.find((item) => item.key === els.activitySelect.value) || state.activityLevels[2];
    if (!selected) return;
    els.activityChip.textContent = `Attività: ${selected.label} (${selected.factor.toFixed(3)})`;
  }

  function updateBfVisibility() {
    const mode = els.bfMethodSelect.value;
    els.bfManualBlock.classList.toggle("hidden", mode !== "manual");
    els.bfNavyBlock.classList.toggle("hidden", mode === "manual");
    if (mode === "navy") {
      els.bfHint.textContent = "Per Navy servono vita, collo e, per le donne, anche i fianchi.";
    } else if (mode === "manual") {
      els.bfHint.textContent = "Inserisci il tuo BF attuale e l'app userà quel valore.";
    } else {
      els.bfHint.textContent = "Automatico usa Navy se hai le misure, altrimenti una stima BMI.";
    }
  }

  function bmiCategory(value) {
    if (value < 18.5) return "Sottopeso";
    if (value < 25) return "Normale";
    if (value < 30) return "Sovrappeso";
    return "Obesita";
  }

  function parseNum(value) {
    const raw = String(value ?? "").trim().replace(",", ".");
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function computeLocalPlan(input) {
    const sex = String(input.sex || "").trim().toLowerCase();
    const ageYears = clamp(parseNum(input.age_years) ?? 0, 14, 99);
    const heightCm = clamp(parseNum(input.height_cm) ?? 0, 120, 230);
    const weightKg = clamp(parseNum(input.weight_kg) ?? 0, 30, 400);
    const targetBf = clamp(parseNum(input.target_body_fat_percent) ?? 0, 3, 60);
    const targetWeeks = clamp(Math.round(parseNum(input.target_weeks) ?? 0), 1, 156);
    const mealsPerDay = clamp(Math.round(parseNum(input.meals_per_day) ?? 4), 2, 8);
    const activityItem = state.activityLevels.find((item) => item.key === input.activity_key) || state.activityLevels[2] || { key: "moderate", label: "Moderato", factor: 1.55 };
    const activityFactor = clamp(parseNum(input.activity_factor) ?? activityItem.factor, 1.1, 2.5);
    const preset = state.macroPresets.find((item) => item.key === input.macro_preset) || state.macroPresets[0] || { key: "balanced", label: "Bilanciata", protein_g_per_kg: 1.8, fat_g_per_kg: 0.8 };
    const proteinFactor = clamp(parseNum(input.protein_g_per_kg) ?? preset.protein_g_per_kg, 0.8, 3.5);
    const fatFactor = clamp(parseNum(input.fat_g_per_kg) ?? preset.fat_g_per_kg, 0.3, 2.0);
    const bfMethod = String(input.bf_method || "auto").trim().toLowerCase();
    const manualBf = parseNum(input.body_fat_manual);
    const waist = parseNum(input.waist_cm);
    const neck = parseNum(input.neck_cm);
    const hips = parseNum(input.hips_cm);
    const canNavy = sex && waist != null && neck != null && (sex === "male" || hips != null);

    if (!sex || !ageYears || !heightCm || !weightKg || !targetWeeks || !targetBf) {
      return { ready: false, warnings: [] };
    }

    let bodyFatPercent;
    let bodyFatMethod;
    let bodyFatLabel;
    let bodyFatDetails;

    if (bfMethod === "manual") {
      if (manualBf == null) return { ready: false, warnings: ["Inserisci la BF manuale."] };
      bodyFatPercent = clamp(manualBf, 3, 80);
      bodyFatMethod = "manuale";
      bodyFatLabel = "BF manuale";
      bodyFatDetails = "Valore inserito manualmente.";
    } else if (bfMethod === "navy" || (bfMethod === "auto" && canNavy)) {
      if (!canNavy) return { ready: false, warnings: ["Completa i campi Navy per calcolare la BF."] };
      const heightIn = heightCm / 2.54;
      const waistIn = waist / 2.54;
      const neckIn = neck / 2.54;
      if (sex === "male") {
        const diff = waistIn - neckIn;
        if (diff <= 0) return { ready: false, warnings: ["Le misure Navy non sono coerenti."] };
        bodyFatPercent = 86.01 * Math.log10(diff) - 70.041 * Math.log10(heightIn) + 36.76;
      } else {
        const hipIn = hips / 2.54;
        const diff = waistIn + hipIn - neckIn;
        if (diff <= 0) return { ready: false, warnings: ["Le misure Navy non sono coerenti."] };
        bodyFatPercent = 163.205 * Math.log10(diff) - 97.684 * Math.log10(heightIn) - 78.387;
      }
      bodyFatMethod = "navy";
      bodyFatLabel = "Metodo Navy";
      bodyFatDetails = "Stima da circonferenze.";
    } else {
      const bmi = weightKg / Math.pow(heightCm / 100, 2);
      const sexFlag = sex === "male" ? 1 : 0;
      bodyFatPercent = 1.2 * bmi + 0.23 * ageYears - 10.8 * sexFlag - 5.4;
      bodyFatMethod = "estimate";
      bodyFatLabel = "Stima BMI";
      bodyFatDetails = "Stima automatica basata su BMI, età e sesso.";
    }

    bodyFatPercent = clamp(bodyFatPercent, 3, 80);
    const bmi = weightKg / Math.pow(heightCm / 100, 2);
    const bmr = sex === "male" ? 10 * weightKg + 6.25 * heightCm - 5 * ageYears + 5 : 10 * weightKg + 6.25 * heightCm - 5 * ageYears - 161;
    const tdee = bmr * activityFactor;
    const leanMass = weightKg * (1 - bodyFatPercent / 100);
    const fatMass = weightKg - leanMass;
    const targetWeight = leanMass / (1 - targetBf / 100);
    const weightDelta = targetWeight - weightKg;
    const dailyDelta = Math.abs(weightDelta) * 7700 / (targetWeeks * 7);
    let calorieTarget = tdee;
    let direction = "mantenimento";
    if (Math.abs(weightDelta) >= 0.05) {
      direction = weightDelta < 0 ? "deficit" : "surplus";
      calorieTarget = weightDelta < 0 ? tdee - dailyDelta : tdee + dailyDelta;
    }
    calorieTarget = Math.max(0, calorieTarget);
    const weeklyChangeKg = weightDelta / targetWeeks;
    const weeklyChangePct = Math.abs(weeklyChangeKg) / weightKg * 100;
    const proteinG = proteinFactor * (direction === "deficit" ? leanMass : weightKg);
    const fatG = fatFactor * weightKg;
    const proteinKcal = proteinG * 4;
    const fatKcal = fatG * 9;
    let carbsKcal = calorieTarget - proteinKcal - fatKcal;
    let carbsG = carbsKcal > 0 ? carbsKcal / 4 : 0;
    if (carbsKcal < 0) {
      carbsKcal = 0;
      carbsG = 0;
    }
    const mealCalories = calorieTarget / mealsPerDay;
    const mealProtein = proteinG / mealsPerDay;
    const mealFat = fatG / mealsPerDay;
    const mealCarbs = carbsG / mealsPerDay;

    const warnings = [];
    if (dailyDelta > tdee * 0.25) warnings.push("Il deficit/surplus richiesto e molto aggressivo.");
    if (calorieTarget < (sex === "male" ? 1500 : 1200)) warnings.push("Le calorie stimate scendono molto in basso: valuta piu tempo o un target BF meno spinto.");
    if (weeklyChangePct > 1.25) warnings.push("La velocita settimanale stimata e alta.");
    if (bodyFatMethod === "estimate") warnings.push("La BF e stimata dal BMI: se puoi, inserisci le circonferenze o un valore manuale.");

    return {
      ready: true,
      inputs: {
        sex,
        age_years: ageYears,
        height_cm: heightCm,
        weight_kg: weightKg,
        activity_key: activityItem.key,
        activity_label: activityItem.label,
        activity_factor: activityFactor,
        bf_method: bfMethod,
        body_fat_manual: manualBf,
        waist_cm: waist,
        neck_cm: neck,
        hips_cm: hips,
        target_body_fat_percent: targetBf,
        target_weeks: targetWeeks,
        meals_per_day: mealsPerDay,
        macro_preset: preset.key,
        protein_g_per_kg: proteinFactor,
        fat_g_per_kg: fatFactor,
        goal_note: input.goal_note || "",
      },
      metrics: {
        bmi,
        bmi_category: bmiCategory(bmi),
        bmr,
        tdee,
        body_fat_percent: bodyFatPercent,
        body_fat_method: bodyFatMethod,
        body_fat_label: bodyFatLabel,
        body_fat_details: bodyFatDetails,
        lean_mass_kg: leanMass,
        fat_mass_kg: fatMass,
        target_weight_kg: targetWeight,
        weight_delta_kg: weightDelta,
        weekly_change_kg: weeklyChangeKg,
        weekly_change_percent: weeklyChangePct,
        daily_calorie_delta: dailyDelta,
        calorie_target: calorieTarget,
        direction,
      },
      macros: {
        preset,
        protein_g: proteinG,
        protein_kcal: proteinKcal,
        fat_g: fatG,
        fat_kcal: fatKcal,
        carbs_g: carbsG,
        carbs_kcal: carbsKcal,
        meals_per_day: mealsPerDay,
        per_meal: {
          calories: mealCalories,
          protein_g: mealProtein,
          fat_g: mealFat,
          carbs_g: mealCarbs,
        },
      },
      warnings,
      summary: `Obiettivo: arrivare al ${formatPercent(targetBf)} in ${targetWeeks} settimane con ${formatCalories(calorieTarget)}.`,
    };
  }

  function computeLocalPlan(input) {
    const sex = String(input.sex || "").trim().toLowerCase();
    const ageYears = clamp(parseNum(input.age_years) ?? 0, 14, 99);
    const heightCm = clamp(parseNum(input.height_cm) ?? 0, 120, 230);
    const weightKg = clamp(parseNum(input.weight_kg) ?? 0, 30, 400);
    const activityItem = state.activityLevels.find((item) => item.key === input.activity_key) || state.activityLevels[2] || { key: "moderate", label: "Moderato", factor: 1.55 };
    const dietGoal = state.dietGoals.find((item) => item.key === input.diet_goal) || state.dietGoals[0] || { key: "maintenance", label: "Mantenimento", adjustment_percent: 0, direction: "mantenimento" };
    const idealWeightKg = parseNum(input.ideal_weight_kg);
    const targetBf = parseNum(input.target_body_fat_percent);
    const preset = state.macroPresets.find((item) => item.key === input.macro_preset) || state.macroPresets[0] || { key: "balanced", label: "Bilanciata", protein_g_per_kg: 1.8, fat_g_per_kg: 0.8 };
    const proteinFactor = clamp(parseNum(input.protein_g_per_kg) ?? preset.protein_g_per_kg, 0.8, 3.5);
    const fatFactor = clamp(parseNum(input.fat_g_per_kg) ?? preset.fat_g_per_kg, 0.3, 2.0);
    const bfMethod = String(input.bf_method || "auto").trim().toLowerCase();
    const manualBf = parseNum(input.body_fat_manual);
    const waist = parseNum(input.waist_cm);
    const neck = parseNum(input.neck_cm);
    const hips = parseNum(input.hips_cm);
    const canNavy = sex && waist != null && neck != null && (sex === "male" || hips != null);

    if (!sex || !ageYears || !heightCm || !weightKg) {
      return { ready: false, warnings: [] };
    }

    let bodyFatPercent;
    let bodyFatMethod;
    let bodyFatLabel;
    let bodyFatDetails;

    if (bfMethod === "manual") {
      if (manualBf == null) return { ready: false, warnings: ["Inserisci la BF manuale."] };
      bodyFatPercent = clamp(manualBf, 3, 80);
      bodyFatMethod = "manuale";
      bodyFatLabel = "BF manuale";
      bodyFatDetails = "Valore inserito manualmente.";
    } else if (bfMethod === "navy" || (bfMethod === "auto" && canNavy)) {
      if (!canNavy) return { ready: false, warnings: ["Completa i campi Navy per calcolare la BF."] };
      const heightIn = heightCm / 2.54;
      const waistIn = waist / 2.54;
      const neckIn = neck / 2.54;
      if (sex === "male") {
        const diff = waistIn - neckIn;
        if (diff <= 0) return { ready: false, warnings: ["Le misure Navy non sono coerenti."] };
        bodyFatPercent = 86.01 * Math.log10(diff) - 70.041 * Math.log10(heightIn) + 36.76;
      } else {
        const hipIn = hips / 2.54;
        const diff = waistIn + hipIn - neckIn;
        if (diff <= 0) return { ready: false, warnings: ["Le misure Navy non sono coerenti."] };
        bodyFatPercent = 163.205 * Math.log10(diff) - 97.684 * Math.log10(heightIn) - 78.387;
      }
      bodyFatMethod = "navy";
      bodyFatLabel = "Metodo Navy";
      bodyFatDetails = "Stima da circonferenze.";
    } else {
      const bmi = weightKg / Math.pow(heightCm / 100, 2);
      const sexFlag = sex === "male" ? 1 : 0;
      bodyFatPercent = 1.2 * bmi + 0.23 * ageYears - 10.8 * sexFlag - 5.4;
      bodyFatMethod = "estimate";
      bodyFatLabel = "Stima BMI";
      bodyFatDetails = "Stima automatica basata su BMI, eta e sesso.";
    }

    bodyFatPercent = clamp(bodyFatPercent, 3, 80);
    const bmi = weightKg / Math.pow(heightCm / 100, 2);
    const bmr = sex === "male" ? 10 * weightKg + 6.25 * heightCm - 5 * ageYears + 5 : 10 * weightKg + 6.25 * heightCm - 5 * ageYears - 161;
    const activityFactor = activityItem.factor;
    const tdee = bmr * activityFactor;
    const leanMass = weightKg * (1 - bodyFatPercent / 100);
    const fatMass = weightKg - leanMass;
    const targetWeightFromBf = targetBf != null ? leanMass / (1 - targetBf / 100) : null;
    const displayIdealWeight = idealWeightKg != null ? idealWeightKg : targetWeightFromBf;
    const calorieTarget = Math.max(0, tdee * (1 + (dietGoal.adjustment_percent / 100)));
    const dailyDelta = calorieTarget - tdee;
    const direction = dietGoal.direction;
    const weeklyChangeKg = dailyDelta * 7 / 7700;
    const weeklyChangePct = Math.abs(weeklyChangeKg) / weightKg * 100;
    const proteinG = proteinFactor * (direction === "deficit" ? leanMass : weightKg);
    const fatG = fatFactor * weightKg;
    const proteinKcal = proteinG * 4;
    const fatKcal = fatG * 9;
    let carbsKcal = calorieTarget - proteinKcal - fatKcal;
    let carbsG = carbsKcal > 0 ? carbsKcal / 4 : 0;
    if (carbsKcal < 0) {
      carbsKcal = 0;
      carbsG = 0;
    }

    const warnings = [];
    if (Math.abs(dietGoal.adjustment_percent) >= 20) warnings.push("Il piano e aggressivo: monitora energia e recupero.");
    if (calorieTarget < (sex === "male" ? 1500 : 1200)) warnings.push("Le calorie stimate scendono molto in basso: valuta piu tempo o un target BF meno spinto.");
    if (weeklyChangePct > 1.25) warnings.push("La velocita settimanale stimata e alta.");
    if (bodyFatMethod === "estimate") warnings.push("La BF e stimata dal BMI: se puoi, inserisci le circonferenze o un valore manuale.");

    const summaryParts = [`Obiettivo: ${dietGoal.label} a ${formatCalories(calorieTarget)}.`];
    if (displayIdealWeight != null) summaryParts.push(`Peso ideale ${formatWeight(displayIdealWeight)}.`);
    if (targetBf != null) summaryParts.push(`Target BF ${formatPercent(targetBf)}.`);

    return {
      ready: true,
      inputs: {
        sex,
        age_years: ageYears,
        height_cm: heightCm,
        weight_kg: weightKg,
        activity_key: activityItem.key,
        activity_label: activityItem.label,
        activity_factor: Math.round(activityFactor * 1000) / 1000,
        diet_goal: dietGoal.key,
        diet_goal_label: dietGoal.label,
        diet_goal_adjustment_percent: dietGoal.adjustment_percent,
        bf_method: bfMethod,
        body_fat_manual: manualBf,
        waist_cm: waist,
        neck_cm: neck,
        hips_cm: hips,
        ideal_weight_kg: idealWeightKg,
        target_body_fat_percent: targetBf,
        macro_preset: preset.key,
        protein_g_per_kg: proteinFactor,
        fat_g_per_kg: fatFactor,
        goal_note: input.goal_note || "",
      },
      metrics: {
        bmi,
        bmi_category: bmiCategory(bmi),
        bmr,
        tdee,
        body_fat_percent: bodyFatPercent,
        body_fat_method: bodyFatMethod,
        body_fat_label: bodyFatLabel,
        body_fat_details: bodyFatDetails,
        lean_mass_kg: leanMass,
        fat_mass_kg: fatMass,
        ideal_weight_kg: displayIdealWeight != null ? displayIdealWeight : null,
        target_weight_kg: displayIdealWeight != null ? displayIdealWeight : null,
        target_weight_from_bf_kg: targetWeightFromBf,
        target_body_fat_percent: targetBf,
        diet_goal: dietGoal.key,
        diet_goal_label: dietGoal.label,
        diet_goal_adjustment_percent: dietGoal.adjustment_percent,
        weight_delta_kg: displayIdealWeight != null ? displayIdealWeight - weightKg : 0,
        weekly_change_kg: weeklyChangeKg,
        weekly_change_percent: weeklyChangePct,
        daily_calorie_delta: dailyDelta,
        calorie_target: calorieTarget,
        direction,
      },
      macros: {
        preset,
        protein_g: proteinG,
        protein_kcal: proteinKcal,
        fat_g: fatG,
        fat_kcal: fatKcal,
        carbs_g: carbsG,
        carbs_kcal: carbsKcal,
      },
      warnings,
      summary: summaryParts.join(" "),
    };
  }

  function renderMetrics(plan) {
    const metrics = plan && plan.metrics;
    if (!metrics) {
      els.metricBmi.textContent = "0.0";
      els.metricBmiNote.textContent = "Classe BMI";
      els.metricBmr.textContent = "0 kcal";
      els.metricTdee.textContent = "0 kcal";
      els.metricBf.textContent = "0.0%";
      els.metricIdealWeight.textContent = "0.0 kg";
      els.metricCalories.textContent = "0 kcal";
      els.metricTargetBf.textContent = "0.0%";
      els.bfMethodChip.textContent = "In attesa";
      els.planSummary.textContent = "Compila il form per generare il piano.";
      els.dietStatusChip.textContent = "In attesa";
      return;
    }
    els.metricBmi.textContent = formatNumber(metrics.bmi, 1);
    els.metricBmiNote.textContent = metrics.bmi_category;
    els.metricBmr.textContent = formatCalories(metrics.bmr);
    els.metricTdee.textContent = formatCalories(metrics.tdee);
    els.metricBf.textContent = formatPercent(metrics.body_fat_percent);
    els.metricIdealWeight.textContent = metrics.ideal_weight_kg != null ? formatWeight(metrics.ideal_weight_kg) : "-";
    els.metricCalories.textContent = formatCalories(metrics.calorie_target);
    els.metricTargetBf.textContent = metrics.target_body_fat_percent != null ? formatPercent(metrics.target_body_fat_percent) : "-";
    els.bfMethodChip.textContent = metrics.body_fat_label;
    els.planSummary.textContent = plan.summary || "Piano pronto.";
    els.dietStatusChip.textContent = metrics.diet_goal_label || (metrics.direction === "deficit" ? "Cut" : metrics.direction === "surplus" ? "Bulk" : "Mantenimento");
  }

  function renderDiet(plan) {
    const metrics = plan && plan.metrics;
    const macros = plan && plan.macros;
    if (!macros) {
      els.dietProtein.textContent = "0 g";
      els.dietProteinNote.textContent = "0 kcal";
      els.dietFat.textContent = "0 g";
      els.dietFatNote.textContent = "0 kcal";
      els.dietCarbs.textContent = "0 g";
      els.dietCarbsNote.textContent = "0 kcal";
      els.dietGoal.textContent = "Mantenimento";
      els.dietGoalNote.textContent = "0% del TDEE";
      els.warningList.innerHTML = "";
      return;
    }
    els.dietProtein.textContent = `${formatNumber(macros.protein_g, 1)} g`;
    els.dietProteinNote.textContent = formatCalories(macros.protein_kcal);
    els.dietFat.textContent = `${formatNumber(macros.fat_g, 1)} g`;
    els.dietFatNote.textContent = formatCalories(macros.fat_kcal);
    els.dietCarbs.textContent = `${formatNumber(macros.carbs_g, 1)} g`;
    els.dietCarbsNote.textContent = formatCalories(macros.carbs_kcal);
    els.dietGoal.textContent = metrics && metrics.diet_goal_label ? metrics.diet_goal_label : (metrics && metrics.direction === "surplus" ? "Bulk" : metrics && metrics.direction === "deficit" ? "Cut" : "Mantenimento");
    const adjustment = metrics && metrics.diet_goal_adjustment_percent != null ? Number(metrics.diet_goal_adjustment_percent) : 0;
    els.dietGoalNote.textContent = adjustment === 0 ? "0% del TDEE" : `${adjustment > 0 ? "+" : ""}${adjustment}% del TDEE`;
    els.warningList.innerHTML = (plan.warnings || []).length
      ? (plan.warnings || []).map((warning) => `<span class="warning-pill">${escapeHtml(warning)}</span>`).join("")
      : `<span class="tag success">Nessun warning rilevato</span>`;
  }

  function renderProfile() {
    const user = state.me;
    els.profileAvatar.textContent = avatarText(user);
    els.profileName.textContent = user ? (user.name || "Il tuo profilo") : "Benvenuto";
    els.profileEmail.textContent = user ? (user.email || "") : "Nessun account caricato";
    const profile = state.profile || {};
    const latest = state.latestPlan || state.preview;
    const latestGoal = latest && latest.metrics ? (latest.metrics.diet_goal_label || (latest.metrics.direction === "deficit" ? "Cut" : latest.metrics.direction === "surplus" ? "Bulk" : "Mantenimento")) : "";
    els.profileWeight.textContent = profile.weight_kg ? formatWeight(profile.weight_kg) : "-";
    els.profileBf.textContent = latest && latest.metrics ? formatPercent(latest.metrics.body_fat_percent) : "-";
    els.profileTarget.textContent = profile.diet_goal_label || profile.diet_goal || latestGoal || "-";
    els.profileActivity.textContent = profile.activity_key ? (state.activityLevels.find((item) => item.key === profile.activity_key)?.label || profile.activity_key) : "-";
  }

  function renderPlanHistory() {
    const plans = state.plans || [];
    if (!plans.length) {
      els.planHistoryList.innerHTML = "<div class='empty-state'>Nessun piano salvato ancora.</div>";
      return;
    }
    els.planHistoryList.innerHTML = plans.map((plan) => {
      const metrics = plan.metrics || {};
      const inputs = plan.inputs || {};
      const historyNotes = [];
      if (inputs.ideal_weight_kg != null && String(inputs.ideal_weight_kg).trim() !== "") historyNotes.push(`Peso ideale ${formatWeight(inputs.ideal_weight_kg)}`);
      if (inputs.target_body_fat_percent != null && String(inputs.target_body_fat_percent).trim() !== "") historyNotes.push(`Target BF ${formatPercent(inputs.target_body_fat_percent)}`);
      const legacyGoal = metrics.direction === "deficit" ? "Cut" : metrics.direction === "surplus" ? "Bulk" : "Mantenimento";
      return `
        <article class="stack-item">
          <h4>${escapeHtml(formatDateTime(plan.created_at))} - ${escapeHtml(formatCalories(metrics.calorie_target || 0))}</h4>
          <p>${escapeHtml(metrics.diet_goal_label || inputs.diet_goal_label || inputs.diet_goal || legacyGoal)}${historyNotes.length ? ` - ${escapeHtml(historyNotes.join(" - "))}` : ""}</p>
          <div class="stack-meta">
            <span class="tag success">${escapeHtml(metrics.diet_goal_label || (metrics.direction === "deficit" ? "Cut" : metrics.direction === "surplus" ? "Bulk" : "Mantenimento"))}</span>
            <span class="pill">BMI ${escapeHtml(formatNumber(metrics.bmi || 0, 1))}</span>
            <span class="pill">TDEE ${escapeHtml(formatCalories(metrics.tdee || 0))}</span>
          </div>
        </article>
      `;
    }).join("");
  }

  function renderCheckins() {
    const items = state.checkins || [];
    if (!items.length) {
      els.checkinList.innerHTML = "<div class='empty-state'>Nessun check-in ancora.</div>";
      return;
    }
    els.checkinList.innerHTML = items.map((item) => `
      <article class="stack-item">
        <h4>${escapeHtml(formatDate(item.measured_on))} - ${escapeHtml(formatWeight(item.weight_kg || 0))}</h4>
        <p>${escapeHtml(item.body_fat_percent != null ? formatPercent(item.body_fat_percent) : "BF non inserita")}${item.notes ? ` - ${escapeHtml(item.notes)}` : ""}</p>
      </article>
    `).join("");
  }

  function renderAll() {
    const plan = state.latestPlan || state.preview;
    renderMetrics(plan);
    renderDiet(plan);
    renderProfile();
    renderPlanHistory();
    renderCheckins();
    updateActivityChip();
  }

  function applyStateToForm() {
    const stored = loadDraft();
    const profile = profileToDraft(state.profile || {});
    const merged = { ...defaultDraft, ...stored, ...profile };
    applyDraftToForm(merged);
    if (!els.checkinDateInput.value) els.checkinDateInput.value = (els.body.dataset.today || new Date().toISOString().slice(0, 10));
  }

  function refreshPreview() {
    const draft = readFormDraft();
    state.preview = computeLocalPlan(draft);
    renderAll();
    persistDraft();
  }

  function setStatus(message) {
    els.syncChip.textContent = message;
    els.headerSubtitle.textContent = message;
  }

  function refreshMe() {
    return api("/api/me").then((data) => {
      if (!data.logged_in || !data.user) {
        state.me = null;
        showGate("auth");
        return false;
      }
      state.me = data.user;
      showGate("app");
      els.welcomeName.textContent = `Ciao, ${state.me.name || "utente"}`;
      setStatus("Pronto");
      return true;
    });
  }

  function refreshState() {
    if (state.refreshPromise) return state.refreshPromise;
    state.refreshPromise = api("/api/state")
      .then((data) => {
        state.activityLevels = data.activity_levels || [];
        state.dietGoals = data.diet_goals || [];
        state.macroPresets = data.macro_presets || [];
        state.profile = data.profile || {};
        state.latestPlan = data.latest_plan || null;
        state.plans = data.plans || [];
        state.checkins = data.checkins || [];
        updateActivitySelect();
        updateDietGoalSelect();
        updateMacroPresetSelect();
        applyStateToForm();
        state.preview = state.latestPlan || computeLocalPlan(readFormDraft());
        renderAll();
      })
      .finally(() => {
        state.refreshPromise = null;
      });
    return state.refreshPromise;
  }

  function submitPlan() {
    const draft = readFormDraft();
    const local = computeLocalPlan(draft);
    if (!local || !local.ready) {
      showToast((local && local.warnings && local.warnings[0]) || "Completa i campi necessari per generare il piano.", "warn");
      renderAll();
      return;
    }
    setStatus("Sto salvando il piano...");
    api("/api/plan/calc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
      timeoutMs: 15000,
    })
      .then((data) => {
        state.profile = data.profile || state.profile;
        state.latestPlan = data.latest_plan || data.plan || state.latestPlan;
        state.plans = data.plans || state.plans;
        state.checkins = data.checkins || state.checkins;
        state.preview = state.latestPlan || local;
        applyStateToForm();
        renderAll();
        showToast(data.message || "Piano salvato.", "success");
        setStatus("Piano salvato");
      })
      .catch((err) => {
        showToast(err.message, "danger");
        setStatus("Errore nel salvataggio");
      });
  }

  function saveCheckin() {
    const payload = {
      measured_on: els.checkinDateInput.value,
      weight_kg: els.checkinWeightInput.value,
      body_fat_percent: els.checkinBfInput.value,
      notes: els.checkinNoteInput.value,
    };
    if (!payload.weight_kg) {
      showToast("Inserisci il peso del check-in.", "warn");
      return;
    }
    api("/api/checkins", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((data) => {
        state.checkins = data.checkins || [];
        renderCheckins();
        renderProfile();
        showToast(data.message || "Check-in salvato.", "success");
      })
      .catch((err) => showToast(err.message, "danger"));
  }

  function downloadCsv() {
    window.location.href = `/api/export.csv?v=${encodeURIComponent(assetVersion)}`;
  }

  function logout() {
    api("/auth/logout", { method: "POST" })
      .then(() => {
        state.me = null;
        state.profile = {};
        state.latestPlan = null;
        state.plans = [];
        state.checkins = [];
        showGate("auth");
        initGoogleSignIn();
      })
      .catch((err) => showToast(err.message, "danger"));
  }

  function initGoogleSignIn() {
    if (!googleClientId || !els.googleSignin || state.googleInitialized) return;
    const waitForGoogle = () => {
      if (!(window.google && window.google.accounts && window.google.accounts.id)) {
        window.setTimeout(waitForGoogle, 150);
        return;
      }
      state.googleInitialized = true;
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: (response) => {
          api("/auth/google", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credential: response.credential }),
          })
            .then((data) => {
              state.me = data.user;
              showGate("app");
              els.welcomeName.textContent = `Ciao, ${state.me.name || "utente"}`;
              refreshState();
            })
            .catch((err) => showToast(err.message, "danger"));
        },
        auto_select: true,
        cancel_on_tap_outside: false,
      });
      window.google.accounts.id.renderButton(els.googleSignin, {
        theme: "filled_blue",
        size: "large",
        shape: "pill",
        text: "continue_with",
        logo_alignment: "left",
        width: 320,
      });
      window.google.accounts.id.prompt();
    };
    waitForGoogle();
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register(`/service-worker.js?v=${encodeURIComponent(assetVersion)}`, { updateViaCache: "none" }).catch(() => {});
  }

  function bindFormEvents() {
    const inputs = [
      els.sexSelect,
      els.ageInput,
      els.heightInput,
      els.weightInput,
      els.activitySelect,
      els.bfMethodSelect,
      els.bodyFatManualInput,
      els.waistInput,
      els.neckInput,
      els.hipsInput,
      els.dietGoalSelect,
      els.idealWeightInput,
      els.targetBfInput,
      els.macroPresetSelect,
      els.proteinInput,
      els.fatInput,
      els.goalNoteInput,
    ];
    inputs.forEach((element) => {
      element.addEventListener("input", () => {
        if (element === els.macroPresetSelect) updateMacroPresetFields(true);
        if (element === els.activitySelect) updateActivityChip();
        if (element === els.bfMethodSelect) updateBfVisibility();
        refreshPreview();
      });
      element.addEventListener("change", () => {
        if (element === els.macroPresetSelect) updateMacroPresetFields(true);
        if (element === els.activitySelect) updateActivityChip();
        if (element === els.bfMethodSelect) updateBfVisibility();
        refreshPreview();
      });
    });
  }

  function bindEvents() {
    els.navButtons.forEach((button) => {
      button.addEventListener("click", () => setActiveScreen(button.dataset.screen));
    });
    els.generateFromHeader.addEventListener("click", submitPlan);
    els.calcSaveBtn.addEventListener("click", submitPlan);
    els.fabCalc.addEventListener("click", () => {
      setActiveScreen("screen-calc");
      submitPlan();
    });
    els.saveCheckinBtn.addEventListener("click", saveCheckin);
    els.exportCsvBtn.addEventListener("click", downloadCsv);
    els.logoutBtn.addEventListener("click", logout);
    if (els.devLogin) {
      els.devLogin.addEventListener("click", () => {
        api("/auth/dev-login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: els.devName.value,
            email: els.devEmail.value,
          }),
        })
          .then((data) => {
            state.me = data.user;
            showGate("app");
            els.welcomeName.textContent = `Ciao, ${state.me.name || "utente"}`;
            refreshState();
          })
          .catch((err) => showToast(err.message, "danger"));
      });
    }
    bindFormEvents();
  }

  function boot() {
    showGate("auth");
    setActiveScreen("screen-dashboard");
    registerServiceWorker();
    bindEvents();
    initGoogleSignIn();
    refreshMe()
      .then((loggedIn) => {
        hideBootSplash();
        if (loggedIn) {
          return refreshState().then(() => {
            applyStateToForm();
            refreshPreview();
          });
        }
        applyDraftToForm(loadDraft());
        refreshPreview();
        return null;
      })
      .catch((err) => {
        hideBootSplash();
        showToast(err.message, "danger");
        applyDraftToForm(loadDraft());
        refreshPreview();
      });
  }

  boot();
})();
