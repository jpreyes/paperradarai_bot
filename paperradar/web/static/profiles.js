(() => {
  const state = {
    users: [],
    chatIds: [],
    currentChatId: null,
    config: null,
    selectedProfile: null,
  };

  const elements = {
    chatSelect: document.getElementById("chatSelect"),
    profileList: document.getElementById("profileList"),
    newProfileName: document.getElementById("newProfileName"),
    newProfileText: document.getElementById("newProfileText"),
    createProfileBtn: document.getElementById("createProfileBtn"),
    deleteProfileBtn: document.getElementById("deleteProfileBtn"),
    uploadPdfBtn: document.getElementById("uploadPdfBtn"),
    profilePdf: document.getElementById("profilePdf"),
    profileStatus: document.getElementById("profileStatus"),
    configSummary: document.getElementById("configSummary"),
    configTopics: document.getElementById("configTopics"),
    configTopicWeights: document.getElementById("configTopicWeights"),
    configPreferences: document.getElementById("configPreferences"),
    configStatus: document.getElementById("configStatus"),
  };

  const initial = window.__PAPERRADAR_INITIAL__ || {};

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function setStatus(message, tone = "info") {
    if (!elements.profileStatus) return;
    elements.profileStatus.textContent = message || "";
    elements.profileStatus.className = `upload-status ${tone}`;
  }

  function formatDate(value) {
    if (!value) return "--";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString();
  }

  async function fetchJSON(url, options) {
    const resp = await fetch(url, options);
    if (!resp.ok) {
      let message = `Error ${resp.status}`;
      try {
        const payload = await resp.json();
        if (payload?.detail) message = payload.detail;
      } catch (_err) {
        /* noop */
      }
      throw new Error(message);
    }
    return resp.json();
  }

  async function postJSON(url, body) {
    return fetchJSON(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  async function refreshUsers() {
    try {
      state.users = await fetchJSON("/users");
    } catch (err) {
      console.error(err);
      state.users = [];
    }
  }

  function profileSnippet(summary) {
    if (!summary) return "";
    const clean = summary.trim().replace(/\s+/g, " ");
    if (!clean) return "";
    return clean.length > 48 ? `${clean.slice(0, 48)}...` : clean;
  }

  function renderChatSelect() {
    const select = elements.chatSelect;
    if (!select) return;
    select.innerHTML = "";
    const users = state.users.length
      ? state.users
      : (state.chatIds || []).map((cid) => ({ chat_id: cid }));
    if (!users.length) {
      const opt = document.createElement("option");
      opt.textContent = "Sin chats disponibles";
      opt.disabled = true;
      select.appendChild(opt);
      select.disabled = true;
      return;
    }
    select.disabled = false;
    users.forEach((user) => {
      const opt = document.createElement("option");
      const summary = profileSnippet(user.profile_summary || "");
      const profileName = user.active_profile || "default";
      opt.value = String(user.chat_id);
      opt.textContent = summary
        ? `${user.chat_id} - ${profileName} - ${summary}`
        : `${user.chat_id} - ${profileName}`;
      select.appendChild(opt);
    });
    if (state.currentChatId) {
      select.value = String(state.currentChatId);
    } else if (users.length) {
      state.currentChatId = users[0].chat_id;
      select.value = String(state.currentChatId);
    }
  }

  function ensureSelectedProfile() {
    if (!state.config) return;
    const profiles = state.config.profiles || [];
    if (!profiles.length) {
      state.selectedProfile = null;
      return;
    }
    if (state.selectedProfile && profiles.includes(state.selectedProfile)) {
      return;
    }
    state.selectedProfile = state.config.active_profile || profiles[0];
  }

  function renderTopics(topics) {
    if (!elements.configTopics) return;
    elements.configTopics.innerHTML = "";
    if (!topics || !topics.length) {
      elements.configTopics.innerHTML = "<li>Sin temas detectados.</li>";
      return;
    }
    topics.forEach((topic) => {
      const li = document.createElement("li");
      li.textContent = topic;
      elements.configTopics.appendChild(li);
    });
  }

  function renderTopicWeights(weights) {
    if (!elements.configTopicWeights) return;
    const entries = Object.entries(weights || {})
      .sort((a, b) => (b[1] || 0) - (a[1] || 0))
      .slice(0, 12);
    if (!entries.length) {
      elements.configTopicWeights.innerHTML = "<div>Sin pesos asociados.</div>";
      return;
    }
    elements.configTopicWeights.innerHTML = entries
      .map(([topic, weight]) => `<div><strong>${escapeHtml(topic)}:</strong> ${Number(weight).toFixed(3)}</div>`)
      .join("");
  }

  function renderPreferences(cfg) {
    if (!elements.configPreferences) return;
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
      .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`)
      .join("");
  }

  function renderStatus(cfg) {
    if (!elements.configStatus) return;
    const status = [
      ["Perfil activo", cfg.active_profile || "--"],
      ["Perfiles disponibles", (cfg.profiles || []).join(", ") || "--"],
      ["Ultimo tick", formatDate(cfg.last_lucky_ts)],
      ["Likes totales", cfg.likes_total ?? 0],
      ["Dislikes totales", cfg.dislikes_total ?? 0],
    ];
    elements.configStatus.innerHTML = status
      .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd>`)
      .join("");
  }

  function renderProfileList() {
    const list = elements.profileList;
    if (!list || !state.config) return;
    const profiles = state.config.profiles || [];
    const active = state.config.active_profile || "";
    list.innerHTML = "";
    if (!profiles.length) {
      list.innerHTML = '<li class="profile-item empty">Sin perfiles configurados.</li>';
      if (elements.deleteProfileBtn) elements.deleteProfileBtn.disabled = true;
      return;
    }
    ensureSelectedProfile();
    profiles.forEach((name) => {
      const li = document.createElement("li");
      li.className = "profile-item";
      if (name === active) li.classList.add("is-active");
      if (name === state.selectedProfile) li.classList.add("is-selected");
      li.dataset.profile = name;
      const badge = name === active ? '<span class="profile-badge">Activo</span>' : "";
      const actions = name === active
        ? '<button type="button" class="toolbar-btn small" data-action="select">Seleccionar</button>'
        : '<button type="button" class="toolbar-btn small" data-action="select">Seleccionar</button><button type="button" class="toolbar-btn small" data-action="activate">Activar</button>';
      li.innerHTML = `
        <div class="profile-meta">
          <span class="profile-name">${escapeHtml(name)}</span>
          ${badge}
        </div>
        <div class="profile-buttons">
          ${actions}
        </div>
      `;
      list.appendChild(li);
    });
    if (elements.deleteProfileBtn) {
      elements.deleteProfileBtn.disabled = profiles.length <= 1;
    }
  }

  function renderConfig() {
    if (!state.config) {
      if (elements.configSummary) {
        elements.configSummary.textContent = "Selecciona un chat para ver su configuracion.";
      }
      renderTopics([]);
      renderTopicWeights({});
      renderProfileList();
      if (elements.configPreferences) elements.configPreferences.innerHTML = "";
      if (elements.configStatus) elements.configStatus.innerHTML = "";
      return;
    }
    const cfg = state.config;
    ensureSelectedProfile();
    if (elements.configSummary) {
      elements.configSummary.textContent = cfg.profile_summary || "Sin resumen disponible.";
    }
    renderTopics(cfg.profile_topics || []);
    renderTopicWeights(cfg.profile_topic_weights || {});
    renderPreferences(cfg);
    renderStatus(cfg);
    renderProfileList();
  }

  function setSelectedProfile(name) {
    state.selectedProfile = name;
    renderProfileList();
  }

  async function activateProfile(name) {
    if (!state.currentChatId || !name) return;
    setStatus("Cambiando perfil...", "info");
    try {
      const cfg = await postJSON(`/users/${state.currentChatId}/profiles/use`, { profile: name });
      state.config = cfg;
      state.selectedProfile = cfg.active_profile;
      renderConfig();
      await refreshUsers();
      renderChatSelect();
      setStatus("Perfil activo actualizado.", "success");
    } catch (err) {
      console.error(err);
      setStatus(err.message || "No se pudo cambiar el perfil.", "error");
    }
  }

  async function loadConfig(chatId) {
    if (!chatId) {
      state.config = null;
      state.selectedProfile = null;
      renderConfig();
      return;
    }
    try {
      state.config = await fetchJSON(`/users/${chatId}/config`);
      state.selectedProfile = state.config.active_profile || null;
      renderConfig();
    } catch (err) {
      console.error(err);
      state.config = null;
      state.selectedProfile = null;
      renderConfig();
      setStatus(err.message || "No se pudo cargar la configuracion.", "error");
    }
  }

  async function handleChatChange(chatId) {
    state.currentChatId = Number(chatId);
    setStatus("");
    await loadConfig(state.currentChatId);
  }

  async function handleCreateProfile() {
    if (!state.currentChatId) {
      setStatus("Selecciona un chat primero.", "error");
      return;
    }
    const nameInput = elements.newProfileName;
    const textInput = elements.newProfileText;
    const name = (nameInput?.value || "").trim();
    const text = (textInput?.value || "").trim();
    if (!name) {
      setStatus("Ingresa un nombre para el perfil.", "error");
      return;
    }
    if (elements.createProfileBtn) elements.createProfileBtn.disabled = true;
    setStatus("Creando perfil...", "info");
    try {
      const cfg = await postJSON(`/users/${state.currentChatId}/profiles`, {
        name,
        text,
        set_active: true,
      });
      state.config = cfg;
      state.selectedProfile = cfg.active_profile;
      renderConfig();
      await refreshUsers();
      renderChatSelect();
      if (nameInput) nameInput.value = "";
      if (textInput) textInput.value = "";
      setStatus("Perfil creado correctamente.", "success");
    } catch (err) {
      console.error(err);
      setStatus(err.message || "No se pudo crear el perfil.", "error");
    } finally {
      if (elements.createProfileBtn) elements.createProfileBtn.disabled = false;
    }
  }

  async function handleDeleteProfile() {
    if (!state.currentChatId) {
      setStatus("Selecciona un chat primero.", "error");
      return;
    }
    const target = state.selectedProfile;
    if (!target) {
      setStatus("Selecciona un perfil para eliminar.", "error");
      return;
    }
    if (!window.confirm(`Eliminar el perfil "${target}"?`)) {
      return;
    }
    if (elements.deleteProfileBtn) elements.deleteProfileBtn.disabled = true;
    setStatus("Eliminando perfil...", "info");
    try {
      await fetchJSON(`/users/${state.currentChatId}/profiles/${encodeURIComponent(target)}`, {
        method: "DELETE",
      });
      await loadConfig(state.currentChatId);
      await refreshUsers();
      renderChatSelect();
      setStatus("Perfil eliminado.", "success");
    } catch (err) {
      console.error(err);
      setStatus(err.message || "No se pudo eliminar el perfil.", "error");
    } finally {
      if (elements.deleteProfileBtn) elements.deleteProfileBtn.disabled = false;
    }
  }

  async function handleUploadPdf() {
    if (!state.currentChatId) {
      setStatus("Selecciona un chat primero.", "error");
      return;
    }
    const fileInput = elements.profilePdf;
    const file = fileInput?.files?.[0];
    if (!file) {
      setStatus("Selecciona un archivo PDF.", "error");
      return;
    }
    if (file.type !== "application/pdf") {
      setStatus("El archivo debe ser un PDF.", "error");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    if (state.selectedProfile) {
      form.append("profile", state.selectedProfile);
    }
    if (elements.uploadPdfBtn) elements.uploadPdfBtn.disabled = true;
    setStatus("Subiendo PDF...", "info");
    try {
      const resp = await fetch(`/users/${state.currentChatId}/profiles/upload`, {
        method: "POST",
        body: form,
      });
      if (!resp.ok) {
        let msg = `Error ${resp.status}`;
        try {
          const payload = await resp.json();
          if (payload?.detail) msg = payload.detail;
        } catch (_err) {
          /* noop */
        }
        throw new Error(msg);
      }
      const cfg = await resp.json();
      state.config = cfg;
      state.selectedProfile = cfg.active_profile;
      renderConfig();
      await refreshUsers();
      renderChatSelect();
      setStatus("Perfil actualizado.", "success");
      if (fileInput) fileInput.value = "";
    } catch (err) {
      console.error(err);
      setStatus(err.message || "No se pudo procesar el PDF.", "error");
    } finally {
      if (elements.uploadPdfBtn) elements.uploadPdfBtn.disabled = false;
    }
  }

  function attachEvents() {
    elements.chatSelect?.addEventListener("change", async (event) => {
      const select = event.target;
      if (!(select instanceof HTMLSelectElement)) return;
      await handleChatChange(select.value);
    });

    elements.profileList?.addEventListener("click", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const li = target.closest("li[data-profile]");
      if (!li) return;
      const profileName = li.dataset.profile || "";
      const action = target.dataset.action;
      if (action === "activate") {
        await activateProfile(profileName);
        return;
      }
      if (action === "select" || !action) {
        setSelectedProfile(profileName);
      }
    });

    elements.createProfileBtn?.addEventListener("click", (event) => {
      event.preventDefault();
      handleCreateProfile();
    });

    elements.deleteProfileBtn?.addEventListener("click", (event) => {
      event.preventDefault();
      handleDeleteProfile();
    });

    elements.uploadPdfBtn?.addEventListener("click", (event) => {
      event.preventDefault();
      handleUploadPdf();
    });
  }

  async function init() {
    state.chatIds = Array.isArray(initial.chatIds) ? initial.chatIds : [];
    try {
      await refreshUsers();
    } catch (err) {
      console.error(err);
    }
    renderChatSelect();
    const defaultChat = initial.defaultChatId ?? state.chatIds[0];
    if (defaultChat) {
      await handleChatChange(defaultChat);
      if (elements.chatSelect) {
        elements.chatSelect.value = String(defaultChat);
      }
    } else {
      renderConfig();
    }
    attachEvents();
  }

  init();
})();
