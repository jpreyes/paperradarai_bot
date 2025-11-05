import {
  React,
  html,
  Fragment,
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef,
  useToasts,
  ToastHost,
  Spinner,
  Skeleton,
  EmptyState,
  useDocumentTitle,
} from "./ui.js";
import { createRoot } from "https://esm.sh/react-dom@18/client";

const initialData = globalThis.__PAPERRADAR_INITIAL__ ?? {};

const SORT_OPTIONS = [
  { value: "score", label: "Similitud" },
  { value: "published", label: "Fecha publicacion" },
  { value: "venue", label: "Revista" },
  { value: "authors", label: "Autores" },
  { value: "fetched_at", label: "Fecha recogida" },
];

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

async function postJSON(url, body, options = {}) {
  return fetchJSON(
    url,
    Object.assign(
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      options,
    ),
  );
}

async function patchJSON(url, body, options = {}) {
  return fetchJSON(
    url,
    Object.assign(
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      options,
    ),
  );
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

function authorLabel(authors) {
  if (!Array.isArray(authors) || authors.length === 0) return "--";
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")} y ${authors.length - 3} mas`;
}

function clampLimit(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return 25;
  return Math.min(200, Math.max(5, Math.round(numeric)));
}

function encodeKey(value) {
  try {
    return encodeURIComponent(value ?? "");
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

function extractor(entry, key) {
  const item = entry?.item || {};
  switch (key) {
    case "score":
      return entry?.score ?? 0;
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
      const ts = Date.parse(entry?.fetched_at);
      return Number.isNaN(ts) ? null : ts;
    }
    default:
      return null;
  }
}

function sortPapers(items, key, direction) {
  const source = Array.isArray(items) ? items : [];
  const copy = [...source];
  const dir = direction === "asc" ? 1 : -1;
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

function PaperCard({ entry }) {
  const item = entry?.item || {};
  const ideas = Array.isArray(entry?.bullets?.ideas) ? entry.bullets.ideas : [];
  const similarities = Array.isArray(entry?.bullets?.similarities)
    ? entry.bullets.similarities
    : [];
  const tagRaw = entry?.bullets?.tag || "";
  const tagUpper = tagRaw ? String(tagRaw).toUpperCase() : "";
  const paperKey = encodeKey(entryKey(entry));
  const detailSections = [];

  if (ideas.length) {
    detailSections.push(
      html`<div key="ideas">
        <strong>Ideas:</strong>
        <ul className="idea-list">
          ${ideas.map((idea, idx) => html`<li key=${`idea-${idx}`}>${idea}</li>`)}
        </ul>
      </div>`,
    );
  }
  if (similarities.length) {
    detailSections.push(
      html`<div key="similarities">
        <strong>Coincidencias:</strong>
        <ul className="idea-list">
          ${similarities.map((sim, idx) => html`<li key=${`sim-${idx}`}>${sim}</li>`)}
        </ul>
      </div>`,
    );
  }
  if (tagRaw) {
    detailSections.push(html`<span key="tag" className="tag-pill">${tagRaw}</span>`);
  }

  const likeClass = `action-btn like-btn${entry?.liked ? " is-active" : ""}`;
  const dislikeClass = `action-btn dislike-btn${entry?.disliked ? " is-active" : ""}`;

  return html`
    <article className="paper-card">
      <header className="paper-card__header">
        <div className="paper-card__score">
          <span className="score-pill">
            ${typeof entry?.score === "number" ? entry.score.toFixed(3) : entry?.score ?? "--"}
          </span>
          ${tagUpper
            ? html`<span className=${`tag-badge ${String(tagRaw).toLowerCase()}`}>${tagUpper}</span>`
            : null}
        </div>
        <div className="paper-card__source">
          <span>${item.source || "Fuente desconocida"}</span>
          <span className="paper-card__venue">${item.venue || "Revista no registrada"}</span>
        </div>
      </header>
      <div className="paper-card__body">
        <h3 className="paper-card__title">
          <a href=${item.url || "#"} target="_blank" rel="noopener noreferrer">
            ${item.title || "Sin titulo"}
          </a>
        </h3>
        <div className="paper-card__meta">
          <span className="paper-card__meta-item">
            <strong>Autores:</strong> ${authorLabel(item.authors)}
          </span>
          <span className="paper-card__meta-item">
            <strong>Publicado:</strong> ${item.published || item.year || "--"}
          </span>
        </div>
        ${detailSections.length
          ? html`<div className="paper-card__details">
              ${detailSections.map((section, idx) => html`<div key=${`detail-${idx}`}>${section}</div>`)}
            </div>`
          : null}
      </div>
      <footer className="paper-card__footer">
        <div className="paper-card__timestamps">
          <span>Recogido: ${formatDate(entry?.fetched_at)}</span>
        </div>
        <div className="feedback-btns">
          <button
            type="button"
            className=${likeClass}
            data-action="like"
            data-paper=${paperKey}
            title="Like"
          >
            +
          </button>
          <button
            type="button"
            className=${dislikeClass}
            data-action="dislike"
            data-paper=${paperKey}
            title="Dislike"
          >
            -
          </button>
        </div>
      </footer>
    </article>
  `;
}

function PapersView({
  chatId,
  page,
  limit,
  sortKey,
  sortDir,
  papersState,
  view,
  onSortKeyChange,
  onSortDirChange,
  onLimitChange,
  onHistoryRefresh,
  onLiveRefresh,
  onPrev,
  onNext,
}) {
  const sortedItems = useMemo(
    () => sortPapers(papersState.items, sortKey, sortDir),
    [papersState.items, sortKey, sortDir],
  );

  const total = papersState.totalRanked || 0;
  const pageCount = total ? Math.ceil(total / limit) || 1 : 1;
  const safePage = total ? Math.min(page, pageCount - 1) : 0;
  const hasPrev = safePage > 0 && total > 0;
  const hasNext = total > 0 && (safePage + 1) * limit < total;
  const start = total ? Math.min(total, (papersState.offset || 0) + 1) : 0;
  const end = total
    ? Math.min(total, (papersState.offset || 0) + sortedItems.length)
    : 0;
  const showSkeleton = papersState.loading && sortedItems.length === 0;
  const emptyState =
    !papersState.loading && !papersState.error && sortedItems.length === 0;

  const skeletonCards = useMemo(
    () =>
      Array.from({ length: Math.min(6, limit || 6) }).map(
        (_, idx) => html`<article key=${`skeleton-${idx}`} className="paper-card paper-card--skeleton">
          <div className="paper-card__header">
            <div className="paper-card__score">
              <${Skeleton} width="56px" height="20px" radius="999px" />
              <${Skeleton} width="40px" height="20px" radius="999px" />
            </div>
            <div className="skeleton-stack">
              <${Skeleton} width="110px" height="14px" />
              <${Skeleton} width="90px" height="12px" />
            </div>
          </div>
          <div className="paper-card__body">
            <div className="skeleton-stack">
              <${Skeleton} width="92%" height="18px" />
              <${Skeleton} width="75%" height="16px" />
            </div>
            <div className="skeleton-stack">
              <${Skeleton} width="68%" height="12px" />
              <${Skeleton} width="48%" height="12px" />
            </div>
            <div className="skeleton-stack">
              <${Skeleton} width="100%" height="10px" />
              <${Skeleton} width="95%" height="10px" />
            </div>
          </div>
          <div className="paper-card__footer">
            <${Skeleton} width="140px" height="12px" />
            <div className="skeleton-actions">
              <${Skeleton} width="36px" height="36px" radius="12px" />
              <${Skeleton} width="36px" height="36px" radius="12px" />
            </div>
          </div>
        </article>`,
      ),
    [limit],
  );

  const cards = sortedItems.map((entry, idx) =>
    html`<${PaperCard} key=${entryKey(entry) || `card-${idx}`} entry=${entry} />`,
  );

  return html`
    <section id="view-papers" className=${`view${view === "papers" ? " active" : ""}`}>
      <div className="toolbar">
        <div className="toolbar-group">
          <label htmlFor="sortSelect">Ordenar por</label>
          <select id="sortSelect" value=${sortKey} onChange=${onSortKeyChange}>
            ${SORT_OPTIONS.map(
              (option) =>
                html`<option key=${option.value} value=${option.value}>${option.label}</option>`,
            )}
          </select>
        </div>
        <div className="toolbar-group">
          <label htmlFor="sortDir">Sentido</label>
          <select id="sortDir" value=${sortDir} onChange=${onSortDirChange}>
            <option value="desc">Descendente</option>
            <option value="asc">Ascendente</option>
          </select>
        </div>
        <div className="toolbar-group">
          <label htmlFor="limitInput">Limite</label>
          <input
            id="limitInput"
            type="number"
            min="5"
            max="200"
            step="5"
            value=${limit}
            onChange=${onLimitChange}
          />
        </div>
        <div className="toolbar-group toolbar-actions">
          <button
            type="button"
            className="toolbar-btn"
            onClick=${onHistoryRefresh}
            disabled=${!chatId}
          >
            Recargar historial
          </button>
          <button
            type="button"
            className="toolbar-btn primary"
            onClick=${onLiveRefresh}
            disabled=${!chatId}
          >
            Actualizar (live)
          </button>
        </div>
      </div>

      <div className="pagination">
        <button
          type="button"
          id="prevPage"
          className="pagination-btn"
          onClick=${onPrev}
          disabled=${!hasPrev || papersState.loading}
        >
          &larr; Anterior
        </button>
        <div id="pageInfo" className="pagination-info">
          ${total ? `Pagina ${safePage + 1} de ${pageCount}` : "Sin datos"}
        </div>
        <button
          type="button"
          id="nextPage"
          className="pagination-btn"
          onClick=${onNext}
          disabled=${!hasNext || papersState.loading}
        >
          Siguiente &rarr;
        </button>
      </div>

      <div id="papersCount" className="section-meta">
        ${total
          ? `Mostrando ${start}-${end} de ${total} hallazgos (perfil ${chatId ?? "--"}).`
          : sortedItems.length
          ? `Mostrando ${sortedItems.length} hallazgos (perfil ${chatId ?? "--"}).`
          : ""}
      </div>

      <div id="papersTable" className="cards-wrapper">
        ${papersState.error
          ? html`<div className="error">Error: ${papersState.error}</div>`
          : html`<div className="papers-grid">
              ${showSkeleton ? skeletonCards : cards}
            </div>`}
        ${papersState.loading && sortedItems.length
          ? html`<div className="table-overlay">
              <${Spinner} size=${20} />
              <span>Cargando datos frescos...</span>
            </div>`
          : null}
      </div>

      ${emptyState
        ? html`<div className="empty-state-wrapper">
            <${EmptyState}
              title="Sin resultados"
              message="Intenta actualizar o cambia los filtros para este perfil."
              action=${html`<button
                type="button"
                className="toolbar-btn"
                onClick=${onHistoryRefresh}
                disabled=${!chatId}
              >
                Recargar historial
              </button>`}
            />
          </div>`
        : null}
    </section>
  `;
}

function ConfigView({
  state,
  view,
  activeProfile,
  editSummary,
  topicEntries,
  onSummaryChange,
  onTopicNameChange,
  onTopicWeightChange,
  onTopicAdd,
  onTopicRemove,
  onSave,
  saving,
}) {
  const cfg = state.data;
  const topics = cfg?.profile_topics || [];
  const weightsEntries = Object.entries(cfg?.profile_topic_weights || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);

  const preferences = cfg
    ? [
        ["Similitud minima", cfg.sim_threshold ?? "--"],
        ["Top N", cfg.topn ?? "--"],
        ["Edad maxima (h)", cfg.max_age_hours ?? "--"],
        ["Intervalo tick (min)", cfg.poll_min ?? "--"],
        ["Hora diaria (bot)", cfg.poll_daily_time || "--"],
        ["LLM habilitado", cfg.llm_enabled ? "Si" : "No"],
        ["Umbral LLM", cfg.llm_threshold ?? "--"],
        ["LLM max/tick", cfg.llm_max_per_tick ?? "--"],
        ["LLM max/on-demand", cfg.llm_ondemand_max_per_hour ?? "--"],
      ]
    : [];

  const status = cfg
    ? [
        ["Perfil activo", cfg.active_profile || "--"],
        ["Perfiles disponibles", (cfg.profiles || []).join(", ") || "--"],
        ["Ultimo tick", formatDate(cfg.last_lucky_ts)],
        ["Likes totales", cfg.likes_total ?? 0],
        ["Dislikes totales", cfg.dislikes_total ?? 0],
      ]
    : [];
  const activeProfileName = activeProfile || cfg?.active_profile || "";
  const canEdit = Boolean(activeProfileName);
  const topicsEditable = Array.isArray(topicEntries) ? topicEntries : [];
  const disableEdit = !canEdit || saving;

  return html`
    <section id="view-config" className=${`view${view === "config" ? " active" : ""}`}>
      <div className="config-grid">
        ${state.loading && !cfg
          ? html`<article className="card card--placeholder">
              <h2>Resumen del perfil</h2>
              <div className="placeholder-stack">
                <${Skeleton} width="100%" height="16px" />
                <${Skeleton} width="92%" height="14px" />
                <${Skeleton} width="85%" height="14px" />
                <${Skeleton} width="78%" height="14px" />
              </div>
            </article>`
          : null}
        ${state.error
          ? html`<article className="card">
              <h2>Configuracion</h2>
              <p className="error">${state.error}</p>
            </article>`
          : null}
        ${cfg
          ? html`
              <article className="card">
                <h2>Resumen del perfil</h2>
                <p className="summary">${cfg.profile_summary || "Sin resumen disponible."}</p>
              </article>
              <article className="card">
                <h2>Temas</h2>
                <ul className="tags">
                  ${topics.length
                    ? topics.map((topic) => html`<li key=${topic}>${topic}</li>`)
                    : html`<li key="none">Sin temas detectados.</li>`}
                </ul>
                <div className="weights">
                  ${weightsEntries.length
                    ? weightsEntries.map(
                        ([topic, weight]) =>
                          html`<div key=${topic}>
                            <strong>${topic}:</strong> ${weight.toFixed(3)}
                          </div>`,
                      )
                    : "Sin pesos asociados."}
                </div>
              </article>
              <article className="card">
                <h2>Preferencias</h2>
                <dl className="properties">
                  ${preferences.map(
                    ([label, value]) =>
                      html`<${Fragment} key=${label}>
                        <dt>${label}</dt>
                        <dd>${value}</dd>
                      </${Fragment}>`,
                  )}
                </dl>
              </article>
              <article className="card">
                <h2>Estado</h2>
                <dl className="properties">
                  ${status.map(
                    ([label, value]) =>
                      html`<${Fragment} key=${label}>
                        <dt>${label}</dt>
                        <dd>${value}</dd>
                      </${Fragment}>`,
                  )}
                </dl>
              </article>
              <article className="card card--editor">
                <h2>Editar perfil activo</h2>
                <p className="hint">
                  ${canEdit
                    ? html`Guardando estos cambios se actualizar&aacute; el resumen y los t&eacute;rminos
                        del perfil <strong>${activeProfileName}</strong> autom&aacute;ticamente.`
                    : "Selecciona un usuario con perfil activo para editar."}
                </p>
                <div className="field-group">
                  <label htmlFor="configSummary">Resumen / abstract</label>
                  <textarea
                    id="configSummary"
                    rows=${4}
                    value=${editSummary}
                    onChange=${onSummaryChange}
                    placeholder="Describe brevemente los intereses del perfil"
                    disabled=${disableEdit}
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
                              onChange=${(event) => onTopicNameChange(index, event.target.value)}
                              disabled=${disableEdit}
                            />
                            <input
                              type="number"
                              className="topic-weight"
                              min="0"
                              max="1"
                              step="0.01"
                              placeholder="auto"
                              value=${topic.weight ?? ""}
                              onChange=${(event) => onTopicWeightChange(index, event.target.value)}
                              disabled=${disableEdit}
                            />
                            <button
                              type="button"
                              className="topic-remove"
                              onClick=${() => onTopicRemove(index)}
                              disabled=${disableEdit}
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
                      onClick=${onTopicAdd}
                      disabled=${disableEdit}
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
                    onClick=${onSave}
                    disabled=${disableEdit}
                  >
                    ${saving ? "Guardando..." : "Guardar cambios"}
                  </button>
                </div>
              </article>
            `
          : null}
      </div>
    </section>
  `;
}

function Sidebar({
  users,
  loading,
  error,
  currentChatId,
  activeProfile,
  profiles,
  profilesLoading,
  view,
  onChatChange,
  onProfileChange,
  onViewChange,
}) {
  const hasUsers = users.length > 0;
  const hasProfiles = Array.isArray(profiles) && profiles.length > 0;
  const currentUser = users.find((user) => user.chat_id === currentChatId);
  const userLabel = currentUser
    ? `Chat ${currentUser.chat_id}`
    : currentChatId != null
    ? `Chat ${currentChatId}`
    : "Sin usuario";

  return html`
    <aside className="sidebar">
      <header className="brand">
        <span className="logo">PR</span>
        <div>
          <h1>PaperRadar</h1>
          <p className="subtitle">Visualizador</p>
        </div>
      </header>
      <section className="menu">
        <div className="menu-label">Usuario</div>
        <div className="menu-value">${userLabel}</div>
        ${loading
          ? html`<div className="menu-status">
              <${Spinner} size=${16} />
              <span>Cargando usuarios...</span>
            </div>`
          : null}
        <label className="menu-label" htmlFor="profileSelect">
          Perfil activo
        </label>
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
            ? profiles.map((name) => html`<option key=${name} value=${name}>${name}</option>`)
            : html`<option value="">Sin perfiles disponibles</option>`}
        </select>
        <nav className="menu-nav">
          <button
            type="button"
            className=${`nav-btn${view === "papers" ? " active" : ""}`}
            onClick=${() => onViewChange("papers")}
          >
            Papers
          </button>
          <button
            type="button"
            className=${`nav-btn${view === "config" ? " active" : ""}`}
            onClick=${() => onViewChange("config")}
          >
            Configuracion
          </button>
          <a className="nav-btn" href="/profiles">Perfiles</a>
        </nav>
        ${error ? html`<div className="menu-error">${error}</div>` : null}
      </section>
      <footer className="menu-footer">
        <p>Datos compartidos con el bot.</p>
        <p className="hint">Los terminos de busqueda siguen al perfil activo.</p>
      </footer>
    </aside>
  `;
}

function DashboardApp({ initial }) {
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState(null);
  const [currentChatId, setCurrentChatId] = useState(initial.defaultChatId ?? null);
  const [view, setView] = useState("papers");
  const [sortKey, setSortKey] = useState("score");
  const [sortDir, setSortDir] = useState("desc");
  const [limit, setLimit] = useState(25);
  const [page, setPage] = useState(0);
  const [papersRequest, setPapersRequest] = useState({ mode: "history", nonce: 0 });
  const [papersState, setPapersState] = useState({
    items: [],
    totalRanked: 0,
    offset: 0,
    hasMore: false,
    loading: false,
    error: null,
    lastMode: "history",
  });
  const [configState, setConfigState] = useState({
    data: null,
    loading: false,
    error: null,
  });
  const [configNonce, setConfigNonce] = useState(0);
  const { toasts, pushToast, dismissToast } = useToasts({ autoDismiss: 6000 });
  const inflightToastRef = useRef(null);
  const profileToastRef = useRef(null);
  const [profilePending, setProfilePending] = useState(false);
  const [editSummary, setEditSummary] = useState("");
  const [editTopics, setEditTopics] = useState([]);

  useDocumentTitle(
    currentChatId != null
      ? `PaperRadar · Chat ${currentChatId}`
      : "PaperRadar Dashboard",
  );

  useEffect(
    () => () => {
      if (profileToastRef.current) {
        dismissToast(profileToastRef.current);
        profileToastRef.current = null;
      }
    },
    [dismissToast],
  );

  const requestPapers = useCallback((mode = "history") => {
    setPapersRequest((prev) => ({ mode, nonce: prev.nonce + 1 }));
  }, []);

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
      pushToast({
        tone: "error",
        title: "Usuarios",
        message: err.message || "No se pudieron cargar los usuarios.",
      });
    }
  }, [initial.defaultChatId, pushToast]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    if (currentChatId == null) {
      setPapersState((prev) => ({
        ...prev,
        items: [],
        totalRanked: 0,
        offset: 0,
        hasMore: false,
      }));
      setConfigState((prev) => ({ ...prev, data: null }));
      setProfilePending(false);
      if (profileToastRef.current) {
        dismissToast(profileToastRef.current);
        profileToastRef.current = null;
      }
      return;
    }
    setProfilePending(false);
    if (profileToastRef.current) {
      dismissToast(profileToastRef.current);
      profileToastRef.current = null;
    }
    setPage(0);
    setPapersState((prev) => ({
      ...prev,
      items: [],
      totalRanked: 0,
      offset: 0,
      hasMore: false,
    }));
    setConfigState((prev) => ({ ...prev, data: null }));
    setConfigNonce((value) => value + 1);
    requestPapers("history");
  }, [currentChatId, requestPapers, dismissToast]);

  useEffect(() => {
    if (currentChatId == null) return;
    const controller = new AbortController();
    setConfigState({ data: null, loading: true, error: null });
    fetchJSON(`/users/${currentChatId}/config`, { signal: controller.signal })
      .then((data) => {
        setConfigState({ data, loading: false, error: null });
        setProfilePending(false);
        if (profileToastRef.current) {
          dismissToast(profileToastRef.current);
          profileToastRef.current = null;
        }
      })
      .catch((err) => {
        if (err.name === "AbortError") {
          return;
        }
        setConfigState({
          data: null,
          loading: false,
          error: err.message || "No se pudo cargar la configuracion.",
        });
        setProfilePending(false);
        if (profileToastRef.current) {
          dismissToast(profileToastRef.current);
          profileToastRef.current = null;
        }
        pushToast({
          tone: "error",
          title: "Configuracion",
          message: err.message || "No se pudo cargar la configuracion.",
        });
      });
    return () => controller.abort();
  }, [currentChatId, configNonce, dismissToast, pushToast]);

  useEffect(() => {
    const data = configState.data;
    const summary = data?.profile_summary ?? "";
    const topicList = Array.isArray(data?.profile_topics) ? data.profile_topics : [];
    const weightMap = data?.profile_topic_weights || {};
    setEditSummary(summary);
    setEditTopics(normalizeTopicEntries(topicList, weightMap));
  }, [
    configState.data?.profile_summary,
    configState.data?.profile_topics,
    configState.data?.profile_topic_weights,
  ]);

  useEffect(() => {
    if (currentChatId == null) return;
    if (papersRequest.nonce === 0) return;

    const controller = new AbortController();
    setPapersState((prev) => ({ ...prev, loading: true, error: null }));
    const offset = page * limit;
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
      mode: papersRequest.mode,
    });

    fetchJSON(`/users/${currentChatId}/papers?${params.toString()}`, {
      signal: controller.signal,
    })
      .then((payload) => {
        const freshItems = Array.isArray(payload?.items) ? payload.items : [];
        let scheduledPage = null;
        setPapersState((prev) => {
          let items = freshItems;
          let totalRanked = payload?.total_ranked ?? freshItems.length;
          let offsetValue = payload?.offset ?? offset;
          let hasMore = Boolean(payload?.has_more);

          if (papersRequest.mode === "live") {
            const merged = [];
            const known = new Set();
            for (const entry of freshItems) {
              const key = entryKey(entry);
              if (key) known.add(key);
              merged.push(entry);
            }
            const prevItems = Array.isArray(prev.items) ? prev.items : [];
            for (const entry of prevItems) {
              const key = entryKey(entry);
              if (key && known.has(key)) {
                continue;
              }
              if (key) known.add(key);
              merged.push(entry);
            }
            items = merged;
            totalRanked = merged.length;
            offsetValue = 0;
            hasMore = false;
          }

          if (papersRequest.mode !== "live" && totalRanked > 0 && offsetValue >= totalRanked) {
            const nextPage = Math.max(0, Math.ceil(totalRanked / limit) - 1);
            if (nextPage !== page) {
              scheduledPage = nextPage;
            }
            return {
              ...prev,
              totalRanked,
              offset: offsetValue,
              hasMore,
              loading: false,
            };
          }

          return {
            ...prev,
            items,
            totalRanked,
            offset: offsetValue,
            hasMore,
            loading: false,
            error: null,
            lastMode: papersRequest.mode,
          };
        });

        if (scheduledPage !== null && scheduledPage !== page) {
          setPage(scheduledPage);
          requestPapers("history");
        }
        if (inflightToastRef.current != null) {
          dismissToast(inflightToastRef.current);
          inflightToastRef.current = null;
          pushToast({
            tone: "success",
            title: "Datos actualizados",
            message:
              papersRequest.mode === "live"
                ? "Resultados en vivo actualizados correctamente."
                : "Historial refrescado.",
          });
        }
      })
      .catch((err) => {
        if (err.name === "AbortError") {
          return;
        }
        setPapersState((prev) => ({
          ...prev,
          loading: false,
          error: err.message || "No se pudieron cargar los papers.",
        }));
        if (inflightToastRef.current != null) {
          dismissToast(inflightToastRef.current);
          inflightToastRef.current = null;
        }
        pushToast({
          tone: "error",
          title: "Papers",
          message: err.message || "No se pudieron cargar los papers.",
        });
      });

    return () => controller.abort();
  }, [currentChatId, limit, page, papersRequest, requestPapers, dismissToast, pushToast]);

  const handleChatChange = useCallback((event) => {
    const value = Number(event.target.value);
    if (!Number.isFinite(value)) {
      setCurrentChatId(null);
      return;
    }
    setCurrentChatId(value);
  }, []);

  const handleSortKeyChange = useCallback((event) => {
    setSortKey(event.target.value);
  }, []);

  const handleSortDirChange = useCallback((event) => {
    setSortDir(event.target.value);
  }, []);

  const handleLimitChange = useCallback(
    (event) => {
      const next = clampLimit(event.target.value);
      setLimit(next);
      setPage(0);
      requestPapers("history");
    },
    [requestPapers],
  );

  const handleHistoryRefresh = useCallback(() => {
    if (currentChatId == null) return;
    pushToast({
      tone: "info",
      title: "Historial",
      message: "Recargando historial del perfil seleccionado.",
    });
    requestPapers("history");
    setConfigNonce((value) => value + 1);
  }, [currentChatId, pushToast, requestPapers]);

  const handleLiveRefresh = useCallback(() => {
    if (currentChatId == null) return;
    if (inflightToastRef.current != null) {
      dismissToast(inflightToastRef.current);
      inflightToastRef.current = null;
    }
    inflightToastRef.current = pushToast({
      tone: "info",
      title: "Actualizando",
      message: "Consultando nuevas coincidencias en vivo...",
      timeout: 0,
    });
    setPage(0);
    requestPapers("live");
    setConfigNonce((value) => value + 1);
  }, [currentChatId, dismissToast, pushToast, requestPapers]);

  const handlePrevPage = useCallback(() => {
    if (page === 0) return;
    setPage((value) => Math.max(0, value - 1));
    requestPapers("history");
  }, [page, requestPapers]);

  const handleNextPage = useCallback(() => {
    const total = papersState.totalRanked || 0;
    const nextOffset = (page + 1) * limit;
    if (nextOffset >= total) return;
    setPage((value) => value + 1);
    requestPapers("history");
  }, [limit, page, papersState.totalRanked, requestPapers]);

  const activeProfile = configState.data?.active_profile ?? "";
  const availableProfiles = useMemo(
    () => (Array.isArray(configState.data?.profiles) ? configState.data.profiles : []),
    [configState.data?.profiles],
  );

  const handleProfileSelect = useCallback(
    async (event) => {
      if (!currentChatId) return;
      const nextProfile = event.target?.value ?? "";
      if (!nextProfile || configState.data?.active_profile === nextProfile) {
        return;
      }
      setProfilePending(true);
      const pendingToast = pushToast({
        tone: "info",
        title: "Perfil",
        message: `Activando perfil \"${nextProfile}\"...`,
        timeout: 0,
      });
      profileToastRef.current = pendingToast;
      try {
        const cfg = await postJSON(`/users/${currentChatId}/profiles/use`, { profile: nextProfile });
        if (pendingToast) {
          dismissToast(pendingToast);
          profileToastRef.current = null;
        }
        setProfilePending(false);
        setConfigState({ data: cfg, loading: false, error: null });
        setPage(0);
        requestPapers("history");
        await loadUsers();
        pushToast({
          tone: "success",
          title: "Perfil activo",
          message: `Perfil \"${cfg.active_profile}\" activado.`,
        });
      } catch (err) {
        if (pendingToast) {
          dismissToast(pendingToast);
          profileToastRef.current = null;
        }
        setProfilePending(false);
        pushToast({
          tone: "error",
          title: "Perfil",
          message: err.message || "No se pudo activar el perfil.",
        });
      }
    },
    [
      currentChatId,
      configState.data?.active_profile,
      dismissToast,
      loadUsers,
      pushToast,
      requestPapers,
    ],
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

  const handleProfileUpdate = useCallback(async () => {
    if (!currentChatId) return;
    const active = configState.data?.active_profile;
    if (!active) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "No hay un perfil activo para actualizar.",
      });
      return;
    }
    const trimmedSummary = (editSummary ?? "").trim();
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
    setProfilePending(true);
    const pendingToast = pushToast({
      tone: "info",
      title: "Perfil",
      message: "Guardando cambios del perfil...",
      timeout: 0,
    });
    profileToastRef.current = pendingToast;
    try {
      const payload = {
        summary: trimmedSummary,
        topics,
      };
      if (Object.keys(topicWeights).length > 0) {
        payload.topic_weights = topicWeights;
      }
      const cfg = await patchJSON(
        `/users/${currentChatId}/profiles/${encodeURIComponent(active)}`,
        payload,
      );
      if (pendingToast) {
        dismissToast(pendingToast);
        profileToastRef.current = null;
      }
      setProfilePending(false);
      setConfigState({ data: cfg, loading: false, error: null });
      setEditSummary(cfg.profile_summary || "");
      setEditTopics(
        normalizeTopicEntries(
          Array.isArray(cfg.profile_topics) ? cfg.profile_topics : [],
          cfg.profile_topic_weights || {},
        ),
      );
      setPage(0);
      requestPapers("history");
      await loadUsers();
      pushToast({
        tone: "success",
        title: "Perfil",
        message: "Perfil actualizado correctamente.",
      });
    } catch (err) {
      if (pendingToast) {
        dismissToast(pendingToast);
        profileToastRef.current = null;
      }
      setProfilePending(false);
      pushToast({
        tone: "error",
        title: "Perfil",
        message: err.message || "No se pudieron guardar los cambios.",
      });
    }
  }, [
    configState.data?.active_profile,
    currentChatId,
    dismissToast,
    editSummary,
    editTopics,
    loadUsers,
    pushToast,
    requestPapers,
  ]);

  return html`
    <div className="app-shell">
      <${Sidebar}
        users=${users}
        loading=${usersLoading}
        error=${usersError}
        currentChatId=${currentChatId}
        activeProfile=${activeProfile}
        profiles=${availableProfiles}
        profilesLoading=${configState.loading || profilePending}
        view=${view}
        onChatChange=${handleChatChange}
        onProfileChange=${handleProfileSelect}
        onViewChange=${setView}
      />
      <main className="content">
        <${PapersView}
          chatId=${currentChatId}
          page=${page}
          limit=${limit}
          sortKey=${sortKey}
          sortDir=${sortDir}
          papersState=${papersState}
          view=${view}
          onSortKeyChange=${handleSortKeyChange}
          onSortDirChange=${handleSortDirChange}
          onLimitChange=${handleLimitChange}
          onHistoryRefresh=${handleHistoryRefresh}
          onLiveRefresh=${handleLiveRefresh}
          onPrev=${handlePrevPage}
          onNext=${handleNextPage}
        />
        <${ConfigView}
          state=${configState}
          view=${view}
          activeProfile=${activeProfile}
          editSummary=${editSummary}
          onSummaryChange=${(event) => setEditSummary(event.target.value)}
          topicEntries=${editTopics}
          onTopicNameChange=${handleTopicNameChange}
          onTopicWeightChange=${handleTopicWeightChange}
          onTopicAdd=${handleTopicAdd}
          onTopicRemove=${handleTopicRemove}
          onSave=${handleProfileUpdate}
          saving=${profilePending}
        />
      </main>
      <${ToastHost} toasts=${toasts} onDismiss=${dismissToast} />
    </div>
  `;
}

const container = document.getElementById("app");
if (container) {
  const root = createRoot(container);
  root.render(html`<${DashboardApp} initial=${initialData} />`);
}


