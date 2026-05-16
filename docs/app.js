/* global MiniSearch */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const journalByNum = new Map();
  const specById = new Map();
  const linksByJournal = new Map();
  const linksBySpec = new Map();

  let data = null;
  let mode = "journal";
  let journalSearch = null;
  let specSearch = null;
  let selectedJournal = null;
  let selectedSpec = null;

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
    resultsPanel: $("#results-panel"),
    resultsTitle: $("#results-title"),
    resultsMeta: $("#results-meta"),
    resultsBody: $("#results-body"),
    emptyState: $("#empty-state"),
    tabJournal: $("#tab-journal"),
    tabSpec: $("#tab-spec"),
  };

  function dataUrl() {
    return new URL("data/vak.json", window.location.href).href;
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

    specSearch = new MiniSearch({
      fields: ["code", "title", "branch", "search"],
      storeFields: ["id", "code", "title", "branch", "type"],
      searchOptions: { prefix: true, fuzzy: 0.12, boost: { code: 3, title: 1.5 } },
    });
    specSearch.addAll(data.specialties);
  }

  function setMode(next) {
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
    el.search.focus();
  }

  function runSearch(q) {
    if (!q || q.length < 2) {
      el.suggestions.hidden = true;
      return;
    }
    const ms = mode === "journal" ? journalSearch : specSearch;
    const hits = ms.search(q, { limit: 12 });
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
        const branch = s.branch ? ` · ${escapeHtml(s.branch)}` : "";
        return `<li><button type="button" data-spec="${s.id}">
            <strong class="code">${escapeHtml(s.code)}</strong> ${escapeHtml(s.title)}
            <span class="sub">${s.type === "diss" ? "код диссертации" : "номенклатура"}${branch}</span>
          </button></li>`;
      })
      .join("");
    el.suggestions.hidden = false;
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

    if (!links.length) {
      el.resultsBody.innerHTML =
        "<p class=\"hint\">Нет специальностей для выбранных условий (проверьте фильтр по дате).</p>";
      return;
    }

    const groups = new Map();
    for (const link of links) {
      const key = link.g;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(link);
    }

    let html = "";
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
          ? `<p class="branch">${escapeHtml(s.branch)}</p>`
          : "";
        const dates =
          sortedGroups.length === 1
            ? `<p class="dates">${formatDates(link)}</p>`
            : "";
        html += `<li class="result-item">
          <span class="code">${escapeHtml(s.code)}</span>
          <p class="title">${escapeHtml(s.title)}</p>
          ${branch}
          ${dates}
        </li>`;
      }
      html += "</ul>";
    }
    el.resultsBody.innerHTML = html;
  }

  function renderSpecResults(specId) {
    const s = specById.get(specId);
    if (!s) return;
    const iso = filterIso();
    let links = linksBySpec.get(specId) || [];
    links = links.filter((l) => activeOn(l, iso));

    el.resultsTitle.innerHTML = `<span class="code">${escapeHtml(s.code)}</span> ${escapeHtml(s.title)}`;
    el.resultsMeta.innerHTML = [
      s.branch ? escapeHtml(s.branch) : null,
      iso ? `актуально на ${formatIsoRu(iso)}` : null,
      `${links.length} журналов`,
    ]
      .filter(Boolean)
      .join(" · ");

    if (!links.length) {
      el.resultsBody.innerHTML =
        "<p class=\"hint\">Нет журналов для выбранных условий.</p>";
      return;
    }

    links.sort((a, b) => a.j - b.j);
    let html = '<ul class="result-list">';
    for (const link of links) {
      const j = journalByNum.get(link.j);
      html += `<li class="result-item">
        <strong>№ ${j.n}</strong> ${escapeHtml(j.name)}
        ${j.issn ? `<p class="branch">ISSN ${escapeHtml(j.issn)}</p>` : ""}
        <p class="dates">${formatDates(link)}</p>
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

    el.loading.hidden = true;
    el.app.hidden = false;
  }

  el.tabJournal.addEventListener("click", () => setMode("journal"));
  el.tabSpec.addEventListener("click", () => setMode("spec"));

  el.search.addEventListener("input", () => {
    selectedJournal = null;
    selectedSpec = null;
    el.resultsPanel.hidden = true;
    el.emptyState.hidden = false;
    runSearch(el.search.value.trim());
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
      el.search.value = `${s.code} ${s.title}`;
    }
    el.suggestions.hidden = true;
    showResults();
  });

  el.filterDate.addEventListener("change", () => {
    el.date.disabled = !el.filterDate.checked;
    if (selectedJournal != null || selectedSpec != null) showResults();
  });

  el.date.addEventListener("change", () => {
    if (selectedJournal != null || selectedSpec != null) showResults();
  });

  document.addEventListener("click", (e) => {
    if (!el.suggestions.contains(e.target) && e.target !== el.search) {
      el.suggestions.hidden = true;
    }
  });

  load().catch((err) => {
    el.loading.innerHTML = `<p>Не удалось загрузить данные: ${escapeHtml(err.message)}</p>`;
  });
})();
