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
  { value: "analysis", label: "Tipo analisis (LLM/Heur)" },
];

const JOURNAL_SORT_OPTIONS = [
  { value: "score", label: "Score combinado" },
  { value: "fit_score", label: "Fit LLM" },
  { value: "similarity", label: "Similitud vectorial" },
  { value: "topic_overlap", label: "Coincidencia de temas" },
  { value: "title", label: "Titulo" },
  { value: "analysis", label: "Tipo analisis (LLM/Heur)" },
];

const DEFAULT_JOURNAL_STATE = {
  items: [],
  loading: false,
  error: null,
  catalogSize: 0,
  generatedAt: null,
  usedEmbeddings: false,
};

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

function formatNumber(value, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return Number(value).toFixed(digits);
}

function formatPercent(value, digits = 1) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return `${(value * 100).toFixed(digits)}%`;
}

function formatCurrency(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  const formatted = numeric.toLocaleString("en-US", {
    minimumFractionDigits: numeric >= 1000 ? 0 : 2,
    maximumFractionDigits: numeric >= 1000 ? 0 : 2,
  });
  return `USD ${formatted}`;
}

function sanitizeTags(value) {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value
      .map((entry) => String(entry ?? "").trim())
      .filter((entry) => entry.length > 0);
  }
  if (typeof value === "string") {
    return value
      .split(/[,;]/)
      .map((part) => part.trim())
      .filter((part) => part.length > 0);
  }
  return [];
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
    case "analysis":
      return (entry?.bullets?.tag || "").toString();
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

function loadPinSessions() {
  try {
    const raw = globalThis.localStorage?.getItem("paperradarPins");
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return parsed;
    }
  } catch (_err) {
    /* ignore */
  }
  return {};
}

function persistPinSessions(data) {
  try {
    globalThis.localStorage?.setItem("paperradarPins", JSON.stringify(data));
  } catch (_err) {
    /* ignore */
  }
}

function journalExtractor(entry, key) {
  const journal = entry?.journal || {};
  const analysis = entry?.analysis || {};
  switch (key) {
    case "score":
      return entry?.score ?? 0;
    case "fit_score":
      return analysis?.fit_score ?? 0;
    case "similarity":
      return entry?.similarity ?? 0;
    case "topic_overlap":
      return entry?.topic_overlap ?? 0;
    case "title":
      return (journal.title || "").toLowerCase();
    case "analysis":
      return (analysis.tag || "").toString();
    default:
      return null;
  }
}

