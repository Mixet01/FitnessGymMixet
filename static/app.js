(function () {
  const state = {
    me: null,
    activeScreen: "screen-dashboard",
    month: "",
    monthLabel: "",
    storageMode: "database",
    categories: [],
    entries: [],
    recentEntries: [],
    summary: {
      expense_total: 0,
      income_total: 0,
      balance: 0,
      transaction_count: 0,
      average_expense: 0,
      daily_expense: 0,
      active_days: 0,
      savings_rate: null,
      category_totals: [],
      weekly_totals: [],
      top_category: null,
    },
    trend: [],
    filterType: "all",
    search: "",
    editingEntryId: null,
    editingCategoryId: null,
  };

  const els = {
    body: document.body,
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
    metricCount: document.getElementById("metric-count"),
    topCategoryTag: document.getElementById("top-category-tag"),
    categoryBars: document.getElementById("category-bars"),
    weekBars: document.getElementById("week-bars"),
    trendBars: document.getElementById("trend-bars"),
    recentList: document.getElementById("recent-list"),
    storageBadge: document.getElementById("storage-badge"),
    movementList: document.getElementById("movement-list"),
    categoryGrid: document.getElementById("category-grid"),
    searchInput: document.getElementById("search-input"),
    filterButtons: Array.from(document.querySelectorAll("[data-filter-type]")),
    navButtons: Array.from(document.querySelectorAll(".nav-btn")),
    screens: Array.from(document.querySelectorAll(".screen")),
    openMovements: document.getElementById("open-movements"),
    headerAddEntry: document.getElementById("header-add-entry"),
    movementsAddEntry: document.getElementById("movements-add-entry"),
    fabEntry: document.getElementById("fab-entry"),
    addCategory: document.getElementById("add-category"),
    exportCsv: document.getElementById("export-csv"),
    logoutBtn: document.getElementById("logout-btn"),
    profileName: document.getElementById("profile-name"),
    profileEmail: document.getElementById("profile-email"),
    profileAvatar: document.getElementById("profile-avatar"),
    profileAverage: document.getElementById("profile-average"),
    profileDaily: document.getElementById("profile-daily"),
    profileDays: document.getElementById("profile-days"),
    profileSavingRate: document.getElementById("profile-saving-rate"),
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
  const assetVersion = (els.body.dataset.assetVersion || "2026-05-18-v2").trim();
  const currencyFormatter = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
  const shortDateFormatter = new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short" });
  const monthFormatter = new Intl.DateTimeFormat("it-IT", { month: "long", year: "numeric" });

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

  function avatarText(user) {
    const base = String((user && (user.name || user.email)) || appName).trim();
    return base.slice(0, 2).toUpperCase();
  }

  async function api(url, options = {}) {
    const response = await fetch(url, { ...options, cache: "no-store" });
    let data = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      data = await response.json();
    }
    if (!response.ok) {
      throw new Error((data && data.message) || "Operazione non riuscita.");
    }
    return data;
  }

  function showGate(mode) {
    els.authGate.classList.toggle("hidden", mode !== "auth");
    els.appShell.classList.toggle("hidden", mode !== "app");
  }

  function setActiveScreen(screenId) {
    state.activeScreen = screenId;
    els.screens.forEach((screen) => screen.classList.toggle("active", screen.id === screenId));
    els.navButtons.forEach((button) => button.classList.toggle("active", button.dataset.screen === screenId));
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
      const suffix = category.archived ? " (archiviata)" : "";
      options.push(
        `<option value="${category.id}" ${Number(selectedId || 0) === Number(category.id) ? "selected" : ""}>${escapeHtml(category.name + suffix)}</option>`
      );
    });
    els.entryCategory.innerHTML = options.join("");
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
    els.metricBalanceNote.textContent = balance >= 0 ? "Bilancio in positivo" : "Bilancio da tenere d'occhio";
    els.metricExpense.textContent = formatMoney(state.summary.expense_total || 0);
    els.metricIncome.textContent = formatMoney(state.summary.income_total || 0);
    els.metricCount.textContent = String(state.summary.transaction_count || 0);
    const top = state.summary.top_category;
    els.topCategoryTag.textContent = top ? `${top.name} - ${formatMoney(top.amount)}` : "Nessuna";
    els.storageBadge.textContent = state.storageMode === "database" ? "supabase" : "file locale";
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

  function renderWeekBars() {
    const items = state.summary.weekly_totals || [];
    if (!items.length) {
      els.weekBars.innerHTML = "<div class='empty-state'>Nessun dato disponibile.</div>";
      return;
    }
    els.weekBars.innerHTML = items.map((item) => {
      const balanceClass = Number(item.balance || 0) >= 0 ? "income" : "expense";
      return `
        <article class="week-card">
          <span class="mini-label">Set ${escapeHtml(item.label)}</span>
          <strong class="${balanceClass}">${escapeHtml(formatMoney(item.balance))}</strong>
          <p class="helper">Spese ${escapeHtml(formatMoney(item.expense_total))}</p>
        </article>
      `;
    }).join("");
  }

  function renderTrendBars() {
    const items = state.trend || [];
    if (!items.length) {
      els.trendBars.innerHTML = "<div class='empty-state'>Trend non disponibile.</div>";
      return;
    }
    els.trendBars.innerHTML = items.map((item) => {
      const balanceClass = Number(item.balance || 0) >= 0 ? "income" : "expense";
      return `
        <article class="trend-card">
          <span class="mini-label">${escapeHtml(item.label)}</span>
          <strong class="${balanceClass}">${escapeHtml(formatMoney(item.balance))}</strong>
          <p class="helper">Uscite ${escapeHtml(formatMoney(item.expense_total))}</p>
        </article>
      `;
    }).join("");
  }

  function recentRowMarkup(entry) {
    const dotColor = entry.category ? entry.category.color : (entry.entry_type === "income" ? "#27e89d" : "#ff4d7a");
    const amountClass = entry.entry_type === "income" ? "income" : "expense";
    return `
      <article class="recent-row" data-entry-id="${entry.id}">
        <span class="dot" style="background:${escapeHtml(dotColor)};"></span>
        <div class="recent-copy">
          <strong>${escapeHtml(entry.title)}</strong>
          <p>${escapeHtml(formatShortDate(entry.occurred_on))}${entry.category ? ` - ${escapeHtml(entry.category.name)}` : ""}</p>
        </div>
        <div class="movement-amount">
          <strong class="${amountClass}">${escapeHtml(formatMoney(entry.amount))}</strong>
        </div>
      </article>
    `;
  }

  function renderRecentEntries() {
    if (!state.recentEntries.length) {
      els.recentList.innerHTML = "<div class='empty-state'>Ancora nessun movimento salvato.</div>";
      return;
    }
    els.recentList.innerHTML = state.recentEntries.map(recentRowMarkup).join("");
  }

  function filteredEntries() {
    const term = state.search.trim().toLowerCase();
    return state.entries.filter((entry) => {
      if (state.filterType !== "all" && entry.entry_type !== state.filterType) return false;
      if (!term) return true;
      const haystack = `${entry.title} ${entry.notes} ${(entry.category && entry.category.name) || ""}`.toLowerCase();
      return haystack.includes(term);
    });
  }

  function movementRowMarkup(entry) {
    const dotColor = entry.category ? entry.category.color : (entry.entry_type === "income" ? "#27e89d" : "#ff4d7a");
    const amountClass = entry.entry_type === "income" ? "income" : "expense";
    const categoryLabel = entry.category ? entry.category.name : "Senza categoria";
    return `
      <article class="movement-row" data-entry-id="${entry.id}">
        <span class="dot" style="background:${escapeHtml(dotColor)};"></span>
        <div class="movement-copy">
          <strong>${escapeHtml(entry.title)}</strong>
          <p>${escapeHtml(formatShortDate(entry.occurred_on))} - ${escapeHtml(categoryLabel)}</p>
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

  function renderProfile() {
    const user = state.me || {};
    els.profileName.textContent = user.name || "Profilo";
    els.profileEmail.textContent = user.email || "";
    els.profileAverage.textContent = formatMoney(state.summary.average_expense || 0);
    els.profileDaily.textContent = formatMoney(state.summary.daily_expense || 0);
    els.profileDays.textContent = String(state.summary.active_days || 0);
    els.profileSavingRate.textContent = state.summary.savings_rate == null ? "-" : `${state.summary.savings_rate}%`;

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
    renderWeekBars();
    renderTrendBars();
    renderRecentEntries();
    renderMovements();
    renderCategories();
    renderProfile();
    els.monthCaption.textContent = `Panoramica di ${state.monthLabel.toLowerCase()}`;
  }

  function entryById(entryId) {
    const targetId = Number(entryId);
    return state.entries.find((entry) => Number(entry.id) === targetId)
      || state.recentEntries.find((entry) => Number(entry.id) === targetId)
      || null;
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

  async function refreshState() {
    const data = await api(`/api/state?month=${encodeURIComponent(state.month)}`);
    state.month = data.month;
    state.monthLabel = data.month_label;
    state.storageMode = data.storage_mode;
    state.categories = data.categories || [];
    state.entries = data.entries || [];
    state.recentEntries = data.recent_entries || [];
    state.summary = data.summary || state.summary;
    state.trend = data.trend || [];
    renderApp();
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

  async function logout() {
    if (window.google && window.google.accounts && window.google.accounts.id) {
      window.google.accounts.id.disableAutoSelect();
    }
    await api("/auth/logout", { method: "POST" });
    state.me = null;
    showGate("auth");
  }

  function initGoogleSignIn() {
    if (!googleClientId || !els.googleSignin) return;
    const waitForGoogle = () => {
      if (!(window.google && window.google.accounts && window.google.accounts.id)) {
        window.setTimeout(waitForGoogle, 200);
        return;
      }
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
    els.openMovements.addEventListener("click", () => setActiveScreen("screen-movements"));

    [els.headerAddEntry, els.movementsAddEntry, els.fabEntry].forEach((button) => {
      button.addEventListener("click", () => openEntryModal(null));
    });
    els.addCategory.addEventListener("click", () => openCategoryModal(null));

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

    els.recentList.addEventListener("click", (event) => {
      const row = event.target.closest("[data-entry-id]");
      if (!row) return;
      const entry = entryById(row.dataset.entryId);
      if (!entry) return;
      setActiveScreen("screen-movements");
      openEntryModal(entry);
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
      window.open(`/api/export.csv?month=${encodeURIComponent(state.month)}`, "_blank");
    });

    els.logoutBtn.addEventListener("click", () => {
      logout().catch((err) => alert(err.message));
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
      if (!document.hidden && state.me) {
        refreshState().catch(() => {});
      }
    });
  }

  async function boot() {
    document.title = appName;
    setMonthValue(els.body.dataset.month || new Date().toISOString().slice(0, 7));
    bindEvents();
    initGoogleSignIn();
    registerServiceWorker();

    try {
      await refreshMe();
      if (state.me) {
        await refreshState();
      }
    } catch (err) {
      alert(err.message);
    }
  }

  boot();
})();
