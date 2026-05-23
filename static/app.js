(function () {
  const state = {
    me: null,
    activeScreen: "screen-dashboard",
    month: "",
    monthLabel: "",
    storageMode: "database",
    categories: [],
    entries: [],
    summary: {
      expense_total: 0,
      income_total: 0,
      balance: 0,
      top_category: null,
      category_totals: [],
    },
    profileMode: "month",
    profileCycleDay: 25,
    profilePeriod: {
      label: "",
      mode: "month",
      start_date: "",
      end_date: "",
      cycle_day: 25,
    },
    profileSummary: {
      expense_total: 0,
      income_total: 0,
      balance: 0,
      transaction_count: 0,
      average_expense: 0,
      average_income: 0,
      daily_expense: 0,
      active_days: 0,
      savings_rate: null,
      period_days: 0,
      top_category: null,
      category_totals: [],
      biggest_expense: null,
      expense_count: 0,
      income_count: 0,
    },
    filterType: "all",
    search: "",
    editingEntryId: null,
    editingCategoryId: null,
    bank: {
      configured: false,
      connected: false,
      aspsp_name: "Postepay Evolution",
      account_name: "",
      account_iban: "",
      currency: "EUR",
      current_balance: null,
      available_balance: null,
      booked_balance: null,
      balance_label: "",
      last_sync_at: "",
      transaction_count: 0,
      transactions: [],
      access_valid_until: "",
      pending_category_count: 0,
      auto_sync_minutes: 30,
    },
    bankFlash: null,
    bankAutoSyncRequested: false,
    bankSyncInFlight: false,
    bankAutoSyncDone: false,
    lastStateFetchAt: 0,
    refreshPromise: null,
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
    monthInput: document.getElementById("month-input"),
    monthPrev: document.getElementById("month-prev"),
    monthNext: document.getElementById("month-next"),
    monthLabel: document.getElementById("month-label"),
    monthCaption: document.getElementById("month-caption"),
    welcomeName: document.getElementById("welcome-name"),
    metricBalance: document.getElementById("metric-balance"),
    metricBalanceNote: document.getElementById("metric-balance-note"),
    metricExpense: document.getElementById("metric-expense"),
    metricIncome: document.getElementById("metric-income"),
    topCategoryTag: document.getElementById("top-category-tag"),
    categoryBars: document.getElementById("category-bars"),
    movementList: document.getElementById("movement-list"),
    categoryGrid: document.getElementById("category-grid"),
    searchInput: document.getElementById("search-input"),
    filterButtons: Array.from(document.querySelectorAll("[data-filter-type]")),
    navButtons: Array.from(document.querySelectorAll(".nav-btn")),
    screens: Array.from(document.querySelectorAll(".screen")),
    headerAddEntry: document.getElementById("header-add-entry"),
    movementsAddEntry: document.getElementById("movements-add-entry"),
    fabEntry: document.getElementById("fab-entry"),
    addCategory: document.getElementById("add-category"),
    quickCategoryName: document.getElementById("category-quick-name"),
    quickCategoryColor: document.getElementById("category-quick-color"),
    saveQuickCategory: document.getElementById("save-quick-category"),
    exportCsv: document.getElementById("export-csv"),
    logoutBtn: document.getElementById("logout-btn"),
    profileName: document.getElementById("profile-name"),
    profileEmail: document.getElementById("profile-email"),
    profileAvatar: document.getElementById("profile-avatar"),
    profileModeButtons: Array.from(document.querySelectorAll("[data-profile-mode]")),
    profileCycleDay: document.getElementById("profile-cycle-day"),
    profilePeriodLabel: document.getElementById("profile-period-label"),
    profileBalance: document.getElementById("profile-balance"),
    profileExpenseTotal: document.getElementById("profile-expense-total"),
    profileIncomeTotal: document.getElementById("profile-income-total"),
    profileCount: document.getElementById("profile-count"),
    profileAverage: document.getElementById("profile-average"),
    profileDaily: document.getElementById("profile-daily"),
    profileDays: document.getElementById("profile-days"),
    profileSavingRate: document.getElementById("profile-saving-rate"),
    profileBreakdown: document.getElementById("profile-breakdown"),
    bankStatusText: document.getElementById("bank-status-text"),
    bankSyncChip: document.getElementById("bank-sync-chip"),
    bankBalance: document.getElementById("bank-balance"),
    bankAccountName: document.getElementById("bank-account-name"),
    bankIban: document.getElementById("bank-iban"),
    bankValidUntil: document.getElementById("bank-valid-until"),
    bankMessage: document.getElementById("bank-message"),
    bankConnect: document.getElementById("bank-connect"),
    bankSync: document.getElementById("bank-sync"),
    bankDisconnect: document.getElementById("bank-disconnect"),
    bankTransactionList: document.getElementById("bank-transaction-list"),
    entryModal: document.getElementById("entry-modal"),
    entryModalTitle: document.getElementById("entry-modal-title"),
    closeEntryModal: document.getElementById("close-entry-modal"),
    entryType: document.getElementById("entry-type"),
    entryDate: document.getElementById("entry-date"),
    entryTitle: document.getElementById("entry-title"),
    entryAmount: document.getElementById("entry-amount"),
    entryCategory: document.getElementById("entry-category"),
    entryNotes: document.getElementById("entry-notes"),
    saveEntry: document.getElementById("save-entry"),
    deleteEntry: document.getElementById("delete-entry"),
    categoryModal: document.getElementById("category-modal"),
    categoryModalTitle: document.getElementById("category-modal-title"),
    closeCategoryModal: document.getElementById("close-category-modal"),
    categoryName: document.getElementById("category-name"),
    categoryColor: document.getElementById("category-color"),
    categoryArchived: document.getElementById("category-archived"),
    saveCategory: document.getElementById("save-category"),
    deleteCategory: document.getElementById("delete-category"),
  };

  const googleClientId = (els.body.dataset.googleClientId || "").trim();
  const appName = (els.body.dataset.pwaAppName || "Spese Mixet").trim();
  const assetVersion = (els.body.dataset.assetVersion || "2026-05-23-v6").trim();
  const currencyFormatter = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
  const shortDateFormatter = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short" });
  const monthFormatter = new Intl.DateTimeFormat("it-IT", { month: "long", year: "numeric" });
  const dateTimeFormatter = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  let googleInitialized = false;

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatMoney(value) {
    return currencyFormatter.format(Number(value || 0));
  }

  function formatShortDate(value) {
    const dateObj = new Date(`${value}T12:00:00`);
    if (Number.isNaN(dateObj.getTime())) return value || "";
    return shortDateFormatter.format(dateObj).replace(".", "");
  }

  function formatDateTime(value) {
    if (!value) return "-";
    const normalized = String(value).includes("T") ? String(value).replace(" ", "T") : `${value}T00:00:00`;
    const dateObj = new Date(normalized);
    if (Number.isNaN(dateObj.getTime())) return String(value);
    return dateTimeFormatter.format(dateObj);
  }

  function formatAccessDate(value) {
    if (!value) return "Accesso non attivo";
    return `Accesso valido fino al ${formatDateTime(value)}`;
  }

  function avatarText(user) {
    const base = String((user && (user.name || user.email)) || appName).trim();
    return base.slice(0, 2).toUpperCase();
  }

  async function api(url, options = {}) {
    const timeoutMs = Number(options.timeoutMs || 0);
    const fetchOptions = { ...options, cache: "no-store" };
    delete fetchOptions.timeoutMs;
    let timeoutId = null;
    if (timeoutMs > 0) {
      const controller = new AbortController();
      fetchOptions.signal = controller.signal;
      timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    }
    let response;
    try {
      response = await fetch(url, fetchOptions);
    } catch (err) {
      if (timeoutId) window.clearTimeout(timeoutId);
      if (err && err.name === "AbortError") {
        throw new Error("La richiesta ha impiegato troppo tempo. Riprova tra poco.");
      }
      throw err;
    }
    if (timeoutId) window.clearTimeout(timeoutId);
    let data = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      data = await response.json();
    }
    if (!response.ok) {
      if (response.status === 401) {
        state.me = null;
        showGate("auth");
        initGoogleSignIn();
      }
      throw new Error((data && data.message) || "Operazione non riuscita.");
    }
    return data;
  }

  function showGate(mode) {
    els.authGate.classList.toggle("hidden", mode !== "auth");
    els.appShell.classList.toggle("hidden", mode !== "app");
  }

  function hideBootSplash() {
    els.bootSplash.classList.add("hidden");
  }

  function setActiveScreen(screenId) {
    state.activeScreen = screenId;
    els.screens.forEach((screen) => screen.classList.toggle("active", screen.id === screenId));
    els.navButtons.forEach((button) => button.classList.toggle("active", button.dataset.screen === screenId));
  }

  function consumeBankFlashFromUrl() {
    const url = new URL(window.location.href);
    const status = (url.searchParams.get("bank_status") || "").trim();
    const message = (url.searchParams.get("bank_message") || "").trim();
    const autoSync = (url.searchParams.get("bank_autosync") || "").trim() === "1";
    if (status || message) {
      state.bankFlash = { status: status || "info", message };
      setActiveScreen("screen-profile");
    }
    if (autoSync) {
      state.bankAutoSyncRequested = true;
      setActiveScreen("screen-profile");
    }
    if (!status && !message && !autoSync) return;
    url.searchParams.delete("bank_status");
    url.searchParams.delete("bank_message");
    url.searchParams.delete("bank_autosync");
    const cleanUrl = `${url.pathname}${url.searchParams.toString() ? `?${url.searchParams.toString()}` : ""}${url.hash || ""}`;
    window.history.replaceState({}, "", cleanUrl);
  }

  function setMonthValue(monthValue) {
    state.month = monthValue;
    els.monthInput.value = monthValue;
    const [year, month] = monthValue.split("-");
    const dateObj = new Date(Number(year), Number(month) - 1, 1);
    els.monthLabel.textContent = monthFormatter.format(dateObj);
  }

  function shiftMonth(step) {
    const [yearRaw, monthRaw] = state.month.split("-");
    const dateObj = new Date(Number(yearRaw), Number(monthRaw) - 1, 1);
    dateObj.setMonth(dateObj.getMonth() + step);
    const nextValue = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, "0")}`;
    setMonthValue(nextValue);
    refreshState().catch((err) => alert(err.message));
  }

  function renderCategoryOptions(selectedId) {
    const options = ['<option value="">Senza categoria</option>'];
    state.categories.forEach((category) => {
      if (category.archived) return;
      options.push(
        `<option value="${category.id}" ${Number(selectedId || 0) === Number(category.id) ? "selected" : ""}>${escapeHtml(category.name)}</option>`
      );
    });
    els.entryCategory.innerHTML = options.join("");
  }

  function resetQuickCategoryForm() {
    els.quickCategoryName.value = "";
    els.quickCategoryColor.value = "#1f7a6f";
  }

  function openEntryModal(entry) {
    state.editingEntryId = entry ? entry.id : null;
    els.entryModalTitle.textContent = entry ? "Modifica movimento" : "Nuovo movimento";
    els.deleteEntry.classList.toggle("hidden", !entry);
    els.entryType.value = entry ? entry.entry_type : "expense";
    els.entryDate.value = entry ? entry.occurred_on : (els.body.dataset.today || "");
    els.entryTitle.value = entry ? entry.title : "";
    els.entryAmount.value = entry ? Number(entry.amount).toFixed(2) : "";
    renderCategoryOptions(entry && entry.category ? entry.category.id : null);
    els.entryNotes.value = entry ? entry.notes : "";
    els.entryModal.classList.remove("hidden");
  }

  function closeEntryModal() {
    state.editingEntryId = null;
    els.entryModal.classList.add("hidden");
  }

  function openCategoryModal(category) {
    state.editingCategoryId = category ? category.id : null;
    els.categoryModalTitle.textContent = category ? "Modifica categoria" : "Nuova categoria";
    els.deleteCategory.classList.toggle("hidden", !category);
    els.categoryName.value = category ? category.name : "";
    els.categoryColor.value = category ? category.color : "#1f7a6f";
    els.categoryArchived.checked = category ? Boolean(category.archived) : false;
    els.categoryModal.classList.remove("hidden");
  }

  function closeCategoryModal() {
    state.editingCategoryId = null;
    els.categoryModal.classList.add("hidden");
  }

  function renderMetrics() {
    const balance = Number(state.summary.balance || 0);
    els.metricBalance.textContent = formatMoney(balance);
    els.metricBalanceNote.textContent = balance >= 0 ? "Entrate meno uscite del mese" : "Periodo da tenere sotto controllo";
    els.metricExpense.textContent = formatMoney(state.summary.expense_total || 0);
    els.metricIncome.textContent = formatMoney(state.summary.income_total || 0);
    const top = state.summary.top_category;
    els.topCategoryTag.textContent = top ? `${top.name} - ${formatMoney(top.amount)}` : "Nessuna";
  }

  function renderCategoryBars() {
    const items = state.summary.category_totals || [];
    if (!items.length) {
      els.categoryBars.innerHTML = "<div class='empty-state'>Nessuna spesa categorizzata nel mese selezionato.</div>";
      return;
    }
    const maxValue = Math.max(...items.map((item) => Number(item.amount || 0)), 1);
    els.categoryBars.innerHTML = items.map((item) => {
      const width = Math.max(8, Math.round((Number(item.amount || 0) / maxValue) * 100));
      return `
        <div class="bar-row">
          <div class="bar-meta">
            <span>${escapeHtml(item.name)}</span>
            <strong>${escapeHtml(formatMoney(item.amount))}</strong>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${width}%; background:${escapeHtml(item.color)};"></div>
          </div>
        </div>
      `;
    }).join("");
  }

  function filteredEntries() {
    const term = state.search.trim().toLowerCase();
    return state.entries.filter((entry) => {
      if (state.filterType === "expense" && entry.entry_type !== "expense") return false;
      if (state.filterType === "income" && entry.entry_type !== "income") return false;
      if (state.filterType === "uncategorized" && !entry.needs_category) return false;
      if (!term) return true;
      const haystack = `${entry.title} ${entry.notes} ${(entry.category && entry.category.name) || ""} ${entry.source || ""}`.toLowerCase();
      return haystack.includes(term);
    });
  }

  function movementRowMarkup(entry) {
    const dotColor = entry.category ? entry.category.color : (entry.entry_type === "income" ? "#27e89d" : "#ff4d7a");
    const amountClass = entry.entry_type === "income" ? "income" : "expense";
    const categoryLabel = entry.category ? entry.category.name : "Senza categoria";
    const sourceTag = entry.imported ? "<span class='soft-chip'>Postepay</span>" : "";
    const categoryTag = entry.needs_category ? "<span class='soft-chip needs-tag'>Da catalogare</span>" : "";
    return `
      <article class="movement-row" data-entry-id="${entry.id}">
        <span class="dot" style="background:${escapeHtml(dotColor)};"></span>
        <div class="movement-copy">
          <strong>${escapeHtml(entry.title)}</strong>
          <p>${escapeHtml(formatShortDate(entry.occurred_on))} - ${escapeHtml(categoryLabel)}</p>
          <div class="movement-tags">${sourceTag}${categoryTag}</div>
          ${entry.notes ? `<p>${escapeHtml(entry.notes)}</p>` : ""}
          <div class="movement-actions">
            <button class="mini-btn" data-entry-action="edit" data-entry-id="${entry.id}">Modifica</button>
            <button class="mini-btn" data-entry-action="delete" data-entry-id="${entry.id}">Elimina</button>
          </div>
        </div>
        <div class="movement-amount">
          <strong class="${amountClass}">${escapeHtml(formatMoney(entry.amount))}</strong>
          <small>${escapeHtml(entry.entry_type_label)}</small>
        </div>
      </article>
    `;
  }

  function renderMovements() {
    const items = filteredEntries();
    if (!items.length) {
      els.movementList.innerHTML = "<div class='empty-state'>Nessun movimento trovato con i filtri attivi.</div>";
      return;
    }
    els.movementList.innerHTML = items.map(movementRowMarkup).join("");
  }

  function renderCategories() {
    if (!state.categories.length) {
      els.categoryGrid.innerHTML = "<div class='empty-state'>Crea la tua prima categoria personalizzata.</div>";
      return;
    }
    els.categoryGrid.innerHTML = state.categories.map((category) => `
      <article class="category-card" data-category-id="${category.id}">
        <div class="category-head">
          <div>
            <div style="display:flex; align-items:center; gap:10px;">
              <span class="swatch" style="background:${escapeHtml(category.color)};"></span>
              <strong>${escapeHtml(category.name)}</strong>
            </div>
            <p class="helper">${category.archived ? "Categoria archiviata" : "Categoria attiva"}</p>
          </div>
          <span class="soft-chip">${category.entry_count} mov.</span>
        </div>
        <div class="category-meta">
          <div class="meta-pill">Spese: ${escapeHtml(formatMoney(category.expense_total))}</div>
          <div class="meta-pill">Entrate: ${escapeHtml(formatMoney(category.income_total))}</div>
        </div>
        <div class="category-actions">
          <button class="mini-btn" data-category-action="edit" data-category-id="${category.id}">Modifica</button>
          <button class="mini-btn" data-category-action="delete" data-category-id="${category.id}">Archivia</button>
        </div>
      </article>
    `).join("");
  }

  function renderProfileBreakdown() {
    const summary = state.profileSummary;
    const lines = [
      `Periodo attivo: ${state.profilePeriod.label || "-"}`,
      `Numero spese: ${summary.expense_count || 0}`,
      `Numero entrate: ${summary.income_count || 0}`,
      `Media entrate: ${formatMoney(summary.average_income || 0)}`,
      `Giorni coperti: ${summary.period_days || 0}`,
      `Categoria piu pesante: ${summary.top_category ? `${summary.top_category.name} - ${formatMoney(summary.top_category.amount)}` : "Nessuna"}`,
      `Spesa piu alta: ${summary.biggest_expense ? `${summary.biggest_expense.title} - ${formatMoney(summary.biggest_expense.amount)} (${formatShortDate(summary.biggest_expense.occurred_on)})` : "Nessuna"}`,
    ];

    const categoryLines = (summary.category_totals || []).slice(0, 5).map((item) => {
      return `Categoria: ${item.name} - ${formatMoney(item.amount)}`;
    });

    const allLines = lines.concat(categoryLines);
    els.profileBreakdown.innerHTML = allLines.map((line) => `
      <article class="recent-row compact-row">
        <div class="recent-copy">
          <p>${escapeHtml(line)}</p>
        </div>
      </article>
    `).join("");
  }

  function bankTransactionMarkup(item) {
    const amountClass = item.direction === "income" ? "income" : "expense";
    const dotColor = item.direction === "income" ? "#27e89d" : "#ff4d7a";
    const amountPrefix = item.direction === "income" ? "+" : "-";
    return `
      <article class="movement-row">
        <span class="dot" style="background:${dotColor};"></span>
        <div class="movement-copy">
          <strong>${escapeHtml(item.title || "Movimento Postepay")}</strong>
          <p>${escapeHtml(formatShortDate(item.date || ""))}${item.status ? ` - ${escapeHtml(item.status)}` : ""}</p>
          ${item.notes ? `<p>${escapeHtml(item.notes)}</p>` : ""}
        </div>
        <div class="movement-amount">
          <strong class="${amountClass}">${escapeHtml(`${amountPrefix}${formatMoney(item.amount || 0)}`)}</strong>
          <small>${escapeHtml(item.currency || "EUR")}</small>
        </div>
      </article>
    `;
  }

  function renderBank() {
    const bank = state.bank || {};
    const hasBalance = bank.current_balance != null || bank.available_balance != null || bank.booked_balance != null;
    const visibleBalance = bank.current_balance ?? bank.available_balance ?? bank.booked_balance;
    const balanceLabel = bank.balance_label ? `Saldo ${bank.balance_label.toLowerCase()}` : "Saldo attuale";
    const flashMessage = state.bankFlash && state.bankFlash.message ? state.bankFlash.message : "";

    els.bankBalance.textContent = hasBalance ? formatMoney(visibleBalance) : "-";
    els.bankAccountName.textContent = bank.connected ? (bank.account_name || "Carta Postepay") : "Nessun collegamento";
    els.bankIban.textContent = bank.account_iban || "IBAN o PAN non disponibile";
    els.bankValidUntil.textContent = formatAccessDate(bank.access_valid_until);
    els.bankMessage.textContent = flashMessage || bank.last_error || "";

    if (!bank.configured) {
      els.bankStatusText.textContent = "Manca la configurazione del provider PSD2 per collegare davvero la Postepay.";
      els.bankSyncChip.textContent = "Non configurato";
      els.bankBalance.previousElementSibling.textContent = "Saldo attuale";
      els.bankTransactionList.innerHTML = "<div class='empty-state'>Configura Enable Banking nel server per attivare saldo e movimenti live.</div>";
      els.bankConnect.disabled = true;
      els.bankSync.disabled = true;
      els.bankDisconnect.disabled = true;
      return;
    }

    els.bankBalance.previousElementSibling.textContent = balanceLabel;
    els.bankConnect.disabled = false;
    els.bankSync.disabled = !bank.connected;
    els.bankDisconnect.disabled = !bank.connected;

    if (!bank.connected) {
      els.bankStatusText.textContent = "Carta non ancora collegata. Il collegamento usa il consenso ufficiale PSD2.";
      els.bankSyncChip.textContent = "Da collegare";
      els.bankTransactionList.innerHTML = "<div class='empty-state'>Collega la tua Postepay Evolution per scaricare saldo e movimenti.</div>";
      return;
    }

    els.bankStatusText.textContent = state.bankSyncInFlight
      ? "Sto sincronizzando saldo e movimenti Postepay."
      : bank.last_sync_at
        ? `Saldo e movimenti aggiornati al ${formatDateTime(bank.last_sync_at)}.`
        : "Carta collegata. Sto aspettando la prima sincronizzazione.";
    if (state.bankSyncInFlight) {
      els.bankSyncChip.textContent = "Sincronizzo";
    } else if ((bank.pending_category_count || 0) > 0) {
      els.bankSyncChip.textContent = `${bank.pending_category_count} da catalogare`;
    } else {
      els.bankSyncChip.textContent = bank.last_sync_at ? "Sincronizzata" : "Collegata";
    }

    if (!(bank.transactions || []).length) {
      els.bankTransactionList.innerHTML = "<div class='empty-state'>Nessun movimento scaricato. Premi Aggiorna saldo per sincronizzare i dati.</div>";
      return;
    }

    els.bankTransactionList.innerHTML = (bank.transactions || []).slice(0, 8).map(bankTransactionMarkup).join("");
  }

  function renderProfile() {
    const user = state.me || {};
    const summary = state.profileSummary || {};
    els.profileName.textContent = user.name || "Profilo";
    els.profileEmail.textContent = user.email || "";
    els.profilePeriodLabel.value = state.profilePeriod.label || "";
    els.profileCycleDay.value = String(state.profilePeriod.cycle_day || state.profileCycleDay || 25);
    els.profileCycleDay.disabled = state.profileMode !== "cycle";
    els.profileBalance.textContent = formatMoney(summary.balance || 0);
    els.profileExpenseTotal.textContent = formatMoney(summary.expense_total || 0);
    els.profileIncomeTotal.textContent = formatMoney(summary.income_total || 0);
    els.profileCount.textContent = String(summary.transaction_count || 0);
    els.profileAverage.textContent = formatMoney(summary.average_expense || 0);
    els.profileDaily.textContent = formatMoney(summary.daily_expense || 0);
    els.profileDays.textContent = String(summary.active_days || 0);
    els.profileSavingRate.textContent = summary.savings_rate == null ? "-" : `${summary.savings_rate}%`;
    els.profileModeButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.profileMode === state.profileMode);
    });
    renderProfileBreakdown();
    renderBank();

    if (user.picture) {
      els.profileAvatar.innerHTML = `<img src="${escapeHtml(user.picture)}" alt="${escapeHtml(user.name || "avatar")}" style="width:100%;height:100%;object-fit:cover;border-radius:22px;">`;
    } else {
      els.profileAvatar.textContent = avatarText(user);
    }
  }

  function renderApp() {
    renderCategoryOptions(null);
    renderMetrics();
    renderCategoryBars();
    renderMovements();
    renderCategories();
    renderProfile();
    els.monthCaption.textContent = `Panoramica di ${state.monthLabel.toLowerCase()}`;
  }

  function entryById(entryId) {
    const targetId = Number(entryId);
    return state.entries.find((entry) => Number(entry.id) === targetId) || null;
  }

  function categoryById(categoryId) {
    return state.categories.find((category) => Number(category.id) === Number(categoryId)) || null;
  }

  async function refreshMe() {
    const data = await api("/api/me");
    if (!data.logged_in || !data.user) {
      state.me = null;
      showGate("auth");
      return;
    }
    state.me = data.user;
    showGate("app");
    els.welcomeName.textContent = `Ciao, ${state.me.name || "utente"}`;
  }

  async function refreshState(options = {}) {
    if (state.refreshPromise) return state.refreshPromise;
    const run = (async () => {
      const params = new URLSearchParams({
        month: state.month,
        profile_mode: state.profileMode,
        cycle_day: String(state.profileCycleDay),
      });
      const data = await api(`/api/state?${params.toString()}`);
      state.month = data.month;
      state.monthLabel = data.month_label;
      state.storageMode = data.storage_mode;
      state.categories = data.categories || [];
      state.entries = data.entries || [];
      state.summary = data.summary || state.summary;
      state.profilePeriod = data.profile_period || state.profilePeriod;
      state.profileSummary = data.profile_summary || state.profileSummary;
      state.bank = data.bank || state.bank;
      state.lastStateFetchAt = Date.now();
      renderApp();
      maybeAutoSyncBank();
    })();
    state.refreshPromise = run;
    try {
      await run;
    } finally {
      state.refreshPromise = null;
    }
  }

  async function saveEntry() {
    const payload = {
      entry_type: els.entryType.value,
      occurred_on: els.entryDate.value,
      title: els.entryTitle.value,
      amount: els.entryAmount.value,
      category_id: els.entryCategory.value || null,
      notes: els.entryNotes.value,
    };
    const url = state.editingEntryId ? `/api/entries/${state.editingEntryId}` : "/api/entries";
    const method = state.editingEntryId ? "PUT" : "POST";
    await api(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    closeEntryModal();
    await refreshState();
  }

  async function removeEntry(entryId) {
    if (!window.confirm("Eliminare questo movimento?")) return;
    await api(`/api/entries/${entryId}`, { method: "DELETE" });
    closeEntryModal();
    await refreshState();
  }

  async function saveQuickCategory() {
    await api("/api/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: els.quickCategoryName.value,
        color: els.quickCategoryColor.value,
        archived: false,
      }),
    });
    resetQuickCategoryForm();
    await refreshState();
  }

  async function saveCategory() {
    const payload = {
      name: els.categoryName.value,
      color: els.categoryColor.value,
      archived: els.categoryArchived.checked,
    };
    const url = state.editingCategoryId ? `/api/categories/${state.editingCategoryId}` : "/api/categories";
    const method = state.editingCategoryId ? "PUT" : "POST";
    await api(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    closeCategoryModal();
    await refreshState();
  }

  async function removeCategory(categoryId) {
    if (!window.confirm("Archiviare o eliminare questa categoria?")) return;
    await api(`/api/categories/${categoryId}`, { method: "DELETE" });
    closeCategoryModal();
    await refreshState();
  }

  async function connectBank() {
    const data = await api("/api/bank/connect", { method: "POST" });
    if (!data.redirect_url) {
      throw new Error("Il provider non ha restituito un URL di collegamento.");
    }
    window.location.assign(data.redirect_url);
  }

  function needsBankAutoSync() {
    const bank = state.bank || {};
    if (!bank.connected || !bank.configured) return false;
    if (state.bankSyncInFlight) return false;
    if (state.bankAutoSyncRequested) return true;
    if (!bank.last_sync_at) return true;
    const lastSync = new Date(String(bank.last_sync_at).replace(" ", "T"));
    if (Number.isNaN(lastSync.getTime())) return true;
    const ageMinutes = (Date.now() - lastSync.getTime()) / 60000;
    return ageMinutes >= Number(bank.auto_sync_minutes || 30);
  }

  async function syncBank(options = {}) {
    if (state.bankSyncInFlight) return;
    state.bankSyncInFlight = true;
    renderBank();
    try {
      const data = await api("/api/bank/sync", { method: "POST", timeoutMs: 25000 });
      state.bankFlash = options.preserveFlash && state.bankFlash
        ? state.bankFlash
        : { status: "success", message: data.message || "Saldo Postepay aggiornato." };
      state.bankAutoSyncRequested = false;
      state.bankAutoSyncDone = true;
      await refreshState();
    } catch (err) {
      state.bankFlash = { status: "error", message: err.message || "Sincronizzazione Postepay non riuscita." };
      state.bankAutoSyncRequested = false;
      state.bankAutoSyncDone = false;
      renderBank();
      throw err;
    } finally {
      state.bankSyncInFlight = false;
      renderBank();
    }
  }

  function maybeAutoSyncBank() {
    if (state.bankAutoSyncDone && !state.bankAutoSyncRequested) return;
    if (!needsBankAutoSync()) return;
    syncBank({ preserveFlash: true }).catch(() => {});
  }

  async function disconnectBank() {
    if (!window.confirm("Scollegare Postepay e rimuovere saldo e movimenti sincronizzati?")) return;
    const data = await api("/api/bank/disconnect", { method: "POST" });
    state.bankFlash = { status: "info", message: data.message || "Collegamento rimosso." };
    state.bankAutoSyncRequested = false;
    state.bankAutoSyncDone = false;
    await refreshState();
  }

  async function logout() {
    if (window.google && window.google.accounts && window.google.accounts.id) {
      window.google.accounts.id.disableAutoSelect();
    }
    await api("/auth/logout", { method: "POST" });
    state.me = null;
    state.bankFlash = null;
    showGate("auth");
    initGoogleSignIn();
  }

  function initGoogleSignIn() {
    if (!googleClientId || !els.googleSignin || googleInitialized) return;
    const waitForGoogle = () => {
      if (!(window.google && window.google.accounts && window.google.accounts.id)) {
        window.setTimeout(waitForGoogle, 200);
        return;
      }
      googleInitialized = true;
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        auto_select: true,
        callback: async (response) => {
          try {
            await api("/auth/google", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ credential: response.credential }),
            });
            await refreshMe();
            await refreshState();
            hideBootSplash();
          } catch (err) {
            alert(err.message);
          }
        },
      });
      window.google.accounts.id.renderButton(els.googleSignin, {
        theme: "outline",
        size: "large",
        shape: "pill",
        text: "continue_with",
        width: 280,
      });
      window.google.accounts.id.prompt();
    };
    waitForGoogle();
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register(`/service-worker.js?v=${encodeURIComponent(assetVersion)}`, { updateViaCache: "none" }).catch(() => {});
    });
  }

  function bindEvents() {
    els.navButtons.forEach((button) => {
      button.addEventListener("click", () => setActiveScreen(button.dataset.screen));
    });

    els.monthPrev.addEventListener("click", () => shiftMonth(-1));
    els.monthNext.addEventListener("click", () => shiftMonth(1));

    [els.headerAddEntry, els.movementsAddEntry, els.fabEntry].forEach((button) => {
      button.addEventListener("click", () => openEntryModal(null));
    });

    els.addCategory.addEventListener("click", () => {
      resetQuickCategoryForm();
      els.quickCategoryName.focus();
    });

    els.saveQuickCategory.addEventListener("click", () => {
      saveQuickCategory().catch((err) => alert(err.message));
    });

    els.closeEntryModal.addEventListener("click", closeEntryModal);
    els.closeCategoryModal.addEventListener("click", closeCategoryModal);

    els.entryModal.addEventListener("click", (event) => {
      if (event.target === els.entryModal) closeEntryModal();
    });

    els.categoryModal.addEventListener("click", (event) => {
      if (event.target === els.categoryModal) closeCategoryModal();
    });

    els.saveEntry.addEventListener("click", () => saveEntry().catch((err) => alert(err.message)));
    els.deleteEntry.addEventListener("click", () => {
      if (!state.editingEntryId) return;
      removeEntry(state.editingEntryId).catch((err) => alert(err.message));
    });

    els.saveCategory.addEventListener("click", () => saveCategory().catch((err) => alert(err.message)));
    els.deleteCategory.addEventListener("click", () => {
      if (!state.editingCategoryId) return;
      removeCategory(state.editingCategoryId).catch((err) => alert(err.message));
    });

    els.filterButtons.forEach((button) => {
      button.addEventListener("click", () => {
        state.filterType = button.dataset.filterType;
        els.filterButtons.forEach((item) => item.classList.toggle("active", item === button));
        renderMovements();
      });
    });

    els.profileModeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        state.profileMode = button.dataset.profileMode;
        refreshState().catch((err) => alert(err.message));
      });
    });

    els.profileCycleDay.addEventListener("change", () => {
      const nextDay = Number(els.profileCycleDay.value || 25);
      state.profileCycleDay = Math.max(1, Math.min(28, nextDay));
      if (state.profileMode === "cycle") {
        refreshState().catch((err) => alert(err.message));
      } else {
        els.profileCycleDay.value = String(state.profileCycleDay);
      }
    });

    els.searchInput.addEventListener("input", () => {
      state.search = els.searchInput.value || "";
      renderMovements();
    });

    els.movementList.addEventListener("click", (event) => {
      const action = event.target.closest("[data-entry-action]");
      if (!action) return;
      const entry = entryById(action.dataset.entryId);
      if (!entry) return;
      if (action.dataset.entryAction === "edit") {
        openEntryModal(entry);
      } else if (action.dataset.entryAction === "delete") {
        removeEntry(entry.id).catch((err) => alert(err.message));
      }
    });

    els.categoryGrid.addEventListener("click", (event) => {
      const action = event.target.closest("[data-category-action]");
      if (!action) return;
      const category = categoryById(action.dataset.categoryId);
      if (!category) return;
      if (action.dataset.categoryAction === "edit") {
        openCategoryModal(category);
      } else if (action.dataset.categoryAction === "delete") {
        removeCategory(category.id).catch((err) => alert(err.message));
      }
    });

    els.exportCsv.addEventListener("click", () => {
      const params = new URLSearchParams({
        month: state.month,
        profile_mode: state.profileMode,
        cycle_day: String(state.profileCycleDay),
      });
      window.open(`/api/export.csv?${params.toString()}`, "_blank");
    });

    els.logoutBtn.addEventListener("click", () => {
      logout().catch((err) => alert(err.message));
    });

    els.bankConnect.addEventListener("click", () => {
      connectBank().catch((err) => alert(err.message));
    });

    els.bankSync.addEventListener("click", () => {
      syncBank().catch((err) => alert(err.message));
    });

    els.bankDisconnect.addEventListener("click", () => {
      disconnectBank().catch((err) => alert(err.message));
    });

    if (els.devLogin) {
      els.devLogin.addEventListener("click", async () => {
        try {
          await api("/auth/dev-login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: els.devName.value,
              email: els.devEmail.value,
            }),
          });
          await refreshMe();
          await refreshState();
        } catch (err) {
          alert(err.message);
        }
      });
    }

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && state.me && (Date.now() - state.lastStateFetchAt) > 45000) {
        refreshState().catch(() => {});
      }
    });
  }

  async function boot() {
    document.title = appName;
    setMonthValue(els.body.dataset.month || new Date().toISOString().slice(0, 7));
    consumeBankFlashFromUrl();
    bindEvents();
    registerServiceWorker();

    try {
      await refreshMe();
      if (state.me) {
        await refreshState();
      } else {
        initGoogleSignIn();
      }
    } catch (err) {
      alert(err.message);
    } finally {
      hideBootSplash();
    }
  }

  boot();
})();