function sortJournals(items, key, direction) {
  const source = Array.isArray(items) ? items : [];
  const copy = [...source];
  const dir = direction === "asc" ? 1 : -1;
  copy.sort((a, b) => {
    const av = journalExtractor(a, key);
    const bv = journalExtractor(b, key);
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

function JournalCard({ entry }) {
  const journal = entry?.journal || {};
  const analysis = entry?.analysis || {};
  const topics = sanitizeTags(journal.topics?.length ? journal.topics : journal.keywords);
  const categories = sanitizeTags(journal.categories);
  const chips = (topics.length ? topics : categories).slice(0, 4);
  const reasons = Array.isArray(analysis.reasons) ? analysis.reasons : [];
  const risks = Array.isArray(analysis.risks) ? analysis.risks : [];
  const metrics = journal.metrics || {};
  const impactValue = metrics.impact_factor ?? metrics.if;
  const sjrValue = metrics.sjr ?? metrics["SJR"];
  const speedWeeksRaw = journal?.speed?.avg_weeks_to_decision ?? journal?.speed?.weeks;
  const speedWeeks = Number(speedWeeksRaw);
  const speedLabel =
    Number.isFinite(speedWeeks) && speedWeeks > 0 ? `${speedWeeks} sem` : "--";
  const apcLabel = formatCurrency(journal.apc_usd);
  const fitValue =
    typeof analysis.fit_score === "number" && Number.isFinite(analysis.fit_score)
      ? Math.max(0, Math.min(1, analysis.fit_score))
      : null;
  const analysisTag = analysis.tag ? String(analysis.tag).toUpperCase() : "HEUR";
  const similarityValue =
    typeof entry?.similarity === "number" && Number.isFinite(entry.similarity)
      ? Math.max(-1, Math.min(1, entry.similarity))
      : 0;
  const topicOverlap =
    typeof entry?.topic_overlap === "number" && entry.topic_overlap >= 0
      ? Math.min(1, entry.topic_overlap)
      : 0;

  return html`
    <article className="journal-card">
      <header className="journal-card__header">
        <div className="journal-card__headings">
          <div className="journal-card__rank">#${entry?.rank ?? "--"}</div>
          <div>
            <p className="journal-card__publisher">${journal.publisher || journal.country || "Revista"}</p>
            <h3 className="journal-card__title">${journal.title || "Sin titulo"}</h3>
            ${journal.website
              ? html`<a className="journal-card__link" href=${journal.website} target="_blank" rel="noopener noreferrer">
                  Visitar sitio
                </a>`
              : null}
            ${chips.length
              ? html`<div className="journal-card__chips">
                  ${chips.map((chip) => html`<span key=${chip} className="journal-chip">${chip}</span>`)}
                </div>`
              : null}
          </div>
        </div>
        <div className="journal-card__score">
          <div>
            <span className="score-label">Score</span>
            <span className="score-value">${formatNumber(entry?.score ?? 0, 3)}</span>
          </div>
          <div>
            <span className="score-label">Similitud</span>
            <span className="score-value">${formatPercent(similarityValue)}</span>
          </div>
          <div>
            <span className="score-label">Temas</span>
            <span className="score-value">${formatPercent(topicOverlap)}</span>
          </div>
        </div>
      </header>
      <section className="journal-card__analysis">
        <div className="journal-card__analysis-head">
          <span className="analysis-tag">${analysisTag}</span>
          <span className="analysis-score">${fitValue !== null ? formatPercent(fitValue, 0) : "--"}</span>
        </div>
        <p className="journal-card__summary">
          ${analysis.fit_summary || "Sin analisis disponible para esta revista."}
        </p>
        <div className="journal-card__lists">
          ${reasons.length
            ? html`<div>
                <h4>Razones</h4>
                <ul>
                  ${reasons.slice(0, 3).map((reason, idx) => html`<li key=${`reason-${idx}`}>${reason}</li>`)}
                </ul>
              </div>`
            : null}
          ${risks.length
            ? html`<div>
                <h4>Riesgos</h4>
                <ul>
                  ${risks.slice(0, 3).map((risk, idx) => html`<li key=${`risk-${idx}`}>${risk}</li>`)}
                </ul>
              </div>`
            : null}
        </div>
      </section>
      <footer className="journal-card__footer">
        <div className="journal-card__stat">
          <span>Impact factor</span>
          <strong>${impactValue != null ? formatNumber(Number(impactValue), 2) : "--"}</strong>
        </div>
        <div className="journal-card__stat">
          <span>SJR</span>
          <strong>${sjrValue != null ? formatNumber(Number(sjrValue), 2) : "--"}</strong>
        </div>
        <div className="journal-card__stat">
          <span>Decision</span>
          <strong>${speedLabel}</strong>
        </div>
        <div className="journal-card__stat">
          <span>Acceso</span>
          <strong>${journal.open_access ? "Abierto" : "Cerrado"}</strong>
        </div>
        <div className="journal-card__stat">
          <span>APC</span>
          <strong>${apcLabel ?? "--"}</strong>
        </div>
        <div className="journal-card__stat">
          <span>Pais</span>
          <strong>${journal.country || "--"}</strong>
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
  if (!chatId) {
    return html`
      <section id="view-papers" className=${`view${view === "papers" ? " active" : ""}`}>
        <div className="empty-state">Selecciona un usuario y valida el PIN para ver los papers.</div>
      </section>
    `;
  }
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

function JournalsView({
  chatId,
  view,
  state,
  sortKey,
  sortDir,
  onSortKeyChange,
  onSortDirChange,
  onRefresh,
  ingesting,
}) {
  if (!chatId) {
    return html`
      <section id="view-journals" className=${`view${view === "journals" ? " active" : ""}`}>
        <div className="empty-state">Selecciona un usuario y valida el PIN para ver las revistas.</div>
      </section>
    `;
  }
  const showSkeleton = state.loading && (!state.items || state.items.length === 0);
  const emptyState =
    !state.loading && !state.error && (!state.items || state.items.length === 0);
  const embeddingsLabel = state.usedEmbeddings ? "Embeddings activos" : "Modo heuristico";
  const sortedItems = useMemo(
    () => sortJournals(state.items, sortKey, sortDir),
    [state.items, sortKey, sortDir],
  );

  const skeletonCards = useMemo(
    () =>
      Array.from({ length: 6 }).map(
        (_, idx) => html`<article key=${`journal-skeleton-${idx}`} className="journal-card journal-card--skeleton">
          <div className="journal-card__header">
            <div className="journal-card__headings">
              <${Skeleton} width="40px" height="18px" />
              <div className="skeleton-stack">
                <${Skeleton} width="160px" height="18px" />
                <${Skeleton} width="120px" height="14px" />
              </div>
            </div>
            <div className="journal-card__score">
              <${Skeleton} width="60px" height="24px" radius="12px" />
            </div>
          </div>
          <div className="journal-card__analysis">
            <${Skeleton} width="100%" height="14px" />
            <${Skeleton} width="95%" height="12px" />
          </div>
          <div className="journal-card__footer">
            <${Skeleton} width="80px" height="16px" />
            <${Skeleton} width="80px" height="16px" />
          </div>
        </article>`,
      ),
    [],
  );

  const cards = sortedItems.map((entry, idx) =>
    html`<${JournalCard}
      key=${entry.journal_id || entry?.journal?.title || `journal-${idx}`}
      entry=${entry}
    />`,
  );

  return html`
    <section id="view-journals" className=${`view${view === "journals" ? " active" : ""}`}>
      <div className="toolbar">
        <div className="toolbar-group">
          <label htmlFor="journalSort">Ordenar por</label>
          <select id="journalSort" value=${sortKey} onChange=${onSortKeyChange}>
            ${JOURNAL_SORT_OPTIONS.map(
              (option) =>
                html`<option key=${option.value} value=${option.value}>${option.label}</option>`,
            )}
          </select>
        </div>
        <div className="toolbar-group">
          <label htmlFor="journalSortDir">Sentido</label>
          <select id="journalSortDir" value=${sortDir} onChange=${onSortDirChange}>
            <option value="desc">Descendente</option>
            <option value="asc">Ascendente</option>
          </select>
        </div>
        <div className="toolbar-meta">
          <span>Catalogo: ${state.catalogSize ?? 0}</span>
          <span>Generado: ${state.generatedAt ? formatDate(state.generatedAt) : "--"}</span>
          <span>${embeddingsLabel}</span>
        </div>
        <div className="toolbar-group toolbar-actions">
          <button
            type="button"
            className="toolbar-btn primary"
            onClick=${onRefresh}
            disabled=${!chatId || state.loading || ingesting}
          >
            ${ingesting ? "Buscando catalogo..." : "Actualizar catalogo"}
          </button>
        </div>
      </div>

      ${state.error ? html`<div className="error">${state.error}</div>` : null}

      <div className="cards-wrapper">
        <div className="journals-grid">
          ${showSkeleton ? skeletonCards : cards}
        </div>
        ${state.loading && cards.length
          ? html`<div className="table-overlay">
              <${Spinner} size=${20} />
              <span>Actualizando recomendaciones...</span>
            </div>`
          : null}
        ${ingesting
          ? html`<div className="table-overlay">
              <${Spinner} size=${20} />
              <span>Descargando revistas de Crossref...</span>
            </div>`
          : null}
      </div>

      ${emptyState
        ? html`<div className="empty-state-wrapper">
            <${EmptyState}
              title="Sin recomendaciones"
              message="Crea o selecciona un perfil para generar coincidencias con revistas."
              action=${html`<button
                type="button"
                className="toolbar-btn"
                onClick=${onRefresh}
                disabled=${!chatId}
              >
                Reintentar
              </button>`}
            />
          </div>`
        : null}
    </section>
  `;
}

function ConfigView({
  chatId,
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
  ingestText,
  onIngestTextChange,
  onIngestSubmit,
  ingestingText,
  pdfInputRef,
  onPdfUpload,
  uploadingPdf,
  onDeleteProfile,
  deletingProfile,
  canDeleteProfile,
  newProfileName,
  onNewProfileNameChange,
  newProfileText,
  onNewProfileTextChange,
  onCreateProfile,
  creatingProfile,
  magicEmail,
  onMagicEmailChange,
  magicLinkData,
  magicLinkLoading,
  onMagicLinkRequest,
  magicLinkHistory,
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
  const hasAbstractInput = Boolean((ingestText || "").trim());
  const disableAbstractAction = !canEdit || ingestingText || !hasAbstractInput;
  const disablePdfAction = !canEdit || uploadingPdf;
  const disableDeleteAction = !canDeleteProfile || deletingProfile;
  const newProfileReady = Boolean((newProfileName || "").trim());
  const disableCreateAction = creatingProfile || !newProfileReady;

  if (!chatId) {
    return html`
      <section id="view-config" className=${`view${view === "config" ? " active" : ""}`}>
        <div className="card">
          <h2>Protegido por PIN</h2>
          <p>Selecciona un usuario y valida el PIN para administrar su configuracion.</p>
        </div>
      </section>
    `;
  }

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
              <article className="card profile-tools">
                <h2>Actualizar perfil activo</h2>
                <p className="hint">
                  ${canEdit
                    ? html`Los cambios se aplicar&aacute;n a <strong>${activeProfileName}</strong>.`
                    : "Selecciona un perfil desde el menu lateral."}
                </p>
                <div className="field-group">
                  <label htmlFor="profileAbstract">Nuevo abstract</label>
                  <textarea
                    id="profileAbstract"
                    rows=${4}
                    placeholder="Pega aqui el abstract o descripcion completa"
                    value=${ingestText}
                    onChange=${onIngestTextChange}
                    disabled=${!canEdit || ingestingText}
                  />
                </div>
                <div className="button-row">
                  <button
                    type="button"
                    className="toolbar-btn"
                    onClick=${onIngestSubmit}
                    disabled=${disableAbstractAction}
                  >
                    ${ingestingText ? "Procesando..." : "Aplicar abstract"}
                  </button>
                  <button
                    type="button"
                    className="toolbar-btn danger"
                    onClick=${onDeleteProfile}
                    disabled=${disableDeleteAction}
                  >
                    ${deletingProfile ? "Eliminando..." : "Eliminar perfil"}
                  </button>
                </div>
                ${!canDeleteProfile
                  ? html`<p className="hint">Necesitas al menos otro perfil para poder eliminar el actual.</p>`
                  : null}
                <div className="field-group">
                  <label htmlFor="profilePdf">Actualizar desde PDF</label>
                  <input
                    id="profilePdf"
                    type="file"
                    accept="application/pdf"
                    ref=${pdfInputRef}
                    disabled=${!canEdit || uploadingPdf}
                  />
                  <button
                    type="button"
                    className="toolbar-btn"
                    onClick=${onPdfUpload}
                    disabled=${disablePdfAction}
                  >
                    ${uploadingPdf ? "Subiendo..." : "Subir PDF"}
                  </button>
                  <p className="hint">Analizaremos el PDF para extraer resumen, temas y pesos.</p>
                </div>
              </article>
              <article className="card profile-create">
                <h2>Crear nuevo perfil</h2>
                <p className="hint">Se activar&aacute; inmediatamente despu&eacute;s de crearlo.</p>
                <div className="field-group">
                  <label htmlFor="newProfileName">Nombre</label>
                  <input
                    id="newProfileName"
                    type="text"
                    maxLength=${60}
                    placeholder="Nombre del perfil"
                    value=${newProfileName}
                    onChange=${onNewProfileNameChange}
                  />
                </div>
                <div className="field-group">
                  <label htmlFor="newProfileText">Abstract / intereses (opcional)</label>
                  <textarea
                    id="newProfileText"
                    rows=${3}
                    placeholder="Describe brevemente los intereses del nuevo perfil"
                    value=${newProfileText}
                    onChange=${onNewProfileTextChange}
                  />
                </div>
                <div className="button-row">
                  <button
                    type="button"
                    className="toolbar-btn primary"
                    onClick=${onCreateProfile}
                    disabled=${disableCreateAction}
                  >
                    ${creatingProfile ? "Creando..." : "Crear y activar"}
                  </button>
                </div>
              </article>
              <article className="card magic-link-card">
                <h2>Registro web (magic link)</h2>
                <p className="hint">
                  Genera un enlace de acceso y comp&aacute;rtelo con investigadores que no usan Telegram.
                </p>
                <div className="field-group">
                  <label htmlFor="magicEmail">Correo electr&oacute;nico</label>
                  <input
                    id="magicEmail"
                    type="email"
                    placeholder="investigador@ejemplo.com"
                    value=${magicEmail}
                    onChange=${onMagicEmailChange}
                  />
                </div>
                <div className="button-row">
                  <button
                    type="button"
                    className="toolbar-btn primary"
                    onClick=${onMagicLinkRequest}
                    disabled=${magicLinkLoading}
                  >
                    ${magicLinkLoading ? "Generando..." : "Generar link"}
                  </button>
                </div>
                ${magicLinkData
                  ? html`<div className="magic-link-output">
                      <p>Enlace generado:</p>
                      <code>${magicLinkData.absoluteUrl || ""}</code>
                      <p>PIN: <strong>${magicLinkData.pin || "------"}</strong></p>
                      <p className="hint">
                        ID asignado: <strong>${magicLinkData.chat_id}</strong>. Comparte el link para
                        que active su panel.
                      </p>
                    </div>`
                  : null}
              </article>
              ${magicLinkHistory && magicLinkHistory.length
                ? html`<article className="card magic-link-card">
                    <h2>Links generados</h2>
                    <div className="magic-history">
                      ${magicLinkHistory.map(
                        (entry, index) => html`<div key=${`${entry.email}-${index}`} className="magic-history__item">
                          <p><strong>Correo:</strong> ${entry.email}</p>
                          <p><strong>Chat ID:</strong> ${entry.chat_id}</p>
                          <p><strong>PIN:</strong> ${entry.pin || "------"}</p>
                          <p><strong>Link:</strong></p>
                          <code>${entry.absoluteUrl || entry.login_url || ""}</code>
                          <p className="hint">${formatDate(entry.generated_at)}</p>
                        </div>`,
                      )}
                    </div>
                  </article>`
                : null}
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
  onProfileChange,
  onViewChange,
  isAuthorized,
  loginChatId,
  onLoginChatChange,
  loginPin,
  onLoginPinChange,
  onLoginSubmit,
  loginError,
  loginLoading,
  savedSessions,
  onSavedSessionSelect,
  onLogoutChat,
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
        ${!isAuthorized
          ? html`
              <div className="login-card">
                <label className="menu-label" htmlFor="loginChat">Chat ID</label>
                <input
                  id="loginChat"
                  className="menu-select"
                  type="number"
                  min="1"
                  placeholder="Ej. 8455728091"
                  value=${loginChatId}
                  onChange=${onLoginChatChange}
                />
                <label className="menu-label" htmlFor="loginPin">PIN</label>
                <input
                  id="loginPin"
                  className="menu-select"
                  type="password"
                  placeholder="PIN"
                  value=${loginPin}
                  onChange=${onLoginPinChange}
                />
                ${loginError ? html`<div className="menu-error">${loginError}</div>` : null}
                <button
                  type="button"
                  className="toolbar-btn primary"
                  onClick=${onLoginSubmit}
                  disabled=${loginLoading}
                >
                  ${loginLoading ? "Ingresando..." : "Iniciar sesion"}
                </button>
                ${savedSessions.length
                  ? html`<div className="session-list">
                      <p className="hint">Sesiones recordadas:</p>
                      ${savedSessions.map(
                        (chatId) => html`<button
                          type="button"
                          className="toolbar-btn"
                          onClick=${() => onSavedSessionSelect(chatId)}
                        >
                          Chat ${chatId}
                        </button>`,
                      )}
                    </div>`
                  : null}
              </div>
            `
          : html`
              <div className="menu-value">${userLabel}</div>
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
                  className=${`nav-btn${view === "journals" ? " active" : ""}`}
                  onClick=${() => onViewChange("journals")}
                >
                  Revistas
                </button>
                <button
                  type="button"
                  className=${`nav-btn${view === "config" ? " active" : ""}`}
                  onClick=${() => onViewChange("config")}
                >
                  Configuracion
                </button>
              </nav>
              <button type="button" className="toolbar-btn danger" onClick=${onLogoutChat}>
                Cerrar sesion
              </button>
            `}
        ${loading
          ? html`<div className="menu-status">
              <${Spinner} size=${16} />
              <span>Cargando usuarios...</span>
            </div>`
          : null}
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
  const pinSessionsRef = useRef(loadPinSessions());
  const [pinSessions, setPinSessions] = useState(pinSessionsRef.current);
  const [currentChatId, setCurrentChatId] = useState(() => {
    let stored = null;
    try {
      const raw = globalThis.localStorage?.getItem("paperradarChatId");
      const parsed = Number(raw);
      if (Number.isFinite(parsed) && parsed > 0) {
        stored = parsed;
      }
    } catch (_err) {
      /* ignore */
    }
    if (stored && pinSessionsRef.current[stored]) {
      return stored;
    }
    const first = Object.keys(pinSessionsRef.current)[0];
    return first ? Number(first) : null;
  });
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
  const [journalsState, setJournalsState] = useState({ ...DEFAULT_JOURNAL_STATE });
  const [journalNonce, setJournalNonce] = useState(0);
  const [journalIngesting, setJournalIngesting] = useState(false);
  const [journalSortKey, setJournalSortKey] = useState("fit_score");
  const [journalSortDir, setJournalSortDir] = useState("desc");
  const [magicEmail, setMagicEmail] = useState("");
  const [magicLinkData, setMagicLinkData] = useState(null);
  const [magicLinkPending, setMagicLinkPending] = useState(false);
  const [magicLinkHistory, setMagicLinkHistory] = useState([]);
  const [loginChatIdInput, setLoginChatIdInput] = useState("");
  const [loginPinInput, setLoginPinInput] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const isAuthorized = currentChatId != null;
  const effectiveChatId = isAuthorized ? currentChatId : null;
  const [configNonce, setConfigNonce] = useState(0);
  const { toasts, pushToast, dismissToast } = useToasts({ autoDismiss: 6000 });
  const inflightToastRef = useRef(null);
  const profileToastRef = useRef(null);
  const [profilePending, setProfilePending] = useState(false);
  const [editSummary, setEditSummary] = useState("");
  const [editTopics, setEditTopics] = useState([]);
  const [ingestText, setIngestText] = useState("");
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [ingestingProfile, setIngestingProfile] = useState(false);
  const [deletingProfile, setDeletingProfile] = useState(false);
  const [creatingProfile, setCreatingProfile] = useState(false);
  const [newProfileName, setNewProfileName] = useState("");
  const [newProfileText, setNewProfileText] = useState("");
  const fileInputRef = useRef(null);

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
    try {
      if (currentChatId != null && Number.isFinite(currentChatId) && currentChatId > 0) {
        globalThis.localStorage?.setItem("paperradarChatId", String(currentChatId));
      } else {
        globalThis.localStorage?.removeItem("paperradarChatId");
      }
    } catch (_err) {
      /* ignore */
    }
  }, [currentChatId]);

  useEffect(() => {
    if (!isAuthorized) {
      setPapersState((prev) => ({
        ...prev,
        items: [],
        totalRanked: 0,
        offset: 0,
        hasMore: false,
      }));
      setConfigState((prev) => ({ ...prev, data: null }));
      setJournalsState({ ...DEFAULT_JOURNAL_STATE });
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
  }, [currentChatId, isAuthorized, requestPapers, dismissToast]);

  useEffect(() => {
    if (!isAuthorized) return;
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
  }, [currentChatId, isAuthorized, configNonce, dismissToast, pushToast]);

  useEffect(() => {
    const data = configState.data;
    const summary = data?.profile_summary ?? "";
    const topicList = Array.isArray(data?.profile_topics) ? data.profile_topics : [];
    const weightMap = data?.profile_topic_weights || {};
    setEditSummary(summary);
    setEditTopics(normalizeTopicEntries(topicList, weightMap));
    setIngestText("");
  }, [
    configState.data?.profile_summary,
    configState.data?.profile_topics,
    configState.data?.profile_topic_weights,
  ]);

  useEffect(() => {
    if (!isAuthorized) {
      setJournalsState({ ...DEFAULT_JOURNAL_STATE });
      setJournalIngesting(false);
      return;
    }
    const controller = new AbortController();
    setJournalsState((prev) => ({ ...prev, loading: true, error: null }));
    fetchJSON(`/users/${currentChatId}/journals?limit=0`, {
      signal: controller.signal,
    })
      .then((payload) => {
        setJournalsState({
          items: Array.isArray(payload?.items) ? payload.items : [],
          loading: false,
          error: null,
          catalogSize: payload?.catalog_size ?? payload?.catalogSize ?? 0,
          generatedAt: payload?.generated_at ?? payload?.generatedAt ?? null,
          usedEmbeddings: Boolean(payload?.used_embeddings),
        });
      })
      .catch((err) => {
        if (err.name === "AbortError") {
          return;
        }
        const message = err.message || "No se pudieron cargar las revistas.";
        setJournalsState((prev) => ({ ...prev, loading: false, error: message }));
        pushToast({
          tone: "error",
          title: "Revistas",
          message,
        });
      });
    return () => controller.abort();
  }, [currentChatId, isAuthorized, journalNonce, pushToast]);

  useEffect(() => {
    if (!isAuthorized) return;
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
  }, [currentChatId, isAuthorized, limit, page, papersRequest, requestPapers, dismissToast, pushToast]);

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

  const handleJournalSortKeyChange = useCallback((event) => {
    setJournalSortKey(event.target.value);
  }, []);

  const handleJournalSortDirChange = useCallback((event) => {
    setJournalSortDir(event.target.value);
  }, []);

  const handleJournalRefresh = useCallback(async () => {
    if (currentChatId == null) return;
    if (!isAuthorized) {
      pushToast({
        tone: "error",
        title: "Sesion",
        message: "Inicia sesion para actualizar el catalogo.",
      });
      return;
    }
    const nextLimit = 25;
    setJournalIngesting(true);
    try {
      await postJSON(`/users/${currentChatId}/journals/ingest`, { limit: nextLimit });
      setJournalNonce((value) => value + 1);
      pushToast({
        tone: "success",
        title: "Revistas",
        message: "Catalogo actualizado desde Crossref.",
      });
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Revistas",
        message: err.message || "No se pudo actualizar el catalogo.",
      });
    } finally {
      setJournalIngesting(false);
    }
  }, [currentChatId, isAuthorized, pushToast]);

  const handleMagicLinkRequest = useCallback(async () => {
    const email = magicEmail.trim();
    if (!email) {
      pushToast({
        tone: "error",
        title: "Magic link",
        message: "Ingresa un correo valido.",
      });
      return;
    }
    setMagicLinkPending(true);
    try {
      const res = await postJSON("/auth/magic/request", { email });
      setMagicLinkData({
        ...res,
        absoluteUrl: `${globalThis.location?.origin || ""}${res.login_url || ""}`,
      });
      await loadUsers();
      setMagicLinkHistory((prev) => [
        {
          email,
          chat_id: res.chat_id,
          login_url: res.login_url,
          absoluteUrl: `${globalThis.location?.origin || ""}${res.login_url || ""}`,
          pin: res.pin,
          generated_at: new Date().toISOString(),
        },
        ...prev,
      ]);
      pushToast({
        tone: "success",
        title: "Magic link",
        message: "Enlace generado. Copia y comparte el URL.",
      });
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Magic link",
        message: err.message || "No se pudo generar el enlace.",
      });
    } finally {
      setMagicLinkPending(false);
    }
  }, [magicEmail, pushToast, loadUsers]);

  const handleLoginChatChange = useCallback((event) => {
    setLoginChatIdInput(event.target.value);
    setLoginError("");
  }, []);

  const handleLoginPinChange = useCallback((event) => {
    setLoginPinInput(event.target.value);
    setLoginError("");
  }, []);

  const handleLoginSubmit = useCallback(async () => {
    const chatId = Number(loginChatIdInput);
    if (!Number.isFinite(chatId) || chatId <= 0) {
      setLoginError("Ingresa un chat ID valido.");
      return;
    }
    const pin = loginPinInput.trim();
    if (pin.length < 3) {
      setLoginError("Ingresa el PIN recibido.");
      return;
    }
    setLoginLoading(true);
    try {
      await postJSON("/auth/pin/verify", { chat_id: chatId, pin });
      setPinSessions((prev) => {
        const next = { ...prev, [chatId]: true };
        persistPinSessions(next);
        pinSessionsRef.current = next;
        return next;
      });
      setCurrentChatId(chatId);
      setView("papers");
      setLoginChatIdInput("");
      setLoginPinInput("");
      setLoginError("");
      pushToast({
        tone: "success",
        title: "Sesion",
        message: `Acceso concedido al chat ${chatId}.`,
      });
    } catch (err) {
      setLoginError(err.message || "PIN incorrecto.");
    } finally {
      setLoginLoading(false);
    }
  }, [loginChatIdInput, loginPinInput, pushToast]);

  const savedSessions = Object.keys(pinSessions || {}).map((id) => Number(id));

  const handleSavedSessionSelect = useCallback(
    (chatId) => {
      if (!pinSessions[chatId]) return;
      setCurrentChatId(chatId);
      setView("papers");
      pushToast({
        tone: "info",
        title: "Sesion",
        message: `Sesión reanudada en chat ${chatId}.`,
      });
    },
    [pinSessions, pushToast],
  );

  const handleLogoutChat = useCallback(() => {
    if (currentChatId == null) return;
    setPinSessions((prev) => {
      const next = { ...prev };
      delete next[currentChatId];
      persistPinSessions(next);
      pinSessionsRef.current = next;
      return next;
    });
    setCurrentChatId(null);
    setLoginChatIdInput("");
    setLoginPinInput("");
    pushToast({
      tone: "info",
      title: "Sesion",
      message: "Cerraste la sesión actual.",
    });
  }, [currentChatId, pushToast]);

  const handleHistoryRefresh = useCallback(() => {
    if (currentChatId == null) return;
    if (!isAuthorized) {
      pushToast({
        tone: "error",
        title: "Sesion",
        message: "Inicia sesion para refrescar el historial.",
      });
      return;
    }
    pushToast({
      tone: "info",
      title: "Historial",
      message: "Recargando historial del perfil seleccionado.",
    });
    requestPapers("history");
    setConfigNonce((value) => value + 1);
  }, [currentChatId, isAuthorized, pushToast, requestPapers]);

  const handleLiveRefresh = useCallback(() => {
    if (currentChatId == null) return;
    if (!isAuthorized) {
      pushToast({
        tone: "error",
        title: "Sesion",
        message: "Inicia sesion para usar actualizaciones en vivo.",
      });
      return;
    }
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
  }, [currentChatId, isAuthorized, dismissToast, pushToast, requestPapers]);

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
  const canDeleteProfile = availableProfiles.length > 1;

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

  const handleProfileIngest = useCallback(async () => {
    if (!currentChatId) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "Selecciona un usuario primero.",
      });
      return;
    }
    const active = configState.data?.active_profile;
    if (!active) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "No hay un perfil activo para actualizar.",
      });
      return;
    }
    const text = (ingestText || "").trim();
    if (!text) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "Ingresa un abstract antes de procesar.",
      });
      return;
    }
    setIngestingProfile(true);
    const pendingToast = pushToast({
      tone: "info",
      title: "Perfil",
      message: "Procesando abstract...",
      timeout: 0,
    });
    try {
      const payload = { text, profile: active };
      const cfg = await postJSON(`/users/${currentChatId}/profiles/ingest`, payload);
      if (pendingToast) {
        dismissToast(pendingToast);
      }
      setConfigState({ data: cfg, loading: false, error: null });
      setEditSummary(cfg.profile_summary || "");
      setEditTopics(
        normalizeTopicEntries(
          Array.isArray(cfg.profile_topics) ? cfg.profile_topics : [],
          cfg.profile_topic_weights || {},
        ),
      );
      setIngestText("");
      setPage(0);
      requestPapers("history");
      await loadUsers();
      pushToast({
        tone: "success",
        title: "Perfil",
        message: "Perfil actualizado con el abstract.",
      });
    } catch (err) {
      if (pendingToast) {
        dismissToast(pendingToast);
      }
      pushToast({
        tone: "error",
        title: "Perfil",
        message: err.message || "No se pudo procesar el abstract.",
      });
    } finally {
      setIngestingProfile(false);
    }
  }, [
    configState.data?.active_profile,
    currentChatId,
    dismissToast,
    ingestText,
    loadUsers,
    pushToast,
    requestPapers,
  ]);

  const handlePdfUpload = useCallback(async () => {
    if (!currentChatId) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "Selecciona un usuario primero.",
      });
      return;
    }
    const active = configState.data?.active_profile;
    if (!active) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "No hay un perfil activo para actualizar.",
      });
      return;
    }
    const input = fileInputRef.current;
    const file = input?.files?.[0];
    if (!file) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "Selecciona un archivo PDF.",
      });
      return;
    }
    if (file.type !== "application/pdf") {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "Solo se aceptan archivos PDF.",
      });
      return;
    }
    setUploadingPdf(true);
    const pendingToast = pushToast({
      tone: "info",
      title: "Perfil",
      message: "Subiendo PDF...",
      timeout: 0,
    });
    try {
      const form = new FormData();
      form.append("file", file);
      if (active) {
        form.append("profile", active);
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
      if (pendingToast) {
        dismissToast(pendingToast);
      }
      setConfigState({ data: cfg, loading: false, error: null });
      setEditSummary(cfg.profile_summary || "");
      setEditTopics(
        normalizeTopicEntries(
          Array.isArray(cfg.profile_topics) ? cfg.profile_topics : [],
          cfg.profile_topic_weights || {},
        ),
      );
      setIngestText("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setPage(0);
      requestPapers("history");
      await loadUsers();
      pushToast({
        tone: "success",
        title: "Perfil",
        message: "Perfil actualizado desde el PDF.",
      });
    } catch (err) {
      if (pendingToast) {
        dismissToast(pendingToast);
      }
      pushToast({
        tone: "error",
        title: "Perfil",
        message: err.message || "No se pudo procesar el PDF.",
      });
    } finally {
      setUploadingPdf(false);
    }
  }, [
    configState.data?.active_profile,
    currentChatId,
    dismissToast,
    fileInputRef,
    loadUsers,
    pushToast,
    requestPapers,
  ]);

  const handleProfileDelete = useCallback(async () => {
    if (!currentChatId) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "Selecciona un usuario primero.",
      });
      return;
    }
    const active = configState.data?.active_profile;
    if (!active) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "No hay un perfil activo para eliminar.",
      });
      return;
    }
    if (!globalThis.confirm(`Eliminar el perfil "${active}"?`)) {
      return;
    }
    setDeletingProfile(true);
    try {
      const cfg = await fetchJSON(
        `/users/${currentChatId}/profiles/${encodeURIComponent(active)}`,
        { method: "DELETE" },
      );
      setConfigState({ data: cfg, loading: false, error: null });
      setPage(0);
      requestPapers("history");
      await loadUsers();
      pushToast({
        tone: "success",
        title: "Perfil",
        message: "Perfil eliminado.",
      });
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: err.message || "No se pudo eliminar el perfil.",
      });
    } finally {
      setDeletingProfile(false);
    }
  }, [
    configState.data?.active_profile,
    currentChatId,
    loadUsers,
    pushToast,
    requestPapers,
  ]);

  const handleCreateProfile = useCallback(async () => {
    if (!currentChatId) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "Selecciona un usuario primero.",
      });
      return;
    }
    const name = (newProfileName || "").trim();
    const text = (newProfileText || "").trim();
    if (!name) {
      pushToast({
        tone: "error",
        title: "Perfil",
        message: "Ingresa un nombre para el nuevo perfil.",
      });
      return;
    }
    setCreatingProfile(true);
    const pendingToast = pushToast({
      tone: "info",
      title: "Perfil",
      message: "Creando perfil...",
      timeout: 0,
    });
    try {
      const cfg = await postJSON(`/users/${currentChatId}/profiles`, {
        name,
        text,
        set_active: true,
      });
      if (pendingToast) {
        dismissToast(pendingToast);
      }
      setConfigState({ data: cfg, loading: false, error: null });
      setNewProfileName("");
      setNewProfileText("");
      setIngestText("");
      setPage(0);
      requestPapers("history");
      await loadUsers();
      pushToast({
        tone: "success",
        title: "Perfil",
        message: `Perfil "${cfg.active_profile}" creado y activado.`,
      });
    } catch (err) {
      if (pendingToast) {
        dismissToast(pendingToast);
      }
      pushToast({
        tone: "error",
        title: "Perfil",
        message: err.message || "No se pudo crear el perfil.",
      });
    } finally {
      setCreatingProfile(false);
    }
  }, [
    currentChatId,
    dismissToast,
    loadUsers,
    newProfileName,
    newProfileText,
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
        onProfileChange=${handleProfileSelect}
        onViewChange=${setView}
        isAuthorized=${isAuthorized}
        loginChatId=${loginChatIdInput}
        onLoginChatChange=${handleLoginChatChange}
        loginPin=${loginPinInput}
        onLoginPinChange=${handleLoginPinChange}
        onLoginSubmit=${handleLoginSubmit}
        loginError=${loginError}
        loginLoading=${loginLoading}
        savedSessions=${savedSessions}
        onSavedSessionSelect=${handleSavedSessionSelect}
        onLogoutChat=${handleLogoutChat}
      />
      <main className="content">
        <${PapersView}
          chatId=${effectiveChatId}
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
        <${JournalsView}
          chatId=${effectiveChatId}
          view=${view}
          state=${journalsState}
          sortKey=${journalSortKey}
          sortDir=${journalSortDir}
          onSortKeyChange=${handleJournalSortKeyChange}
          onSortDirChange=${handleJournalSortDirChange}
          onRefresh=${handleJournalRefresh}
          ingesting=${journalIngesting}
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
          ingestText=${ingestText}
          onIngestTextChange=${(event) => setIngestText(event.target.value)}
          onIngestSubmit=${handleProfileIngest}
          ingestingText=${ingestingProfile}
          pdfInputRef=${fileInputRef}
          onPdfUpload=${handlePdfUpload}
          uploadingPdf=${uploadingPdf}
          onDeleteProfile=${handleProfileDelete}
          deletingProfile=${deletingProfile}
          canDeleteProfile=${canDeleteProfile}
          newProfileName=${newProfileName}
          onNewProfileNameChange=${(event) => setNewProfileName(event.target.value)}
          newProfileText=${newProfileText}
          onNewProfileTextChange=${(event) => setNewProfileText(event.target.value)}
          onCreateProfile=${handleCreateProfile}
          creatingProfile=${creatingProfile}
          magicEmail=${magicEmail}
          onMagicEmailChange=${(event) => setMagicEmail(event.target.value)}
          magicLinkData=${magicLinkData}
          magicLinkLoading=${magicLinkPending}
          onMagicLinkRequest=${handleMagicLinkRequest}
          chatId=${effectiveChatId}
          magicLinkHistory=${magicLinkHistory}
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


