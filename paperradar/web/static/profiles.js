import {
  React,
  html,
  Fragment,
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
  useToasts,
  ToastHost,
  Spinner,
  Skeleton,
  useDocumentTitle,
} from "./ui.js";
import { createRoot } from "https://esm.sh/react-dom@18/client";

const initialData = globalThis.__PAPERRADAR_INITIAL__ ?? {};

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `Error ${response.status}`;
    try {
      const payload = await response.json();
      if (payload?.detail) {
        message = payload.detail;
      }
    } catch (_err) {
      /* no-op */
    }
    throw new Error(message);
  }
  return response.json();
}

async function postJSON(url, body) {
  return fetchJSON(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function patchJSON(url, body) {
  return fetchJSON(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function formatDate(value) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function normalizeTopicEntries(topicList, weightsMap) {
  if (!Array.isArray(topicList) || topicList.length === 0) return [];
  const weights = weightsMap || {};
  return topicList.map((topic) => {
    const weight = weights[topic];
    return {
      name: topic,
      weight:
        typeof weight === "number" && Number.isFinite(weight)
          ? String(weight)
          : weight != null && weight !== ""
          ? String(weight)
          : "",
    };
  });
}

function clampWeight(value) {
  if (value === "" || value === null || value === undefined) return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  const clamped = Math.min(1, Math.max(0, numeric));
  return Math.round(clamped * 1000) / 1000;
}

function profileSnippet(summary) {
  if (!summary) return "Sin resumen";
  const clean = summary.trim().replace(/\s+/g, " ");
  if (!clean) return "Sin resumen";
  return clean.length > 60 ? `${clean.slice(0, 60)}...` : clean;
}

function Sidebar({
  users,
  loading,
  error,
  currentChatId,
  activeProfile,
  profiles,
  profilesLoading,
  onChatChange,
  onProfileChange,
}) {
  const hasUsers = users.length > 0;
  const hasProfiles = Array.isArray(profiles) && profiles.length > 0;
  const userOptions = users.map((user, index) => {
    const indexLabel = `Usuario ${index + 1}`;
    const summary = profileSnippet(user.profile_summary || "");
    const badge = user.active_profile ? ` - ${user.active_profile}` : "";
    return {
      value: user.chat_id,
      label: `${indexLabel}${badge} - ${summary}`.replace(/\s+/g, " ").trim(),
    };
  });
  const currentOption = userOptions.find((option) => option.value === currentChatId);

  return html`
    <aside className="sidebar">
      <header className="brand">
        <span className="logo">PR</span>
        <div>
          <h1>PaperRadar</h1>
          <p className="subtitle">Perfiles</p>
        </div>
      </header>
      <section className="menu">
        <label className="menu-label" htmlFor="chatSelect">Usuario</label>
        <select
          id="chatSelect"
          className="menu-select"
          value=${currentChatId ?? ""}
          onChange=${onChatChange}
          disabled=${!hasUsers || loading}
        >
          ${loading
            ? html`<option value="">Cargando chats...</option>`
            : hasUsers
            ? userOptions.map(
                (option) =>
                  html`<option key=${option.value} value=${option.value}>${option.label}</option>`,
              )
            : html`<option value="">Sin chats disponibles</option>`}
        </select>
        ${currentOption && currentChatId != null
          ? html`<div className="menu-hint">ID: ${currentChatId}</div>`
          : null}
        ${loading
          ? html`<div className="menu-status">
              <${Spinner} size=${16} />
              <span>Cargando usuarios...</span>
            </div>`
          : null}
        <label className="menu-label" htmlFor="profileSelect">Perfil activo</label>
        <select
          id="profileSelect"
          className="menu-select"
          value=${activeProfile ?? ""}
          onChange=${onProfileChange}
          disabled=${!hasProfiles || profilesLoading}
        >
          ${profilesLoading
            ? html`<option value="">Cargando perfiles...</option>`
            : hasProfiles
            ? profiles.map((profile) => html`<option key=${profile} value=${profile}>${profile}</option>`)
            : html`<option value="">Sin perfiles disponibles</option>`}
        </select>
        ${error ? html`<div className="menu-error">${error}</div>` : null}
        <nav className="menu-nav">
          <a className="nav-btn" href="/">Dashboard</a>
          <a className="nav-btn active" href="/profiles">Perfiles</a>
        </nav>
      </section>
      <footer className="menu-footer">
        <p>Gestiona perfiles y terminos desde la web.</p>
        <p className="hint">Los cambios afectan al bot inmediatamente.</p>
      </footer>
    </aside>
  `;
}

function TopicsCard({ topics, weights, loading }) {
  const weightEntries = useMemo(
    () =>
      Object.entries(weights || {})
        .sort((a, b) => (b[1] || 0) - (a[1] || 0))
        .slice(0, 12),
    [weights],
  );

  return html`
    <article className="card">
      <h2>Temas</h2>
      <ul className="tags">
        ${loading
          ? html`<li>Cargando temas...</li>`
          : topics?.length
          ? topics.map((topic) => html`<li key=${topic}>${topic}</li>`)
          : html`<li>Sin temas detectados.</li>`}
      </ul>
      <div className="weights">
        ${loading
          ? "Calculando pesos..."
          : weightEntries.length
          ? weightEntries.map(
              ([topic, weight]) =>
                html`<div key=${topic}>
                  <strong>${topic}:</strong> ${Number(weight).toFixed(3)}
                </div>`,
            )
          : "Sin pesos asociados."}
      </div>
    </article>
  `;
}

function ProfileListCard({
  profiles,
  activeProfile,
  selectedProfile,
  onSelect,
  onActivate,
  activatingProfile,
}) {
  return html`
    <article className="card">
      <h2>Perfiles del chat</h2>
      <ul className="profile-list">
        ${profiles.length
          ? profiles.map((name) => {
              const isActive = name === activeProfile;
              const isSelected = name === selectedProfile;
              const pending = activatingProfile === name;
              const itemClass = `profile-item${isActive ? " is-active" : ""}${
                isSelected ? " is-selected" : ""
              }`;
              return html`<li key=${name} className=${itemClass}>
                <div className="profile-meta">
                  <span className="profile-name">${name}</span>
                  ${isActive ? html`<span className="profile-badge">Activo</span>` : null}
                </div>
                <div className="profile-buttons">
                  <button
                    type="button"
                    className="toolbar-btn small"
                    onClick=${() => onSelect(name)}
                  >
                    Seleccionar
                  </button>
                  ${!isActive
                    ? html`<button
                        type="button"
                        className="toolbar-btn small"
                        onClick=${() => onActivate(name)}
                        disabled=${pending}
                      >
                        ${pending ? "Activando..." : "Activar"}
                      </button>`
                    : null}
                </div>
              </li>`;
            })
          : html`<li className="profile-item empty">Sin perfiles configurados.</li>`}
      </ul>
    </article>
  `;
}

function PreferencesCard({ config, loading }) {
  const prefs = config
    ? [
        ["Similitud minima", config.sim_threshold ?? "--"],
        ["Top N", config.topn ?? "--"],
        ["Edad maxima (h)", config.max_age_hours ?? "--"],
        ["Intervalo tick (min)", config.poll_min ?? "--"],
        ["Hora diaria (bot)", config.poll_daily_time || "--"],
        ["LLM habilitado", config.llm_enabled ? "Si" : "No"],
        ["Umbral LLM", config.llm_threshold ?? "--"],
        ["LLM max/tick", config.llm_max_per_tick ?? "--"],
        ["LLM max/on-demand", config.llm_ondemand_max_per_hour ?? "--"],
      ]
    : [];

  return html`
    <article className="card">
      <h2>Preferencias</h2>
      ${loading && !prefs.length
        ? html`<p>Cargando preferencias...</p>`
        : html`<dl className="properties">
            ${prefs.map(
              ([label, value]) =>
                html`<${Fragment} key=${label}>
                  <dt>${label}</dt>
                  <dd>${value}</dd>
                </${Fragment}>`,
            )}
          </dl>`}
    </article>
  `;
}

function StatusCard({ config, loading }) {
  const status = config
    ? [
        ["Perfil activo", config.active_profile || "--"],
        ["Perfiles disponibles", (config.profiles || []).join(", ") || "--"],
        ["Ultimo tick", formatDate(config.last_lucky_ts)],
        ["Likes totales", config.likes_total ?? 0],
        ["Dislikes totales", config.dislikes_total ?? 0],
      ]
    : [];

  return html`
    <article className="card">
      <h2>Estado</h2>
      ${loading && !status.length
        ? html`<p>Cargando estado...</p>`
        : html`<dl className="properties">
            ${status.map(
              ([label, value]) =>
                html`<${Fragment} key=${label}>
                  <dt>${label}</dt>
                  <dd>${value}</dd>
                </${Fragment}>`,
            )}
          </dl>`}
    </article>
  `;
}

function ProfileManagerApp({ initial }) {
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState(null);
  const [currentChatId, setCurrentChatId] = useState(initial.defaultChatId ?? null);
  const [configState, setConfigState] = useState({
    data: null,
    loading: false,
    error: null,
  });
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [status, setStatus] = useState({ message: "", tone: "info" });
  const [formName, setFormName] = useState("");
  const [formText, setFormText] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [activatingProfile, setActivatingProfile] = useState(null);
  const [editSummary, setEditSummary] = useState("");
  const [editTopics, setEditTopics] = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  const fileInputRef = useRef(null);
  const { toasts, pushToast, dismissToast } = useToasts({ autoDismiss: 6000 });

  const showStatus = useCallback(
    (message, tone = "info", { flash = false, title } = {}) => {
      setStatus({ message, tone });
      if (flash) {
        pushToast({
          tone,
          title: title || (tone === "error" ? "Error" : "Perfiles"),
          message,
        });
      }
    },
    [pushToast],
  );

  useDocumentTitle(
    currentChatId != null
      ? `PaperRadar - Perfiles - Chat ${currentChatId}`
      : "PaperRadar - Perfiles",
  );

  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    setUsersError(null);
    try {
      const list = await fetchJSON("/users");
      setUsers(list);
      setUsersLoading(false);
      setCurrentChatId((prev) => {
        if (prev != null && list.some((user) => user.chat_id === prev)) {
          return prev;
        }
        if (
          initial.defaultChatId != null &&
          list.some((user) => user.chat_id === initial.defaultChatId)
        ) {
          return initial.defaultChatId;
        }
        return list[0]?.chat_id ?? null;
      });
    } catch (err) {
      setUsers([]);
      setUsersLoading(false);
      setUsersError(err.message || "No se pudieron cargar los usuarios.");
      showStatus(err.message || "No se pudieron cargar los usuarios.", "error", {
        flash: true,
        title: "Usuarios",
      });
    }
  }, [initial.defaultChatId, showStatus]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    showStatus("");
    if (currentChatId == null) {
      setConfigState({ data: null, loading: false, error: null });
      setSelectedProfile(null);
      return;
    }
    const controller = new AbortController();
    setConfigState({ data: null, loading: true, error: null });
    fetchJSON(`/users/${currentChatId}/config`, { signal: controller.signal })
      .then((data) => {
        setConfigState({ data, loading: false, error: null });
      })
      .catch((err) => {
        if (err.name === "AbortError") {
          return;
        }
        const message = err.message || "No se pudo cargar la configuracion.";
        setConfigState({
          data: null,
          loading: false,
          error: message,
        });
        showStatus(message, "error", { flash: true, title: "Configuracion" });
      });
    return () => controller.abort();
  }, [currentChatId, showStatus]);

  useEffect(() => {
    const cfg = configState.data;
    if (!cfg || !Array.isArray(cfg.profiles) || cfg.profiles.length === 0) {
      setSelectedProfile(null);
      return;
    }
    if (selectedProfile && cfg.profiles.includes(selectedProfile)) {
      return;
    }
    setSelectedProfile(cfg.active_profile || cfg.profiles[0]);
  }, [configState.data, selectedProfile]);

  useEffect(() => {
    const cfg = configState.data;
    if (!cfg || !selectedProfile) {
      setEditSummary("");
      setEditTopics([]);
      return;
    }
    const overrides = cfg.profile_overrides || {};
    const profilesData = cfg.profiles_data || {};
    const overrideEntry = overrides[selectedProfile] || {};
    const summary =
      overrideEntry.summary ??
      (selectedProfile === cfg.active_profile
        ? cfg.profile_summary
        : profilesData[selectedProfile]) ??
      "";
    const topics =
      overrideEntry.topics ??
      (selectedProfile === cfg.active_profile ? cfg.profile_topics : []);
    const weights =
      overrideEntry.topic_weights ??
      (selectedProfile === cfg.active_profile ? cfg.profile_topic_weights : {});
    setEditSummary(summary || "");
    setEditTopics(
      normalizeTopicEntries(Array.isArray(topics) ? topics : [], weights || {}),
    );
  }, [configState.data, selectedProfile]);

  const handleChatChange = useCallback(
    (event) => {
      const value = Number(event.target.value);
      setCurrentChatId(Number.isFinite(value) ? value : null);
      showStatus("");
    },
    [showStatus],
  );

  const handleSelectProfile = useCallback(
    (name) => {
      setSelectedProfile(name);
      showStatus("");
    },
    [showStatus],
  );

  const handleTopicAdd = useCallback(() => {
    setEditTopics((prev) => {
      const list = Array.isArray(prev) ? [...prev] : [];
      list.push({ name: "", weight: "" });
      return list;
    });
  }, []);

  const handleTopicRemove = useCallback((index) => {
    setEditTopics((prev) => {
      if (!Array.isArray(prev)) return [];
      return prev.filter((_, idx) => idx !== index);
    });
  }, []);

  const handleTopicNameChange = useCallback((index, value) => {
    setEditTopics((prev) => {
      const list = Array.isArray(prev) ? [...prev] : [];
      if (!list[index]) {
        list[index] = { name: "", weight: "" };
      }
      list[index] = { ...list[index], name: value };
      return list;
    });
  }, []);

  const handleTopicWeightChange = useCallback((index, value) => {
    setEditTopics((prev) => {
      const list = Array.isArray(prev) ? [...prev] : [];
      if (!list[index]) {
        list[index] = { name: "", weight: "" };
      }
      list[index] = { ...list[index], weight: value };
      return list;
    });
  }, []);

  const handleSaveOverrides = useCallback(async () => {
    if (!currentChatId || !selectedProfile) {
      showStatus("Selecciona un usuario y un perfil para guardar.", "error", {
        flash: true,
        title: "Perfiles",
      });
      return;
    }
    const profileName = selectedProfile;
    const summary = (editSummary ?? "").trim();
    const topicEntries = Array.isArray(editTopics) ? editTopics : [];
    const topics = [];
    const topicWeights = {};
    for (const entry of topicEntries) {
      const name = (entry?.name || "").trim();
      if (!name) continue;
      if (!topics.includes(name)) {
        topics.push(name);
      }
      const weightValue = clampWeight(entry?.weight);
      if (weightValue !== null) {
        topicWeights[name] = weightValue;
      }
    }
    setIsSaving(true);
    showStatus("Guardando cambios...", "info");
    try {
      const cfg = await patchJSON(
        `/users/${currentChatId}/profiles/${encodeURIComponent(profileName)}`,
        {
          summary,
          topics,
          ...(Object.keys(topicWeights).length > 0 ? { topic_weights: topicWeights } : {}),
        },
      );
      setConfigState({ data: cfg, loading: false, error: null });
      setSelectedProfile(profileName);
      const overrides = cfg.profile_overrides || {};
      const profilesData = cfg.profiles_data || {};
      const overrideEntry = overrides[profileName] || {};
      const updatedTopics =
        overrideEntry.topics ??
        (profileName === cfg.active_profile ? cfg.profile_topics : []);
      const updatedWeights =
        overrideEntry.topic_weights ??
        (profileName === cfg.active_profile ? cfg.profile_topic_weights : {});
      const updatedSummary =
        overrideEntry.summary ??
        (profileName === cfg.active_profile
          ? cfg.profile_summary
          : profilesData[profileName]) ??
        "";
      setEditSummary(updatedSummary || "");
      setEditTopics(
        normalizeTopicEntries(
          Array.isArray(updatedTopics) ? updatedTopics : [],
          updatedWeights || {},
        ),
      );
      await loadUsers();
      showStatus("Perfil actualizado.", "success", {
        flash: true,
        title: "Perfil actualizado",
      });
    } catch (err) {
      showStatus(err.message || "No se pudieron guardar los cambios.", "error", {
        flash: true,
        title: "Perfiles",
      });
    } finally {
      setIsSaving(false);
    }
  }, [
    currentChatId,
    editSummary,
    editTopics,
    loadUsers,
    selectedProfile,
    showStatus,
  ]);

  const handleActivateProfile = useCallback(
    async (name) => {
      if (!currentChatId || !name) return;
      setActivatingProfile(name);
      showStatus("Cambiando perfil...", "info");
      try {
        const cfg = await postJSON(`/users/${currentChatId}/profiles/use`, { profile: name });
        setConfigState({ data: cfg, loading: false, error: null });
        setSelectedProfile(cfg.active_profile || name);
        await loadUsers();
        showStatus("Perfil activo actualizado.", "success", {
          flash: true,
          title: "Perfil activado",
        });
      } catch (err) {
        showStatus(err.message || "No se pudo cambiar el perfil.", "error", {
          flash: true,
          title: "Perfiles",
        });
      } finally {
        setActivatingProfile(null);
      }
    },
    [currentChatId, loadUsers, showStatus],
  );

  const handleCreateProfile = useCallback(
    async (event) => {
      event?.preventDefault();
      if (!currentChatId) {
        showStatus("Selecciona un chat primero.", "error", {
          flash: true,
          title: "Perfiles",
        });
        return;
      }
      const name = formName.trim();
      const text = formText.trim();
      if (!name) {
        showStatus("Ingresa un nombre para el perfil.", "error", {
          flash: true,
          title: "Perfiles",
        });
        return;
      }
      setIsCreating(true);
      showStatus("Creando perfil...", "info");
      try {
        const cfg = await postJSON(`/users/${currentChatId}/profiles`, {
          name,
          text,
          set_active: true,
        });
        setConfigState({ data: cfg, loading: false, error: null });
        setSelectedProfile(cfg.active_profile || name);
        setFormName("");
        setFormText("");
        await loadUsers();
        showStatus("Perfil creado correctamente.", "success", {
          flash: true,
          title: "Perfil creado",
        });
      } catch (err) {
        showStatus(err.message || "No se pudo crear el perfil.", "error", {
          flash: true,
          title: "Perfiles",
        });
      } finally {
        setIsCreating(false);
      }
    },
    [currentChatId, formName, formText, loadUsers, showStatus],
  );

  const handleDeleteProfile = useCallback(async () => {
    if (!currentChatId) {
      showStatus("Selecciona un chat primero.", "error", {
        flash: true,
        title: "Perfiles",
      });
      return;
    }
    if (!selectedProfile) {
      showStatus("Selecciona un perfil para eliminar.", "error", {
        flash: true,
        title: "Perfiles",
      });
      return;
    }
    if (!globalThis.confirm(`Eliminar el perfil "${selectedProfile}"?`)) {
      return;
    }
    setIsDeleting(true);
    showStatus("Eliminando perfil...", "info");
    try {
      const cfg = await fetchJSON(
        `/users/${currentChatId}/profiles/${encodeURIComponent(selectedProfile)}`,
        { method: "DELETE" },
      );
      setConfigState({ data: cfg, loading: false, error: null });
      setSelectedProfile(cfg.active_profile || null);
      await loadUsers();
      showStatus("Perfil eliminado.", "success", {
        flash: true,
        title: "Perfil eliminado",
      });
    } catch (err) {
      showStatus(err.message || "No se pudo eliminar el perfil.", "error", {
        flash: true,
        title: "Perfiles",
      });
    } finally {
      setIsDeleting(false);
    }
  }, [currentChatId, selectedProfile, loadUsers, showStatus]);

  const handleUpload = useCallback(async () => {
    if (!currentChatId) {
      showStatus("Selecciona un chat primero.", "error", {
        flash: true,
        title: "Perfiles",
      });
      return;
    }
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      showStatus("Selecciona un archivo PDF.", "error", {
        flash: true,
        title: "Perfiles",
      });
      return;
    }
    if (file.type !== "application/pdf") {
      showStatus("El archivo debe ser un PDF.", "error", {
        flash: true,
        title: "Perfiles",
      });
      return;
    }
    setIsUploading(true);
    showStatus("Subiendo PDF...", "info");
    try {
      const form = new FormData();
      form.append("file", file);
      if (selectedProfile) {
        form.append("profile", selectedProfile);
      }
      const response = await fetch(`/users/${currentChatId}/profiles/upload`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        let message = `Error ${response.status}`;
        try {
          const payload = await response.json();
          if (payload?.detail) message = payload.detail;
        } catch (_err) {
          /* no-op */
        }
        throw new Error(message);
      }
      const cfg = await response.json();
      setConfigState({ data: cfg, loading: false, error: null });
      setSelectedProfile(cfg.active_profile || selectedProfile);
      await loadUsers();
      showStatus("Perfil actualizado.", "success", {
        flash: true,
        title: "Perfil actualizado",
      });
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err) {
      showStatus(err.message || "No se pudo procesar el PDF.", "error", {
        flash: true,
        title: "Perfiles",
      });
    } finally {
      setIsUploading(false);
    }
  }, [currentChatId, selectedProfile, loadUsers, showStatus]);

  const config = configState.data;
  const profiles = useMemo(() => (config?.profiles ? [...config.profiles] : []), [config]);
  const activeProfile = config?.active_profile ?? "";
  const overridesMap = config?.profile_overrides || {};
  const profilesData = config?.profiles_data || {};
  const selectedOverride = selectedProfile ? overridesMap[selectedProfile] || {} : {};
  const selectedSummary =
    selectedProfile == null || !config
      ? ""
      : (selectedOverride.summary ??
          (selectedProfile === activeProfile
            ? config.profile_summary
            : profilesData[selectedProfile])) || "";
  const selectedTopics =
    selectedProfile == null || !config
      ? []
      : selectedOverride.topics ??
        (selectedProfile === activeProfile ? config.profile_topics || [] : []);
  const selectedWeights =
    selectedProfile == null || !config
      ? {}
      : selectedOverride.topic_weights ??
        (selectedProfile === activeProfile ? config.profile_topic_weights || {} : {});

  let summaryText = "Selecciona un usuario para ver su configuracion.";
  if (currentChatId != null) {
    if (configState.loading) {
      summaryText = "Cargando configuracion...";
    } else if (!config) {
      summaryText = configState.error || "Sin datos disponibles.";
    } else if (!selectedProfile) {
      summaryText = "Selecciona un perfil de la lista.";
    } else {
      summaryText = selectedSummary || "Sin resumen disponible.";
    }
  }

  const statusClass = `upload-status${status.message ? ` ${status.tone}` : ""}`;
  const canDelete = profiles.length > 1 && Boolean(selectedProfile) && !isDeleting;
  const profilesLoading = configState.loading || Boolean(activatingProfile);
  const canSaveOverrides =
    Boolean(currentChatId && selectedProfile) && !isSaving && !configState.loading;
  const topicsEditable = Array.isArray(editTopics) ? editTopics : [];
  const disableEditor =
    !currentChatId || !selectedProfile || configState.loading || isSaving;

  const handleSidebarProfileChange = useCallback(
    (event) => {
      const value = event.target?.value ?? "";
      if (!value || config?.active_profile === value) return;
      handleActivateProfile(value);
    },
    [config?.active_profile, handleActivateProfile],
  );

  return html`
    <div className="app-shell">
      <${Sidebar}
        users=${users}
        loading=${usersLoading}
        error=${usersError}
        currentChatId=${currentChatId}
        onChatChange=${handleChatChange}
        activeProfile=${activeProfile}
        profiles=${profiles}
        profilesLoading=${profilesLoading}
        onProfileChange=${handleSidebarProfileChange}
      />
      <main className="content">
        <section id="manager-view" className="view active">
          <div className="config-grid">
            <article className="card">
              <h2>Resumen del perfil</h2>
              ${configState.loading && currentChatId != null
                ? html`<div className="placeholder-stack">
                    <${Skeleton} width="100%" height="16px" />
                    <${Skeleton} width="92%" height="14px" />
                    <${Skeleton} width="85%" height="14px" />
                    <${Skeleton} width="78%" height="14px" />
                  </div>`
                : html`<p className="summary">${summaryText}</p>`}
            </article>

            <${TopicsCard}
              topics=${selectedTopics}
              weights=${selectedWeights}
              loading=${configState.loading}
            />

            <${ProfileListCard}
              profiles=${profiles}
              activeProfile=${config?.active_profile || ""}
              selectedProfile=${selectedProfile}
              onSelect=${handleSelectProfile}
              onActivate=${handleActivateProfile}
              activatingProfile=${activatingProfile}
            />

            <div className="card profile-editor">
              <h2>Editar perfil</h2>
              <p className="hint">
                ${selectedProfile
                  ? html`Estas editando <strong>${selectedProfile}</strong>. Los cambios se aplican
                      al guardar.`
                  : "Selecciona un perfil para poder editarlo."}
              </p>
              <div className="field-group">
                <label htmlFor="profileSummary">Resumen / abstract</label>
                <textarea
                  id="profileSummary"
                  rows=${4}
                  value=${editSummary}
                  onChange=${(event) => setEditSummary(event.target.value)}
                  placeholder="Describe brevemente los intereses del perfil"
                  disabled=${disableEditor}
                />
              </div>
              <div className="field-group">
                <label>Temas y pesos</label>
                <div className="topics-editor">
                  ${topicsEditable.length
                    ? topicsEditable.map(
                        (topic, index) => html`<div className="topic-row" key=${`${topic.name || "topic"}-${index}`}>
                          <input
                            type="text"
                            className="topic-input"
                            placeholder="Nuevo tema"
                            value=${topic.name}
                            onChange=${(event) => handleTopicNameChange(index, event.target.value)}
                            disabled=${disableEditor}
                          />
                          <input
                            type="number"
                            className="topic-weight"
                            min="0"
                            max="1"
                            step="0.01"
                            placeholder="auto"
                            value=${topic.weight ?? ""}
                            onChange=${(event) => handleTopicWeightChange(index, event.target.value)}
                            disabled=${disableEditor}
                          />
                          <button
                            type="button"
                            className="topic-remove"
                            onClick=${() => handleTopicRemove(index)}
                            disabled=${disableEditor}
                          >
                            Quitar
                          </button>
                        </div>`,
                      )
                    : html`<p className="empty-topics">Sin temas. Agrega uno nuevo para comenzar.</p>`}
                </div>
                <div className="button-row topic-actions">
                  <button
                    type="button"
                    className="toolbar-btn"
                    onClick=${handleTopicAdd}
                    disabled=${disableEditor}
                  >
                    Agregar tema
                  </button>
                </div>
                <p className="hint">
                  Ajusta los pesos entre 0 y 1. Deja el campo vacio para calcularlos automaticamente.
                </p>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="toolbar-btn primary"
                  onClick=${handleSaveOverrides}
                  disabled=${!canSaveOverrides}
                >
                  ${isSaving ? "Guardando..." : "Guardar cambios"}
                </button>
              </div>
            </div>

            <${PreferencesCard} config=${config} loading=${configState.loading} />
            <${StatusCard} config=${config} loading=${configState.loading} />

            <div className="card profile-actions">
              <h2>Crear nuevo perfil</h2>
              <div className="field-group">
                <label htmlFor="newProfileName">Nombre</label>
                <input
                  id="newProfileName"
                  type="text"
                  maxLength=${60}
                  placeholder="Nombre del perfil"
                  value=${formName}
                  onChange=${(event) => setFormName(event.target.value)}
                />
              </div>
              <div className="field-group">
                <label htmlFor="newProfileText">Resumen / intereses (opcional)</label>
                <textarea
                  id="newProfileText"
                  rows=${4}
                  placeholder="Descripcion corta del perfil"
                  value=${formText}
                  onChange=${(event) => setFormText(event.target.value)}
                />
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="toolbar-btn primary"
                  onClick=${handleCreateProfile}
                  disabled=${isCreating || !formName.trim()}
                >
                  ${isCreating ? "Creando..." : "Crear perfil"}
                </button>
                <button
                  type="button"
                  className="toolbar-btn danger"
                  onClick=${handleDeleteProfile}
                  disabled=${!canDelete}
                >
                  ${isDeleting ? "Eliminando..." : "Eliminar perfil seleccionado"}
                </button>
              </div>
            </div>

            <div className="card profile-upload">
              <h2>Actualizar desde PDF</h2>
              <p className="hint">
                El PDF debe contener el texto del perfil para extraer temas y resumen.
              </p>
              <input id="profilePdf" type="file" accept="application/pdf" ref=${fileInputRef} />
              <button
                type="button"
                className="toolbar-btn"
                onClick=${handleUpload}
                disabled=${isUploading}
              >
                ${isUploading ? "Subiendo..." : "Subir PDF"}
              </button>
            </div>
          </div>
          <div id="profileStatus" className=${statusClass}>
            ${status.message}
          </div>
        </section>
      </main>
      <${ToastHost} toasts=${toasts} onDismiss=${dismissToast} />
    </div>
  `;
}

const container = document.getElementById("app");
if (container) {
  const root = createRoot(container);
  root.render(html`<${ProfileManagerApp} initial=${initialData} />`);
}
