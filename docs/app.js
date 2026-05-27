/* global MiniSearch */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const journalByNum = new Map();
  const specById = new Map();
  const linksByJournal = new Map();
  const linksBySpec = new Map();

  let data = null;
  let mode = "spec";
  let journalSearch = null;
  let selectedJournal = null;
  let selectedSpec = null;
  const validModes = new Set(["journal", "spec"]);
  const urlStateDebounceMs = 300;
  const dateFilterParam = "date_filter";
  const dateParam = "date";
  const scopusFilterParam = "scopus";
  const rcsiLevelParam = "rcsi_level";
  const vakCatParam = "vak_cat";
  const defaultTitle = "Перечень рецензируемых изданий ВАК — поиск";
  const defaultDescription =
    "Поиск журналов ВАК для публикаций по кандидатским и докторским диссертациям: научные специальности, паспорта специальностей, ISSN, даты включения и исключения из перечня.";
  const popularSpecCodes = [
    "5.2.3.",
    "2.3.1.",
    "5.2.6.",
    "5.8.7.",
    "5.8.2.",
    "2.3.3.",
    "2.3.4.",
    "5.2.4.",
    "5.8.1.",
    "1.2.2.",
    "5.3.9.",
    "12.00.08",
  ];
  let urlStateTimer = null;

  const el = {
    loading: $("#loading"),
    app: $("#app"),
    metaAsOf: $("#meta-as-of"),
    search: $("#search"),
    searchLabel: $("#search-label"),
    searchHint: $("#search-hint"),
    suggestions: $("#suggestions"),
    filterDate: $("#filter-date"),
    date: $("#date"),
    filterScopus: $("#filter-scopus"),
    filterRcsiLevel: $("#filter-rcsi-level"),
    filterVakCat: $("#filter-vak-cat"),
    resultsPanel: $("#results-panel"),
    resultsTitle: $("#results-title"),
    resultsMeta: $("#results-meta"),
    resultsBody: $("#results-body"),
    emptyState: $("#empty-state"),
    popularSpecialties: $("#popular-specialties"),
    tabJournal: $("#tab-journal"),
    tabSpec: $("#tab-spec"),
  };

  function dataUrl() {
    return new URL("data/vak.json", window.location.href).href;
  }

  function setMeta(name, value) {
    const tag = document.querySelector(`meta[name="${name}"]`);
    if (tag) tag.setAttribute("content", value);
  }

  function setPropertyMeta(property, value) {
    const tag = document.querySelector(`meta[property="${property}"]`);
    if (tag) tag.setAttribute("content", value);
  }

  function setPageMeta(title, description) {
    document.title = title;
    setMeta("description", description);
    setMeta("twitter:title", title);
    setMeta("twitter:description", description);
    setPropertyMeta("og:title", title);
    setPropertyMeta("og:description", description);
    setPropertyMeta("og:url", window.location.href);
  }

  function resetPageMeta() {
    setPageMeta(defaultTitle, defaultDescription);
  }

  function activeOn(link, isoDate) {
    if (!isoDate) return true;
    if (link.from_iso && isoDate < link.from_iso) return false;
    if (link.to_iso && isoDate > link.to_iso) return false;
    return true;
  }

  function filterIso() {
    return el.filterDate.checked ? el.date.value : null;
  }

  /* ---- Journal-level filters ---- */

  function journalPassesScopus(j) {
    if (!el.filterScopus.checked) return true;
    return j.scopus && j.scopus.inScopus === true;
  }

  function journalRcsiLevel(j) {
    const r = j.rcsi;
    if (!r || !r.inRcsi) return null;
    return r.level_2025 ?? r.level_2023 ?? null;
  }

  function journalPassesRcsi(j) {
    const val = el.filterRcsiLevel.value;
    if (!val) return true; // "не важно"
    if (val === "any") {
      return j.rcsi && j.rcsi.inRcsi === true;
    }
    const level = journalRcsiLevel(j);
    if (level === null) return false;
    // val is "1", "1+2", or "1+2+3" — match if level <= max in expression
    const maxLevel = parseInt(val.split("+").pop(), 10);
    return level <= maxLevel;
  }

  function journalPassesVakCat(j) {
    const val = el.filterVakCat.value;
    if (!val) return true;
    return j.vak_cat === val;
  }

  function journalPassesFilters(j) {
    return journalPassesScopus(j) && journalPassesRcsi(j) && journalPassesVakCat(j);
  }

  function anyFiltersActive() {
    return el.filterScopus.checked || el.filterRcsiLevel.value !== "" || el.filterVakCat.value !== "";
  }

  /* ---- Specialty helpers with filters ---- */

  function specialtyHasPassingJournal(s) {
    const links = linksBySpec.get(s.id) || [];
    const iso = filterIso();
    return links.some((l) => {
      if (iso && !activeOn(l, iso)) return false;
      const j = journalByNum.get(l.j);
      return j && journalPassesFilters(j);
    });
  }

  function countPassingJournals(s) {
    const links = linksBySpec.get(s.id) || [];
    const iso = filterIso();
    let count = 0;
    for (const l of links) {
      if (iso && !activeOn(l, iso)) continue;
      const j = journalByNum.get(l.j);
      if (j && journalPassesFilters(j)) count++;
    }
    return count;
  }

  function totalPassingInSpecFilter(s) {
    /* total journals for this specialty before journal-level filters */
    const links = linksBySpec.get(s.id) || [];
    const iso = filterIso();
    if (!iso) return links.length;
    return links.filter((l) => activeOn(l, iso)).length;
  }

  /* ---- End filter helpers ---- */

  function formatDates(link) {
    const parts = [];
    const note = link.date_notes ? ` title="${escapeHtml(link.date_notes)}"` : "";
    const fromClass = link.from_unreliable ? "from unreliable" : "from";
    const toClass = link.to_unreliable ? "to unreliable" : "to";
    if (link.from) {
      const mark = link.from_unreliable ? " (?)" : "";
      parts.push(`<span class="${fromClass}"${note}>с ${escapeHtml(link.from)}${mark}</span>`);
    }
    if (link.to) {
      const mark = link.to_unreliable ? " (?)" : "";
      parts.push(`<span class="${toClass}"${note}>по ${escapeHtml(link.to)}${mark}</span>`);
    }
    if (!parts.length) return '<span class="muted">даты не указаны</span>';
    return parts.join(" · ");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function normalizeForMatch(s) {
    return String(s || "")
      .trim()
      .replace(/\s+/g, " ")
      .toLocaleLowerCase("ru-RU");
  }

  function normalizeSpecCode(code) {
    return String(code || "").replace(/\s+/g, "").replace(/\.$/, "");
  }

  function isIsoDate(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(value || "");
  }

  /* ---- URL state ---- */

  function readDateFilterState(params) {
    const rawFilter = params.get(dateFilterParam);
    const rawDate = params.get(dateParam);
    const filterOffValues = new Set(["0", "false", "off", "no"]);
    return {
      filterDate:
        rawFilter == null ? null : !filterOffValues.has(rawFilter.trim().toLowerCase()),
      date: isIsoDate(rawDate) ? rawDate : null,
    };
  }

  function applyDateFilterState(state) {
    if (state.date) {
      el.date.value = state.date;
    }
    if (state.filterDate != null) {
      el.filterDate.checked = state.filterDate;
    }
    el.date.disabled = !el.filterDate.checked;
  }

  function writeDateFilterState(url) {
    url.searchParams.set(dateFilterParam, el.filterDate.checked ? "1" : "0");
    if (el.date.value) {
      url.searchParams.set(dateParam, el.date.value);
    } else {
      url.searchParams.delete(dateParam);
    }
  }

  function readJournalFilterState(params) {
    return {
      filterScopus: params.get(scopusFilterParam) === "1",
      rcsiLevel: params.get(rcsiLevelParam) || "",
      vakCat: params.get(vakCatParam) || "",
    };
  }

  function applyJournalFilterState(state) {
    el.filterScopus.checked = state.filterScopus;
    el.filterRcsiLevel.value = state.rcsiLevel;
    if (state.rcsiLevel && !["", "any", "1", "1+2", "1+2+3"].includes(state.rcsiLevel)) {
      el.filterRcsiLevel.value = "";
    }
    el.filterVakCat.value = state.vakCat;
    if (state.vakCat && !["", "К1", "К2", "К3"].includes(state.vakCat)) {
      el.filterVakCat.value = "";
    }
  }

  function writeJournalFilterState(url) {
    url.searchParams.set(scopusFilterParam, el.filterScopus.checked ? "1" : "0");
    const r = el.filterRcsiLevel.value;
    if (r) {
      url.searchParams.set(rcsiLevelParam, r);
    } else {
      url.searchParams.delete(rcsiLevelParam);
    }
    const v = el.filterVakCat.value;
    if (v) {
      url.searchParams.set(vakCatParam, v);
    } else {
      url.searchParams.delete(vakCatParam);
    }
  }

  function readUrlState() {
    const params = new URLSearchParams(window.location.search);
    const urlMode = params.get("mode");
    return {
      mode: validModes.has(urlMode) ? urlMode : "spec",
      query: params.get("q") || "",
      journal: Number(params.get("journal")) || null,
      spec: Number(params.get("spec")) || null,
      dateFilter: readDateFilterState(params),
      journalFilter: readJournalFilterState(params),
    };
  }

  function writeUrlState() {
    if (urlStateTimer) {
      window.clearTimeout(urlStateTimer);
      urlStateTimer = null;
    }

    const url = new URL(window.location.href);
    url.searchParams.set("mode", mode);
    const query = el.search.value.trim();
    if (query) {
      url.searchParams.set("q", query);
    } else {
      url.searchParams.delete("q");
    }
    url.searchParams.delete("journal");
    url.searchParams.delete("spec");
    if (mode === "journal" && selectedJournal != null) {
      url.searchParams.set("journal", String(selectedJournal));
    }
    if (mode === "spec" && selectedSpec != null) {
      url.searchParams.set("spec", String(selectedSpec));
    }
    writeDateFilterState(url);
    writeJournalFilterState(url);
    window.history.replaceState({ mode, query }, "", url);
  }

  function debounceUrlState() {
    if (urlStateTimer) window.clearTimeout(urlStateTimer);
    urlStateTimer = window.setTimeout(() => {
      urlStateTimer = null;
      writeUrlState();
    }, urlStateDebounceMs);
  }

  function indexLinks() {
    for (const link of data.links) {
      if (!linksByJournal.has(link.j)) linksByJournal.set(link.j, []);
      linksByJournal.get(link.j).push(link);
      if (!linksBySpec.has(link.s)) linksBySpec.set(link.s, []);
      linksBySpec.get(link.s).push(link);
    }
  }

  function initSearch() {
    journalSearch = new MiniSearch({
      fields: ["name", "issn", "search"],
      storeFields: ["n", "name", "issn"],
      searchOptions: { prefix: true, fuzzy: 0.15, boost: { name: 2, issn: 1.5 } },
    });
    journalSearch.addAll(
      data.journals.map((j) => ({
        id: j.n,
        n: j.n,
        name: j.name,
        issn: j.issn || "",
        search: j.search,
      }))
    );
  }

  function setMode(next, options = {}) {
    const { syncUrl = true, focus = true } = options;
    mode = next;
    selectedJournal = null;
    selectedSpec = null;
    el.tabJournal.classList.toggle("active", mode === "journal");
    el.tabSpec.classList.toggle("active", mode === "spec");
    el.tabJournal.setAttribute("aria-selected", mode === "journal");
    el.tabSpec.setAttribute("aria-selected", mode === "spec");
    el.searchLabel.textContent = mode === "journal" ? "Журнал" : "Специальность";
    el.search.placeholder =
      mode === "journal"
        ? "Название, ISSN или № в перечне"
        : "Код или название специальности";
    el.search.value = "";
    el.suggestions.hidden = true;
    el.resultsPanel.hidden = true;
    el.emptyState.hidden = false;
    el.searchHint.textContent = "";
    resetPageMeta();
    if (syncUrl) writeUrlState();
    if (focus) el.search.focus();
  }

  function isNumericQuery(q) {
    return /^[\d.\-\s]+$/.test(q.trim());
  }

  function specialtyHit(s) {
    return {
      id: s.id,
      code: s.code,
      title: s.title,
      branch: s.branch,
      type: s.type,
    };
  }

  function searchSpecialties(q, limit = 12) {
    const needle = q.trim();
    const normalizedNeedle = normalizeForMatch(needle);
    const iso = filterIso();
    const filtersActive = anyFiltersActive();

    const candidates = data.specialties.filter((s) => {
      /* date filter: specialty must have at least one active link */
      if (iso && !(linksBySpec.get(s.id) || []).some((l) => activeOn(l, iso))) {
        return false;
      }
      /* journal-level filters: specialty must have at least one passing journal */
      if (filtersActive && !specialtyHasPassingJournal(s)) {
        return false;
      }
      return true;
    });

    if (!isNumericQuery(q)) {
      return candidates
        .filter((s) => {
          return normalizeForMatch([s.code, s.branch, s.title].filter(Boolean).join(" ")).includes(
            normalizedNeedle
          );
        })
        .sort((a, b) => a.code.localeCompare(b.code, "ru-RU", { numeric: true }))
        .slice(0, limit)
        .map(specialtyHit);
    }

    return candidates
      .filter((s) => s.code.startsWith(needle))
      .sort((a, b) => a.code.localeCompare(b.code, "ru-RU", { numeric: true }))
      .slice(0, limit)
      .map(specialtyHit);
  }

  function refreshSearchIfTyping() {
    const query = el.search.value.trim();
    if (!query || selectedJournal != null || selectedSpec != null) return;
    runSearch(query);
  }

  function specialtyQuery(s) {
    const branch = s.branch ? ` (${s.branch})` : "";
    return `${s.code} ${s.title}${branch}`;
  }

  function specialtyUrl(s) {
    const url = new URL(window.location.href);
    url.searchParams.set("mode", "spec");
    url.searchParams.set("q", specialtyQuery(s));
    url.searchParams.set("spec", String(s.id));
    url.searchParams.delete("journal");
    writeDateFilterState(url);
    writeJournalFilterState(url);
    return url.href;
  }

  function journalUrl(j) {
    const url = new URL(window.location.href);
    url.searchParams.set("mode", "journal");
    url.searchParams.set("q", j.name);
    url.searchParams.set("journal", String(j.n));
    url.searchParams.delete("spec");
    writeDateFilterState(url);
    writeJournalFilterState(url);
    return url.href;
  }

  function specialtyJournalCount(s) {
    return countPassingJournals(s);
  }

  function renderPopularSpecialties() {
    if (!el.popularSpecialties) return;

    const selected = [];
    const selectedIds = new Set();
    const bestByCode = new Map();

    for (const s of data.specialties) {
      if (!specialtyHasPassingJournal(s)) continue;
      const code = normalizeSpecCode(s.code);
      const current = bestByCode.get(code);
      if (!current || specialtyJournalCount(s) > specialtyJournalCount(current)) {
        bestByCode.set(code, s);
      }
    }

    for (const code of popularSpecCodes) {
      const s = bestByCode.get(normalizeSpecCode(code));
      if (s && !selectedIds.has(s.id)) {
        selected.push(s);
        selectedIds.add(s.id);
      }
    }

    const topByJournalCount = [...data.specialties]
      .filter((s) => specialtyHasPassingJournal(s))
      .sort((a, b) => specialtyJournalCount(b) - specialtyJournalCount(a));
    for (const s of topByJournalCount) {
      if (selected.length >= 16) break;
      if (!selectedIds.has(s.id)) {
        selected.push(s);
        selectedIds.add(s.id);
      }
    }

    el.popularSpecialties.innerHTML = selected
      .map((s) => {
        const branch = s.branch ? `<span>${escapeHtml(s.branch)}</span>` : "";
        return `<a class="popular-card" href="${escapeHtml(specialtyUrl(s))}">
          <strong>${escapeHtml(s.code)} ${escapeHtml(s.title)}</strong>
          ${branch}
          <small>${specialtyJournalCount(s)} журналов ВАК</small>
        </a>`;
      })
      .join("");
  }

  function rcsiSearchUrl(j) {
    const url = new URL("https://journalrank.rcsi.science/ru/record-sources/");
    url.searchParams.set("s", j.issn || j.name);
    url.searchParams.set("adv", "true");
    return url.href;
  }

  function renderRcsiBlock(j) {
    const r = j.rcsi;
    if (!r) return "";

    if (!r.inRcsi) {
      return `<section class="rcsi-card">
        <p class="rcsi-status-link"><a href="${escapeHtml(rcsiSearchUrl(j))}" target="_blank" rel="noopener">Проверить в официальном поиске РЦНИ</a></p>
      </section>`;
    }

    const levelParts = [];
    if (r.level_2025 != null) levelParts.push(`2025: уровень ${escapeHtml(String(r.level_2025))}`);
    if (r.level_2023 != null) levelParts.push(`2023: уровень ${escapeHtml(String(r.level_2023))}`);

    const dateParts = [];
    if (r.dateAccepted) dateParts.push(`включён ${escapeHtml(formatIsoRu(r.dateAccepted))}`);
    if (r.dateDiscontinued) dateParts.push(`исключён ${escapeHtml(formatIsoRu(r.dateDiscontinued))}`);

    const detailsId = r.id;
    const detailsUrl = detailsId
      ? `https://journalrank.rcsi.science/ru/record-sources/details/${encodeURIComponent(detailsId)}/`
      : null;

    const rows = [];
    rows.push(`<section class="rcsi-card">`);
    rows.push(`<div class="rcsi-heading"><strong>Белый список РЦНИ</strong></div>`);
    if (levelParts.length) {
      rows.push(`<p class="rcsi-levels">${levelParts.join(" · ")}</p>`);
    }
    if (dateParts.length) {
      rows.push(`<p class="rcsi-dates">${dateParts.join(" · ")}</p>`);
    }
    if (detailsUrl) {
      rows.push(`<p><a href="${escapeHtml(detailsUrl)}" target="_blank" rel="noopener">Карточка РЦНИ</a></p>`);
    }
    rows.push("</section>");
    return rows.join("");
  }

  function renderPassportLink(s) {
    if (!s.passport || !s.passport.url) return "";
    return `<div class="spec-tools">
      <a class="primary-link" href="${escapeHtml(s.passport.url)}" target="_blank" rel="noopener">
        Паспорт специальности ВАК
      </a>
      <span>${escapeHtml(s.passport.title || s.title)}</span>
    </div>`;
  }

  /* ---- Scopus ---- */

  function renderScopusBlock(j) {
    const s = j.scopus;
    if (!s && !j.issn) return "";

    if (s && s.inScopus) {
      const fetchedInfo = data.meta.scopus_fetched_at
        ? `<span class="rcsi-note">от ${formatIsoRu(data.meta.scopus_fetched_at.slice(0, 10))}</span>`
        : "";
      const metrics = [];
      if (s.citeScore != null) metrics.push(`CiteScore ${s.citeScore} (${s.citeScoreYear || "?"})`);
      if (s.sjr && s.sjr.length) metrics.push(`SJR ${s.sjr[0].value} (${s.sjr[0].year})`);
      if (s.snip && s.snip.length) metrics.push(`SNIP ${s.snip[0].value} (${s.snip[0].year})`);

      let linkHtml = "";
      if (s.scopusLink) {
        linkHtml = `<p><a href="${escapeHtml(s.scopusLink)}" target="_blank" rel="noopener">Карточка источника в Scopus</a></p>`;
      }

      return `<section class="rcsi-card"><div class="rcsi-status">
        <div class="rcsi-heading">
          <strong>Scopus</strong>
          ${fetchedInfo}
        </div>
        <p class="rcsi-levels">${escapeHtml(metrics.join(" · "))}</p>
        ${linkHtml}
        </div>
      </section>`;
    }

    if (s) {
      return `<section class="rcsi-card">
        <p class="rcsi-status-link"><a href="https://www.scopus.com/sources?searchField=issn&searchValue=${encodeURIComponent(j.issn)}" target="_blank" rel="noopener">Проверить в Scopus</a></p>
      </section>`;
    }

    if (j.issn) {
      return `<section class="rcsi-card">
        <p class="rcsi-status-link"><a href="https://www.scopus.com/sources?searchField=issn&searchValue=${encodeURIComponent(j.issn)}" target="_blank" rel="noopener">Проверить в Scopus</a></p>
      </section>`;
    }

    return "";
  }

  function renderVakBlock(j) {
    if (!j.vak_cat) return "";
    return `<section class="rcsi-card"><div class="rcsi-heading">
      <strong>Категория ВАК</strong>
    </div>
    <p class="rcsi-levels">${escapeHtml(j.vak_cat)}</p>
    </section>`;
  }

  function runSearch(q) {
    if (!q || q.length < 2) {
      el.suggestions.hidden = true;
      return;
    }
    const hits = mode === "journal"
      ? journalSearch.search(q, { limit: 12 })
      : searchSpecialties(q);
    if (!hits.length) {
      el.suggestions.hidden = true;
      el.searchHint.textContent = "Ничего не найдено. Уточните запрос.";
      return;
    }
    el.searchHint.textContent = "";
    el.suggestions.innerHTML = hits
      .map((h) => {
        if (mode === "journal") {
          const j = journalByNum.get(h.n);
          return `<li><button type="button" data-journal="${j.n}">
            <strong>№ ${j.n}</strong> ${escapeHtml(j.name)}
            <span class="sub">${j.issn ? "ISSN " + escapeHtml(j.issn) : "ISSN не указан"}</span>
          </button></li>`;
        }
        const s = specById.get(h.id);
        const branch = s.branch ? `<strong class="branch">${escapeHtml(s.branch)}</strong>` : "";
        return `<li><button type="button" data-spec="${s.id}">
            <strong class="code">${escapeHtml(s.code)}</strong> ${branch} ${escapeHtml(s.title)}
            <span class="sub">${s.type === "diss" ? "код диссертации" : "номенклатура"}</span>
          </button></li>`;
      })
      .join("");
    el.suggestions.hidden = false;
  }

  function renderFilterBadges() {
    const badges = [];
    if (el.filterScopus.checked) {
      badges.push("Scopus ✓");
    }
    const r = el.filterRcsiLevel.value;
    if (r === "any") {
      badges.push("РЦНИ есть");
    } else if (r) {
      badges.push(`РЦНИ ур. ${r}`);
    }
    if (el.filterVakCat.value) {
      badges.push(`ВАК ${el.filterVakCat.value}`);
    }
    return badges.length ? `<span class="filter-badges">${badges.map((b) => `<span class="badge">${b}</span>`).join(" ")}</span>` : "";
  }

  function renderJournalResults(journalNum) {
    const j = journalByNum.get(journalNum);
    if (!j) return;
    const iso = filterIso();
    let links = linksByJournal.get(journalNum) || [];
    links = links.filter((l) => activeOn(l, iso));

    el.resultsTitle.textContent = j.name;
    el.resultsMeta.innerHTML = [
      `№ ${j.n} в перечне`,
      j.issn ? `ISSN ${escapeHtml(j.issn)}` : null,
      iso ? `актуально на ${formatIsoRu(iso)}` : null,
      `${links.length} специальностей`,
    ]
      .filter(Boolean)
      .join(" · ");

    setPageMeta(
      `${j.name} — журнал ВАК`,
      `Журнал «${j.name}» в Перечне ВАК: ISSN ${j.issn || "не указан"}, ${links.length} специальностей${iso ? ` на ${formatIsoRu(iso)}` : ""}.`
    );

    if (!links.length) {
      el.resultsBody.innerHTML =
        `<div class="indexing-row">${renderVakBlock(j)}${renderRcsiBlock(j)}${renderScopusBlock(j)}</div>
        <p class="hint">Нет специальностей для выбранных условий (проверьте фильтр по дате).</p>`;
      return;
    }

    const groups = new Map();
    for (const link of links) {
      const key = link.g;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(link);
    }

    let html = `<div class="indexing-row">${renderVakBlock(j)}${renderRcsiBlock(j)}${renderScopusBlock(j)}</div>`;
    const sortedGroups = [...groups.keys()].sort((a, b) => a - b);
    for (const g of sortedGroups) {
      const items = groups.get(g);
      const sample = items[0];
      const groupDates = formatDates(sample);
      if (sortedGroups.length > 1) {
        html += `<p class="group-label">Группа ${g + 1} · ${groupDates}</p>`;
      }
      html += '<ul class="result-list">';
      for (const link of items) {
        const s = specById.get(link.s);
        const branch = s.branch
          ? `<span class="branch">${escapeHtml(s.branch)}</span>`
          : "";
        const dates =
          sortedGroups.length === 1
            ? `<p class="dates">${formatDates(link)}</p>`
            : "";
        html += `<li class="result-item clickable">
          <a class="result-link" href="${escapeHtml(specialtyUrl(s))}">
            <p class="spec-heading"><span class="code">${escapeHtml(s.code)}</span> ${branch}</p>
            <p class="title">${escapeHtml(s.title)}</p>
            ${dates}
          </a>
        </li>`;
      }
      html += "</ul>";
    }
    el.resultsBody.innerHTML = html;
  }

  function renderJournalIndexBadges(j) {
    const parts = [];
    if (j.scopus && j.scopus.inScopus) {
      parts.push(`<span class="idx-badge scopus">Scopus</span>`);
    }
    const r = j.rcsi;
    if (r && r.inRcsi) {
      const level = r.level_2025 ?? r.level_2023;
      parts.push(`<span class="idx-badge rcsi">РЦНИ${level != null ? " " + level : ""}</span>`);
    }
    if (j.vak_cat) {
      parts.push(`<span class="idx-badge vak-cat">${escapeHtml(j.vak_cat)}</span>`);
    }
    return parts.length ? `<span class="idx-badges">${parts.join("")}</span>` : "";
  }

  function renderSpecResults(specId) {
    const s = specById.get(specId);
    if (!s) return;
    const iso = filterIso();
    let links = linksBySpec.get(specId) || [];
    links = links.filter((l) => activeOn(l, iso));
    /* Apply journal-level filters */
    links = links.filter((l) => {
      const j = journalByNum.get(l.j);
      return j && journalPassesFilters(j);
    });

    const branch = s.branch ? `<span class="branch">${escapeHtml(s.branch)}</span>` : "";
    el.resultsTitle.innerHTML = `<span class="code">${escapeHtml(s.code)}</span> ${branch} ${escapeHtml(s.title)}`;

    const totalBeforeFilter = totalPassingInSpecFilter(s);
    const filterBadges = renderFilterBadges();
    const countInfo = anyFiltersActive()
      ? `${links.length} из ${totalBeforeFilter} журналов`
      : `${links.length} журналов`;

    el.resultsMeta.innerHTML = [
      iso ? `актуально на ${formatIsoRu(iso)}` : null,
      countInfo,
      filterBadges || null,
    ]
      .filter(Boolean)
      .join(" · ");

    setPageMeta(
      `${s.code} ${s.title} — журналы ВАК`,
      `Журналы из Перечня ВАК по специальности ${s.code} ${s.title}: ${links.length} журналов${s.passport ? ", есть ссылка на паспорт специальности" : ""}${iso ? ` на ${formatIsoRu(iso)}` : ""}.`
    );

    if (!links.length) {
      el.resultsBody.innerHTML =
        `${renderPassportLink(s)}
        <p class="hint">Нет журналов для выбранных условий (проверьте фильтры).</p>`;
      return;
    }

    links.sort((a, b) => a.j - b.j);
    let html = `${renderPassportLink(s)}<ul class="result-list">`;
    for (const link of links) {
      const j = journalByNum.get(link.j);
      const issnHtml = j.issn ? `<span class="branch">ISSN ${escapeHtml(j.issn)}</span>` : "";
      const sep = j.issn ? `<span class="meta-sep">·</span>` : "";
      html += `<li class="result-item clickable">
        <a class="result-link" href="${escapeHtml(journalUrl(j))}">
          <strong>№ ${j.n}</strong> ${escapeHtml(j.name)}
          <div class="journal-meta-row">
            <span class="journal-meta-left">
              <span class="dates">${formatDates(link)}</span>
              ${sep} ${issnHtml}
            </span>
            <span class="journal-meta-right">${renderJournalIndexBadges(j)}</span>
          </div>
        </a>
      </li>`;
    }
    html += "</ul>";
    el.resultsBody.innerHTML = html;
  }

  function formatIsoRu(iso) {
    const [y, m, d] = iso.split("-");
    return `${d}.${m}.${y}`;
  }

  function showResults() {
    el.emptyState.hidden = true;
    el.resultsPanel.hidden = false;
    if (mode === "journal" && selectedJournal != null) {
      renderJournalResults(selectedJournal);
    } else if (mode === "spec" && selectedSpec != null) {
      renderSpecResults(selectedSpec);
    }
  }

  function applyUrlState() {
    const state = readUrlState();
    setMode(state.mode, { syncUrl: false, focus: false });
    applyDateFilterState(state.dateFilter);
    applyJournalFilterState(state.journalFilter);
    el.search.value = state.query;
    selectedJournal = null;
    selectedSpec = null;
    el.suggestions.hidden = true;

    if (mode === "journal" && state.journal != null && journalByNum.has(state.journal)) {
      selectedJournal = state.journal;
    } else if (mode === "spec" && state.spec != null && specById.has(state.spec)) {
      selectedSpec = state.spec;
    }

    if (selectedJournal != null || selectedSpec != null) {
      showResults();
    } else if (state.query.trim()) {
      runSearch(state.query.trim());
    }

    writeUrlState();
  }

  async function load() {
    const res = await fetch(dataUrl());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();

    for (const j of data.journals) journalByNum.set(j.n, j);
    for (const s of data.specialties) specById.set(s.id, s);
    indexLinks();
    initSearch();

    el.metaAsOf.textContent = data.meta.as_of_label || `по состоянию на ${data.meta.as_of}`;
    if (data.meta.editions_url) {
      $("#link-official").href = data.meta.editions_url;
    }

    const today = new Date().toISOString().slice(0, 10);
    el.date.value = today;
    el.filterDate.checked = true;
    el.date.disabled = false;

    el.loading.hidden = true;
    el.app.hidden = false;
    applyUrlState();
    renderPopularSpecialties();
  }

  el.tabJournal.addEventListener("click", () => setMode("journal"));
  el.tabSpec.addEventListener("click", () => setMode("spec"));

  el.search.addEventListener("input", () => {
    selectedJournal = null;
    selectedSpec = null;
    el.resultsPanel.hidden = true;
    el.emptyState.hidden = false;
    resetPageMeta();
    runSearch(el.search.value.trim());
    debounceUrlState();
  });

  el.suggestions.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.dataset.journal) {
      selectedJournal = Number(btn.dataset.journal);
      selectedSpec = null;
      el.search.value = journalByNum.get(selectedJournal).name;
    }
    if (btn.dataset.spec) {
      selectedSpec = Number(btn.dataset.spec);
      selectedJournal = null;
      const s = specById.get(selectedSpec);
      el.search.value = specialtyQuery(s);
    }
    el.suggestions.hidden = true;
    showResults();
    writeUrlState();
  });

  /* Filter change events */
  el.filterDate.addEventListener("change", () => {
    el.date.disabled = !el.filterDate.checked;
    if (selectedJournal != null || selectedSpec != null) showResults();
    renderPopularSpecialties();
    refreshSearchIfTyping();
    writeUrlState();
  });

  el.date.addEventListener("change", () => {
    if (selectedJournal != null || selectedSpec != null) showResults();
    renderPopularSpecialties();
    refreshSearchIfTyping();
    writeUrlState();
  });

  el.filterScopus.addEventListener("change", () => {
    if (selectedJournal != null || selectedSpec != null) showResults();
    renderPopularSpecialties();
    refreshSearchIfTyping();
    writeUrlState();
  });

  el.filterRcsiLevel.addEventListener("change", () => {
    if (selectedJournal != null || selectedSpec != null) showResults();
    renderPopularSpecialties();
    refreshSearchIfTyping();
    writeUrlState();
  });

  el.filterVakCat.addEventListener("change", () => {
    if (selectedJournal != null || selectedSpec != null) showResults();
    renderPopularSpecialties();
    refreshSearchIfTyping();
    writeUrlState();
  });

  document.addEventListener("click", (e) => {
    if (!el.suggestions.contains(e.target) && e.target !== el.search) {
      el.suggestions.hidden = true;
    }
  });

  window.addEventListener("popstate", applyUrlState);

  load().catch((err) => {
    el.loading.innerHTML = `<p>Не удалось загрузить данные: ${escapeHtml(err.message)}</p>`;
  });
})();
