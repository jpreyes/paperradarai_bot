(() => {
  const state = {
    users: [],
    chatIds: [],
    currentChatId: null,
    papers: [],
    totalRanked: 0,
    config: null,
    sortKey: "score",
    sortDir: "desc",
    limit: 25,
    page: 0,
    offset: 0,
    hasMore: false,
  };

  const elements = {
    chatSelect: document.getElementById("chatSelect"),
    navButtons: document.querySelectorAll(".nav-btn"),
    views: {
      papers: document.getElementById("view-papers"),
      config: document.getElementById("view-config"),
    },
    sortSelect: document.getElementById("sortSelect"),
    sortDir: document.getElementById("sortDir"),
    limitInput: document.getElementById("limitInput"),
    historyBtn: document.getElementById("historyBtn"),
    refreshBtn: document.getElementById("refreshBtn"),
    activeProfile: document.getElementById("activeProfile"),
    prevPage: document.getElementById("prevPage"),
    nextPage: document.getElementById("nextPage"),
    pageInfo: document.getElementById("pageInfo"),
    papersTable: document.getElementById("papersTable"),
    papersEmpty: document.getElementById("papersEmpty"),
    papersCount: document.getElementById("papersCount"),
    configSummary: document.getElementById("configSummary"),
    configTopics: document.getElementById("configTopics"),
    configTopicWeights: document.getElementById("configTopicWeights"),
    configPreferences: document.getElementById("configPreferences"),
    configStatus: document.getElementById("configStatus"),
  };

  const initial = window.__PAPERRADAR_INITIAL__ || {};

  async function fetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) {
      let message = `Error ${resp.status}`;
      try {
        const payload = await resp.json();
        if (payload && payload.detail) {
          message = payload.detail;
        }
      } catch (_err) {
        /* noop */
      }
      throw new Error(message);
    }
    return resp.json();
  }

  async function postJSON(url, body) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      let message = `Error ${resp.status}`;
      try {
        const payload = await resp.json();
        if (payload && payload.detail) {
          message = payload.detail;
        }
      } catch (_err) {
        /* noop */
      }
      throw new Error(message);
    }
    return resp.json();
  }

  function formatDate(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  }

  function authorLabel(authors) {
    if (!Array.isArray(authors) || !authors.length) return "--";
    if (authors.length <= 3) return authors.join(", ");
    return `${authors.slice(0, 3).join(", ")} y ${authors.length - 3} mas`;
  }

  function clampLimit(value) {
    const num = Number(value);
    if (Number.isNaN(num)) return state.limit;
    return Math.min(200, Math.max(5, Math.round(num)));
  }

  function encodeKey(value) {
    return encodeURIComponent(value ?? "");
  }

  function decodeKey(value) {
    try {
      return decodeURIComponent(value ?? "");
    } catch (_err) {
      return value ?? "";
    }
  }

  function entryKey(entry) {
    if (!entry) return "";
    if (entry.paper_key) return entry.paper_key;
    const item = entry.item || {};
    return item.id || item.url || "";
  }

  function updateActiveProfile(name) {
    if (!elements.activeProfile) return;
    const label = (name || "").trim();
    elements.activeProfile.textContent = label || "--";
  }

  function setView(target) {
    Object.entries(elements.views).forEach(([key, el]) => {
      const active = key === target;
      el.classList.toggle("active", active);
      document
        .querySelector(`.nav-btn[data-view="${key}"]`)
        .classList.toggle("active", active);
    });
  }

  function updatePaginationControls() {
    if (!elements.pageInfo || !elements.prevPage || !elements.nextPage) {
      return;
    }
    const total = state.totalRanked || 0;
    const pageCount = total ? Math.ceil(total / state.limit) : 1;
    const currentPage = Math.min(state.page, pageCount - 1);
    state.page = currentPage;
    elements.prevPage.disabled = currentPage === 0 || total === 0;
    elements.nextPage.disabled = currentPage >= pageCount - 1 || total === 0;
    elements.pageInfo.textContent = total
      ? `Pagina ${currentPage + 1} de ${pageCount}`
      : "Sin datos";
  }

  function renderUsers() {
    if (!state.config) {
      updateActiveProfile(null);
    }
    elements.chatSelect.innerHTML = "";
    if (!state.users.length) {
      const opt = document.createElement("option");
      opt.textContent = "No hay chats registrados";
      opt.disabled = true;
      elements.chatSelect.appendChild(opt);
      elements.chatSelect.disabled = true;
      elements.refreshBtn.disabled = true;
      return;
    }
    elements.chatSelect.disabled = false;
    elements.refreshBtn.disabled = false;
    state.users.forEach((user) => {
      const opt = document.createElement("option");
      const summary = user.profile_summary || "";
      const snippet = summary ? summary.slice(0, 60) : "Sin resumen";
      opt.value = user.chat_id;
      opt.textContent = `${user.chat_id}  -  ${user.active_profile}  -  ${snippet}`;
      elements.chatSelect.appendChild(opt);
    });
    if (state.currentChatId) {
      elements.chatSelect.value = state.currentChatId;
    } else {
      state.currentChatId = state.users[0].chat_id;
      elements.chatSelect.value = state.currentChatId;
    }
  }

  function sortPapers(data) {
    const dir = state.sortDir === "asc" ? 1 : -1;
    const key = state.sortKey;
    const copy = [...data];
    copy.sort((a, b) => {
      const av = extractor(a, key);
      const bv = extractor(b, key);
      if (av === bv) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return av < bv ? -dir : dir;
      }
      return av < bv ? -dir : dir;
    });
    return copy;
  }

  function extractor(entry, key) {
    const item = entry.item || {};
    switch (key) {
      case "score":
        return entry.score ?? 0;
      case "published": {
        const raw = item.published || item.year || "";
        const ts = Date.parse(raw);
        return Number.isNaN(ts) ? null : ts;
      }
      case "venue":
        return (item.venue || "").toLowerCase();
      case "authors":
        return (item.authors || []).join(", ").toLowerCase();
      case "fetched_at": {
        const ts = Date.parse(entry.fetched_at);
        return Number.isNaN(ts) ? null : ts;
      }
      default:
        return null;
    }
  }

  function renderPapers() {
    if (!state.papers.length) {
      elements.papersTable.innerHTML = "";
      elements.papersEmpty.classList.remove("hidden");
      elements.papersCount.textContent = "No hay coincidencias.";
      updatePaginationControls();
      return;
    }
    elements.papersEmpty.classList.add("hidden");
    const sorted = sortPapers(state.papers);
    const rows = sorted
      .map((entry) => renderPaperRow(entry))
      .join("");
    elements.papersTable.innerHTML = `
      <div class="table-inner">
        <table>
          <thead>
            <tr>
              <th>Score</th>
              <th>Titulo</th>
              <th>Fuente</th>
              <th>Publicado</th>
              <th>Revista</th>
              <th>Autores</th>
              <th>Recogido</th>
              <th>Feedback</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
    const total = state.totalRanked || 0;
    const start = Math.min(total, state.offset + 1);
    const end = Math.min(total, state.offset + sorted.length);
    elements.papersCount.textContent = total
      ? `Mostrando ${start}-${end} de ${total} items (perfil ${state.currentChatId}).`
      : `Mostrando ${sorted.length} items (perfil ${state.currentChatId}).`;
    updatePaginationControls();
  }

  function renderPaperRow(entry) {
    const item = entry.item || {};
    const authors = authorLabel(item.authors);
    const published = item.published || item.year || "--";
    const venue = item.venue || "--";
    const ideas = (entry.bullets?.ideas || []).map((idea) => `<li>${idea}</li>`).join("");
    const similarities = (entry.bullets?.similarities || [])
      .map((sim) => `<li>${sim}</li>`)
      .join("");
    const details = [];
    if (ideas) {
      details.push(`<strong>Ideas:</strong><ul class="idea-list">${ideas}</ul>`);
    }
    if (similarities) {
      details.push(`<strong>Coincidencias:</strong><ul class="idea-list">${similarities}</ul>`);
    }
    if (entry.bullets?.tag) {
      details.push(`<span class="tag-pill">${entry.bullets.tag}</span>`);
    }
    const tagRaw = entry.bullets?.tag || "";
    const tag = tagRaw ? tagRaw.toUpperCase() : "";
    const tagBadge = tag
      ? `<span class="tag-badge ${tagRaw.toLowerCase()}">${tag}</span>`
      : "";
    const paperKey = entry.paper_key || item.id || item.url || "";
    const encodedKey = encodeKey(paperKey);
    const liked = Boolean(entry.liked);
    const disliked = Boolean(entry.disliked);
    const feedbackButtons = `
      <div class="feedback-btns">
        <button class="action-btn like-btn${liked ? " is-active" : ""}" data-action="like" data-paper="${encodedKey}" title="Like">+</button>
        <button class="action-btn dislike-btn${disliked ? " is-active" : ""}" data-action="dislike" data-paper="${encodedKey}" title="Dislike">-</button>
      </div>
    `;
    const detailBlock = details.length
      ? `<details class="details"><summary>Ver detalles</summary>${details.join("")}</details>`
      : "";
    return `
      <tr>
        <td>
          <div class="score-cell">
            <span class="score-pill">${entry.score?.toFixed?.(3) ?? entry.score}</span>
            ${tagBadge}
          </div>
        </td>
        <td class="title-cell">
          <a href="${item.url || "#"}" target="_blank" rel="noopener noreferrer">${item.title || "Sin titulo"}</a>
          ${detailBlock}
        </td>
        <td>${item.source || "--"}</td>
        <td>${published}</td>
        <td>${venue}</td>
        <td>${authors}</td>
        <td>${formatDate(entry.fetched_at)}</td>
        <td>${feedbackButtons}</td>
      </tr>
    `;
  }

  function renderConfig() {
    if (!state.config) return;
    const cfg = state.config;
    updateActiveProfile(cfg.active_profile);
    elements.configSummary.textContent = cfg.profile_summary || "Sin resumen disponible.";

    elements.configTopics.innerHTML = "";
    (cfg.profile_topics || []).forEach((topic) => {
      const li = document.createElement("li");
      li.textContent = topic;
      elements.configTopics.appendChild(li);
    });
    if (!(cfg.profile_topics || []).length) {
      elements.configTopics.innerHTML = '<li>Sin temas detectados.</li>';
    }

    const weightsEntries = Object.entries(cfg.profile_topic_weights || {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12);
    if (weightsEntries.length) {
      elements.configTopicWeights.innerHTML = weightsEntries
        .map(([topic, weight]) => `<div><strong>${topic}:</strong> ${weight.toFixed(3)}</div>`)
        .join("");
    } else {
      elements.configTopicWeights.innerHTML = "<div>Sin pesos asociados.</div>";
    }

    const preferences = [
      ["Similitud minima", cfg.sim_threshold ?? "--"],
      ["Top N", cfg.topn ?? "--"],
      ["Edad maxima (h)", cfg.max_age_hours ?? "--"],
      ["Intervalo tick (min)", cfg.poll_min ?? "--"],
      ["Hora diaria (bot)", cfg.poll_daily_time || "--"],
      ["LLM habilitado", cfg.llm_enabled ? "Si" : "No"],
      ["Umbral LLM", cfg.llm_threshold ?? "--"],
      ["LLM max/tick", cfg.llm_max_per_tick ?? "--"],
      ["LLM max/on-demand", cfg.llm_ondemand_max_per_hour ?? "--"],
    ];
    elements.configPreferences.innerHTML = preferences
      .map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`)
      .join("");

    const status = [
      ["Perfil activo", cfg.active_profile || "--"],
      ["Perfiles disponibles", (cfg.profiles || []).join(", ") || "--"],
      ["Ultimo tick", formatDate(cfg.last_lucky_ts)],
      ["Likes totales", cfg.likes_total ?? 0],
      ["Dislikes totales", cfg.dislikes_total ?? 0],
    ];
    elements.configStatus.innerHTML = status
      .map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`)
      .join("");
  }

  async function loadConfig(chatId) {
    state.config = await fetchJSON(`/users/${chatId}/config`);
    renderConfig();
  }

  async function loadPapers(chatId, { mode = "history" } = {}) {
    elements.papersTable.innerHTML = '<div class="loading">Cargando...</div>';
    elements.papersEmpty.classList.add("hidden");
    const offset = state.page * state.limit;
    const payload = await fetchJSON(`/users/${chatId}/papers?limit=${state.limit}&offset=${offset}&mode=${mode}`);
    const freshItems = payload.items || [];
    if (mode === "live") {
      const merged = [];
      const known = new Set();
      freshItems.forEach((entry) => {
        const key = entryKey(entry);
        if (key) known.add(key);
        merged.push(entry);
      });
      (state.papers || []).forEach((entry) => {
        const key = entryKey(entry);
        if (key && known.has(key)) {
          return;
        }
        if (key) known.add(key);
        merged.push(entry);
      });
      state.papers = merged;
      state.totalRanked = state.papers.length;
      state.offset = 0;
      state.hasMore = false;
    } else {
      state.papers = freshItems;
      state.totalRanked = payload.total_ranked ?? state.papers.length;
      state.offset = payload.offset ?? offset;
      state.hasMore = Boolean(payload.has_more);
    }
    const total = state.totalRanked;
    if (total > 0 && state.offset >= total) {
      state.page = Math.max(0, Math.ceil(total / state.limit) - 1);
      return loadPapers(chatId, { mode });
    }
    renderPapers();
  }

  async function refreshAll({ mode = "history" } = {}) {
    if (!state.currentChatId) return;
    try {
      await Promise.all([
        loadConfig(state.currentChatId),
        loadPapers(state.currentChatId, { mode }),
      ]);
    } catch (err) {
      elements.papersTable.innerHTML = `<div class="error">Error: ${err.message}</div>`;
    }
  }

  async function init() {
    try {
      state.users = await fetchJSON("/users");
      state.chatIds = state.users.map((u) => u.chat_id);
    } catch (err) {
      console.error(err);
      state.users = [];
    }
    state.currentChatId = initial.defaultChatId ?? state.chatIds?.[0] ?? null;
    renderUsers();
    if (state.currentChatId) {
      await refreshAll();
    }
  }

  elements.chatSelect?.addEventListener("change", async (event) => {
    const nextId = Number(event.target.value);
    if (!Number.isFinite(nextId)) return;
    state.currentChatId = nextId;
    state.page = 0;
    state.config = null;
    updateActiveProfile(null);
    await refreshAll({ mode: "history" });
  });

  elements.navButtons.forEach((btn) =>
    btn.addEventListener("click", () => {
      setView(btn.dataset.view);
      if (btn.dataset.view === "config" && state.config == null && state.currentChatId) {
        loadConfig(state.currentChatId);
      }
    }),
  );

  elements.sortSelect?.addEventListener("change", (event) => {
    state.sortKey = event.target.value;
    renderPapers();
  });

  elements.sortDir?.addEventListener("change", (event) => {
    state.sortDir = event.target.value;
    renderPapers();
  });

  elements.limitInput?.addEventListener("change", async (event) => {
    const next = clampLimit(event.target.value);
    state.limit = next;
    state.page = 0;
    elements.limitInput.value = next;
    if (state.currentChatId) {
      await loadPapers(state.currentChatId, { mode: "history" });
    }
  });

  elements.refreshBtn?.addEventListener("click", async () => {
    if (!state.currentChatId) return;
    state.page = 0;
    await refreshAll({ mode: "live" });
  });

  elements.historyBtn?.addEventListener("click", async () => {
    if (!state.currentChatId) return;
    state.page = 0;
    await refreshAll({ mode: "history" });
  });

  elements.prevPage?.addEventListener("click", async () => {
    if (state.page === 0) return;
    state.page -= 1;
    if (state.currentChatId) {
      await loadPapers(state.currentChatId, { mode: "history" });
    }
  });

  elements.nextPage?.addEventListener("click", async () => {
    const nextOffset = (state.page + 1) * state.limit;
    if (nextOffset >= state.totalRanked) return;
    state.page += 1;
    if (state.currentChatId) {
      await loadPapers(state.currentChatId, { mode: "history" });
    }
  });

  setView("papers");
  state.limit = clampLimit(elements.limitInput?.value ?? state.limit);
  init();
})();
