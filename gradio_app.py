"""
MERIDIAN Gradio UI — Redesigned

Chat-based interface for querying business data using natural language.
Dark-first design with meridian-arc branding, command-palette search,
and modern data navigation experience.
"""

import atexit
import glob
import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional
import pandas as pd
import gradio as gr
import plotly.express as px
import plotly.graph_objects as go

from app.config import settings
from app.views.registry import get_registry
from app.database.connection import get_db
from app.agents.orchestrator import Orchestrator
from app.ui.helpers import (
    CHART_HEIGHT as _CHART_HEIGHT,
    build_empty_chart,
    build_plotly_figure,
    thinking_label_dict as _thinking_label_dict,
    pick_suggestion as _pick_suggestion_impl,
)

logging.basicConfig(level=logging.WARNING)
logging.getLogger("app").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

_TEMP_PREFIX = "meridian_results_"


def _cleanup_temp_files() -> None:
    """Remove leftover MERIDIAN temp files (CSV / JSON / Excel) from the system temp dir."""
    pattern = os.path.join(tempfile.gettempdir(), f"{_TEMP_PREFIX}*")
    for path in glob.glob(pattern):
        try:
            os.unlink(path)
        except OSError:
            pass


# Remove any temp files left over from previous runs, and register cleanup on exit.
_cleanup_temp_files()
atexit.register(_cleanup_temp_files)

# Initialize orchestrator once at startup
registry = get_registry()
db = get_db(connection_string=settings.database_url)
orchestrator = Orchestrator(registry, db)

SAMPLE_QUERIES = [
    "How many sales were made in the WEST region?",
    "What was the total sales amount by customer?",
    "Show me all ledger transactions",
    "What is the inventory in each warehouse?",
]

MAX_SUGGESTIONS = 3


def format_result_as_table(result: list) -> pd.DataFrame:
    """Convert a list-of-dicts query result into a DataFrame."""
    if not result:
        return pd.DataFrame({"Info": ["No results found."]})
    return pd.DataFrame(result)


# ---------------------------------------------------------------------------
# SVG icon library (monochrome, 16x16, uses currentColor for theme compat)
# ---------------------------------------------------------------------------

_ICON_DOMAIN = (
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<rect x="1" y="1" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>'
    '<rect x="9" y="1" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>'
    '<rect x="1" y="9" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>'
    '<rect x="9" y="9" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/>'
    '</svg>'
)

_ICON_TARGET = (
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/>'
    '<circle cx="8" cy="8" r="3" stroke="currentColor" stroke-width="1.5"/>'
    '<circle cx="8" cy="8" r="1" fill="currentColor"/>'
    '</svg>'
)

_ICON_CHECK = (
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.5"/>'
    '<path d="M5 8.5L7 10.5L11 6" stroke="currentColor" stroke-width="1.5" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)

_ICON_ROWS = (
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<rect x="1.5" y="2" width="13" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>'
    '<line x1="1.5" y1="6" x2="14.5" y2="6" stroke="currentColor" stroke-width="1.5"/>'
    '<line x1="1.5" y1="10" x2="14.5" y2="10" stroke="currentColor" stroke-width="1.5"/>'
    '</svg>'
)

_ICON_VIEW = (
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<path d="M1 8C1 8 4 3 8 3C12 3 15 8 15 8C15 8 12 13 8 13C4 13 1 8 1 8Z" '
    'stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
    '<circle cx="8" cy="8" r="2.5" stroke="currentColor" stroke-width="1.5"/>'
    '</svg>'
)


def build_metadata_html(result: dict, show_sql: bool) -> str:
    """Build styled HTML metadata bar with SVG icons."""
    domain = result.get("domain", "unknown").capitalize()
    routing_conf = result.get("routing_confidence", 0) or 0
    confidence = result.get("confidence", 0) or 0
    row_count = result.get("row_count", 0) or 0
    views_list = result.get("views") or []
    views = ", ".join(views_list) if views_list else "\u2014"

    html = f"""
    <div class="meta-bar">
      <span class="meta-chip meta-domain" title="Domain that handled this query">
        {_ICON_DOMAIN} {domain}
      </span>
      <span class="meta-chip meta-routing" title="Router confidence">
        {_ICON_TARGET} Routing {routing_conf:.0%}
      </span>
      <span class="meta-chip meta-accuracy" title="Answer confidence">
        {_ICON_CHECK} Accuracy {confidence:.0%}
      </span>
      <span class="meta-chip meta-rows">
        {_ICON_ROWS} {row_count} row{"s" if row_count != 1 else ""}
      </span>
      <span class="meta-chip meta-views" title="Views accessed">
        {_ICON_VIEW} {views}
      </span>
    </div>
    """
    if show_sql and result.get("sql"):
        import html as html_lib
        safe_sql = html_lib.escape(result["sql"])
        html += f"""
    <details class="sql-details">
      <summary>View generated SQL</summary>
      <pre><code>{safe_sql}</code></pre>
    </details>
    """
    return html


def process_query(
    question: str,
    domain_choice: str,
    show_sql: bool,
    show_explain: bool = False,
    conversation_id: Optional[str] = None,
):
    """
    Process a natural language query and return tabular results + metadata.

    Forced-domain selection is routed through the orchestrator's ``forced_domain``
    parameter so conversation context and history are always maintained.

    Returns:
        Tuple of (DataFrame, error_html, metadata_html, csv_file_path,
                  suggestions_list, conversation_id, explain_data, visualization)
    """
    empty_df = pd.DataFrame()
    no_explain: Dict[str, Any] = {}
    no_viz: Dict[str, Any] = {}

    if not question.strip():
        return empty_df, "", "", None, [], conversation_id, no_explain, no_viz

    try:
        forced = None if domain_choice == "Auto-detect" else domain_choice.lower()
        result = orchestrator.process_query(
            question,
            conversation_id=conversation_id,
            forced_domain=forced,
        )

        new_conv_id = result.get("conversation_id", conversation_id)

        if "error" in result and result["error"]:
            error_html = f'<div class="error-alert">{result["error"]}</div>'
            return empty_df, error_html, "", None, [], new_conv_id, no_explain, no_viz

        raw_results = result.get("result", [])
        df = format_result_as_table(raw_results)
        metadata_html = build_metadata_html(result, show_sql)
        suggestions: List[str] = result.get("suggestions") or []
        visualization: Dict[str, Any] = result.get("visualization") or {}

        csv_path = None
        if raw_results:
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=".csv", prefix=_TEMP_PREFIX
            )
            df.to_csv(tmp.name, index=False)
            csv_path = tmp.name

        # Build explain data when requested
        explain_data: Dict[str, Any] = {}
        if show_explain:
            try:
                from app.explain.builder import build_explain_response
                explain_resp = build_explain_response(question, result)
                explain_data = explain_resp.model_dump()
            except Exception as ex:
                logger.warning(f"Explain generation failed: {ex}")

        return df, "", metadata_html, csv_path, suggestions, new_conv_id, explain_data, visualization

    except Exception as e:
        logger.error(f"UI query failed: {e}", exc_info=True)
        error_html = (
            f'<div class="error-alert">'
            f'An unexpected error occurred: <strong>{str(e)}</strong>. '
            f'Try rephrasing your question.'
            f'</div>'
        )
        return empty_df, error_html, "", None, [], conversation_id, no_explain, no_viz


def export_results_as_json(raw_rows: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Write raw_rows to a temp JSON file and return the path."""
    if not raw_rows:
        return None
    try:
        from app.export.exporters import to_json
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", prefix=_TEMP_PREFIX)
        tmp.write(to_json(raw_rows))
        tmp.flush()
        return tmp.name
    except Exception as e:
        logger.error(f"JSON export failed: {e}")
        return None


def export_results_as_excel(raw_rows: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Write raw_rows to a temp Excel file and return the path."""
    if not raw_rows:
        return None
    try:
        from app.export.exporters import to_excel
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx", prefix=_TEMP_PREFIX)
        tmp.write(to_excel(raw_rows))
        tmp.flush()
        return tmp.name
    except Exception as e:
        logger.error(f"Excel export failed: {e}")
        return None


# ---------------------------------------------------------------------------
# UI Assets
# ---------------------------------------------------------------------------

FAVICON_PATH = "assets/favicon.svg"

LOGO_SVG = """
<svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg"
     style="width:32px;height:32px;vertical-align:middle">
  <!-- Globe outline -->
  <circle cx="20" cy="20" r="17" stroke="#0d9488" stroke-width="1.5" fill="none" opacity="0.6"/>
  <!-- Meridian arc -->
  <ellipse cx="20" cy="20" rx="8" ry="17" stroke="#0d9488" stroke-width="2" fill="none"/>
  <!-- Equator line -->
  <ellipse cx="20" cy="20" rx="17" ry="6" stroke="#0d9488" stroke-width="1" fill="none" opacity="0.3"/>
  <!-- Gold intersection point -->
  <circle cx="20" cy="20" r="2.5" fill="#f59e0b"/>
  <!-- North pole tick -->
  <line x1="20" y1="1" x2="20" y2="5" stroke="#0d9488" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
</svg>
"""

HEADER_HTML = f"""
<div class="meridian-topbar">
  <div class="topbar-brand">
    {LOGO_SVG}
    <span class="topbar-wordmark">MERIDIAN</span>
    <span class="topbar-tagline">Intelligent Data Navigation</span>
  </div>
  <div class="topbar-actions">
    <span class="topbar-shortcut" title="Focus search (⌘/ on Mac, Ctrl+/ on Windows/Linux)">⌘/ · Ctrl+/</span>
  </div>
</div>
"""

EMPTY_STATE_HTML = """
<div class="empty-state">
  <div class="empty-visual">
    <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg" style="width:100px;height:100px">
      <!-- Outer globe -->
      <circle cx="60" cy="60" r="50" stroke="#0d9488" stroke-width="1.5" fill="none" opacity="0.3"/>
      <!-- Meridian arcs -->
      <ellipse cx="60" cy="60" rx="22" ry="50" stroke="#0d9488" stroke-width="1.5" fill="none" opacity="0.5"/>
      <ellipse cx="60" cy="60" rx="38" ry="50" stroke="#0d9488" stroke-width="1" fill="none" opacity="0.2"/>
      <!-- Equator lines -->
      <ellipse cx="60" cy="60" rx="50" ry="18" stroke="#0d9488" stroke-width="1" fill="none" opacity="0.25"/>
      <ellipse cx="60" cy="60" rx="50" ry="35" stroke="#0d9488" stroke-width="0.75" fill="none" opacity="0.15"/>
      <!-- Data points along meridian -->
      <circle cx="60" cy="12" r="3" fill="#0d9488" opacity="0.7"/>
      <circle cx="38" cy="30" r="2.5" fill="#f59e0b" opacity="0.6"/>
      <circle cx="82" cy="45" r="2" fill="#6366f1" opacity="0.5"/>
      <circle cx="60" cy="60" r="4" fill="#f59e0b"/>
      <circle cx="42" cy="85" r="2.5" fill="#10b981" opacity="0.6"/>
      <circle cx="75" cy="95" r="2" fill="#0d9488" opacity="0.5"/>
      <!-- Pulse ring -->
      <circle cx="60" cy="60" r="8" stroke="#f59e0b" stroke-width="1" fill="none" opacity="0.3">
        <animate attributeName="r" values="8;16;8" dur="3s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.3;0;0.3" dur="3s" repeatCount="indefinite"/>
      </circle>
    </svg>
  </div>
  <h2 class="empty-title">Where does your data lead?</h2>
  <p class="empty-subtitle">Ask a question in plain English. MERIDIAN navigates your databases and returns answers.</p>
</div>
"""

# Plain JS — injected via gr.Blocks(js=...) which runs after the UI loads.
# Using the js= parameter is more reliable than gr.HTML(<script>), which
# Gradio may sanitise away depending on its security settings.
KEYBOARD_JS = """
document.addEventListener('keydown', function(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        var ta = document.querySelector('#meridian-search textarea');
        if (ta) { ta.focus(); ta.select(); }
    }
});
"""

# ---------------------------------------------------------------------------
# CSS — Dark-first Meridian design system
# ---------------------------------------------------------------------------

MERIDIAN_CSS = """
/* ── Google Fonts ───────────────────────────────────────── */
/* @import must precede all other rules (CSS spec §6.3).    */
/* Falls back to system-ui / monospace if CDN unavailable.  */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── CSS Variables ──────────────────────────────────────── */
:root {
    --m-navy:       #0B1120;
    --m-navy-light: #131c31;
    --m-surface:    #1E293B;
    --m-surface-2:  #273549;
    --m-border:     #334155;
    --m-border-light: #475569;
    --m-teal:       #0d9488;
    --m-teal-dim:   #0f766e;
    --m-teal-glow:  rgba(13,148,136,0.15);
    --m-gold:       #f59e0b;
    --m-gold-dim:   rgba(245,158,11,0.15);
    --m-red:        #ef4444;
    --m-green:      #10b981;
    --m-text:       #e2e8f0;
    --m-text-2:     #94a3b8;
    --m-text-3:     #64748b;
    --m-font:       'Inter', system-ui, -apple-system, sans-serif;
    --m-font-mono:  'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
    --m-radius:     10px;
    --m-radius-lg:  14px;
    --m-transition: 180ms cubic-bezier(0.4, 0, 0.2, 1);
}

/* ── Base overrides ─────────────────────────────────────── */
body, .gradio-container {
    background: var(--m-navy) !important;
    color: var(--m-text) !important;
    font-family: var(--m-font) !important;
}
.gradio-container { min-height: 100vh; max-width: 1400px !important; }
.main > .contain { height: auto !important; min-height: 100vh; }

/* Remove default Gradio chrome */
.gradio-container .prose { color: var(--m-text-2) !important; }
footer { display: none !important; }
.gr-button { font-family: var(--m-font) !important; }

/* ── Panel / block backgrounds ──────────────────────────── */
.gr-panel, .gr-box, .gr-form, .gr-block,
div[class*="block"] {
    background: transparent !important;
    border: none !important;
}

/* ── Top bar ────────────────────────────────────────────── */
.meridian-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 4px;
    border-bottom: 1px solid var(--m-border);
    margin-bottom: 12px;
}
.topbar-brand {
    display: flex;
    align-items: center;
    gap: 10px;
}
.topbar-wordmark {
    font-family: 'Plus Jakarta Sans', var(--m-font);
    font-size: 1.4em;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: var(--m-teal);
}
.topbar-tagline {
    font-size: 0.78em;
    color: var(--m-text-3);
    border-left: 1px solid var(--m-border);
    padding-left: 10px;
    margin-left: 2px;
}
.topbar-actions {
    display: flex;
    align-items: center;
    gap: 8px;
}
.topbar-shortcut {
    font-size: 0.72em;
    color: var(--m-text-3);
    background: var(--m-surface);
    border: 1px solid var(--m-border);
    border-radius: 6px;
    padding: 3px 8px;
    font-family: var(--m-font-mono);
}

/* ── Search bar (hero element) ──────────────────────────── */
.search-row {
    margin-bottom: 8px !important;
}
.search-row .gr-textbox,
.search-row textarea {
    background: var(--m-surface) !important;
    border: 1.5px solid var(--m-border) !important;
    border-left: 3px solid var(--m-teal) !important;
    border-radius: var(--m-radius) !important;
    color: var(--m-text) !important;
    font-size: 0.95em !important;
    font-family: var(--m-font) !important;
    padding: 14px 16px !important;
    transition: border-color var(--m-transition), box-shadow var(--m-transition) !important;
    min-height: 52px !important;
}
.search-row textarea:focus {
    border-color: var(--m-teal) !important;
    box-shadow: 0 0 0 3px var(--m-teal-glow), inset 0 1px 2px rgba(0,0,0,0.2) !important;
    outline: none !important;
}
.search-row textarea::placeholder {
    color: var(--m-text-3) !important;
}
.search-row label span {
    color: var(--m-text-2) !important;
    font-weight: 500 !important;
    font-size: 0.82em !important;
    letter-spacing: 0.02em !important;
}

/* ── Primary button ─────────────────────────────────────── */
.meridian-submit {
    background: linear-gradient(135deg, var(--m-teal) 0%, var(--m-teal-dim) 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: var(--m-radius) !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    padding: 12px 28px !important;
    min-height: 52px !important;
    transition: all var(--m-transition) !important;
    box-shadow: 0 2px 8px rgba(13,148,136,0.25) !important;
}
.meridian-submit:hover {
    filter: brightness(1.1) !important;
    box-shadow: 0 4px 16px rgba(13,148,136,0.35) !important;
    transform: translateY(-1px) !important;
}
.meridian-submit:active {
    transform: translateY(0) !important;
}

/* ── Secondary / ghost buttons ──────────────────────────── */
.meridian-ghost {
    background: transparent !important;
    color: var(--m-text-3) !important;
    border: 1px solid var(--m-border) !important;
    border-radius: var(--m-radius) !important;
    min-height: 52px !important;
    transition: all var(--m-transition) !important;
}
.meridian-ghost:hover {
    color: var(--m-text-2) !important;
    border-color: var(--m-border-light) !important;
    background: var(--m-surface) !important;
}

/* ── Left rail ──────────────────────────────────────────── */
.left-rail {
    background: var(--m-navy-light) !important;
    border-right: 1px solid var(--m-border) !important;
    border-radius: var(--m-radius-lg) !important;
    padding: 12px !important;
    min-width: 200px;
}

/* ── Domain nav ─────────────────────────────────────────── */
#domain-nav {
    border: none !important;
    background: none !important;
}
#domain-nav .gr-radio-row,
#domain-nav input[type="radio"] {
    display: none !important;
}
#domain-nav label,
#domain-nav .gr-radio-label {
    display: flex !important;
    align-items: center !important;
    padding: 9px 12px !important;
    border: 1px solid transparent !important;
    border-radius: 8px !important;
    margin-bottom: 3px !important;
    cursor: pointer !important;
    transition: all var(--m-transition) !important;
    background: transparent !important;
    color: var(--m-text-2) !important;
    font-size: 0.85em !important;
    line-height: 1.4 !important;
}
#domain-nav label:hover {
    background: var(--m-surface) !important;
    color: var(--m-text) !important;
}
#domain-nav label:has(input[type="radio"]:checked) {
    background: var(--m-teal-glow) !important;
    border-color: var(--m-teal) !important;
    color: var(--m-teal) !important;
}
#domain-nav label:has(input[type="radio"]:checked) span {
    color: var(--m-teal) !important;
    font-weight: 600 !important;
}

/* ── Accordion ──────────────────────────────────────────── */
.gr-accordion {
    border: none !important;
    background: transparent !important;
}
.gr-accordion > .label-wrap {
    color: var(--m-text-3) !important;
    font-size: 0.78em !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
    padding: 8px 4px !important;
    border-bottom: 1px solid var(--m-border) !important;
}

/* ── Checkboxes ─────────────────────────────────────────── */
.gr-checkbox label {
    color: var(--m-text-2) !important;
    font-size: 0.85em !important;
}
.gr-checkbox input[type="checkbox"] {
    accent-color: var(--m-teal) !important;
}
.gr-checkbox .gr-check {
    border-color: var(--m-border) !important;
}

/* ── Main stage ─────────────────────────────────────────── */
.main-stage {
    padding: 0 0 0 16px !important;
}

/* ── Error alert ────────────────────────────────────────── */
.error-alert {
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.25);
    border-left: 3px solid var(--m-red);
    border-radius: var(--m-radius);
    padding: 12px 16px;
    color: #fca5a5;
    font-size: 0.9em;
    margin: 8px 0;
    animation: slideDown 0.2s ease-out;
}

/* ── Metadata bar ───────────────────────────────────────── */
.meta-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 10px 0 6px;
    animation: fadeIn 0.3s ease-out;
}
.meta-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: 999px;
    font-size: 0.78em;
    font-weight: 500;
    white-space: nowrap;
    border: 1px solid var(--m-border);
    transition: all var(--m-transition);
}
.meta-chip svg { flex-shrink: 0; }
.meta-domain  { color: var(--m-teal); border-color: rgba(13,148,136,0.3); background: rgba(13,148,136,0.08); }
.meta-routing { color: #818cf8; border-color: rgba(129,140,248,0.3); background: rgba(129,140,248,0.08); }
.meta-accuracy { color: var(--m-green); border-color: rgba(16,185,129,0.3); background: rgba(16,185,129,0.08); }
.meta-rows    { color: var(--m-gold); border-color: rgba(245,158,11,0.3); background: rgba(245,158,11,0.08); }
.meta-views   { color: var(--m-text-3); border-color: var(--m-border); background: var(--m-surface); }

/* ── SQL details ────────────────────────────────────────── */
.sql-details {
    margin-top: 8px;
    font-size: 0.85em;
}
.sql-details summary {
    cursor: pointer;
    color: var(--m-text-3);
    font-weight: 500;
    padding: 6px 0;
    user-select: none;
    transition: color var(--m-transition);
}
.sql-details summary:hover { color: var(--m-text-2); }
.sql-details pre {
    background: var(--m-navy);
    border: 1px solid var(--m-border);
    color: var(--m-text);
    border-radius: var(--m-radius);
    padding: 12px 16px;
    overflow-x: auto;
    margin-top: 6px;
    font-size: 0.88em;
}
.sql-details code { font-family: var(--m-font-mono); }

/* ── Welcome card ───────────────────────────────────────── */
.welcome-card {
    border: 1px solid var(--m-border) !important;
    border-radius: var(--m-radius-lg) !important;
    background: linear-gradient(180deg, var(--m-surface) 0%, var(--m-navy-light) 100%) !important;
    padding: 8px 20px 20px !important;
    margin-top: 8px !important;
}

/* ── Empty state ────────────────────────────────────────── */
.empty-state {
    text-align: center;
    padding: 36px 24px 16px;
}
.empty-visual {
    margin-bottom: 16px;
    opacity: 0.9;
}
.empty-title {
    font-family: 'Plus Jakarta Sans', var(--m-font);
    font-size: 1.2em;
    font-weight: 700;
    color: var(--m-text);
    margin: 0 0 6px;
}
.empty-subtitle {
    font-size: 0.88em;
    color: var(--m-text-3);
    margin: 0;
    max-width: 420px;
    margin-left: auto;
    margin-right: auto;
}

/* ── Quick-start label ──────────────────────────────────── */
.quickstart-label {
    font-size: 0.75em;
    font-weight: 600;
    color: var(--m-text-3);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 4px 0 6px !important;
    padding: 0 !important;
}

/* ── Sample query buttons ───────────────────────────────── */
.welcome-card .gr-button,
.welcome-card button {
    background: var(--m-navy) !important;
    color: var(--m-text-2) !important;
    border: 1px solid var(--m-border) !important;
    border-radius: 8px !important;
    font-size: 0.82em !important;
    padding: 8px 14px !important;
    text-align: left !important;
    transition: all var(--m-transition) !important;
    line-height: 1.3 !important;
}
.welcome-card .gr-button:hover,
.welcome-card button:hover {
    border-color: var(--m-teal) !important;
    background: var(--m-teal-glow) !important;
    color: var(--m-text) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(13,148,136,0.15) !important;
}

/* ── Results table ──────────────────────────────────────── */
.dataframe {
    border-radius: var(--m-radius-lg) !important;
    overflow: hidden !important;
    border: 1px solid var(--m-border) !important;
}
.dataframe table {
    border-collapse: separate !important;
    border-spacing: 0 !important;
    width: 100% !important;
}
.dataframe thead th {
    background: var(--m-surface) !important;
    color: var(--m-text-2) !important;
    font-weight: 600 !important;
    font-size: 0.78em !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    padding: 11px 16px !important;
    border-bottom: 2px solid var(--m-border) !important;
    white-space: nowrap !important;
    position: sticky;
    top: 0;
    z-index: 1;
}
.dataframe tbody td {
    padding: 10px 16px !important;
    font-size: 0.88em !important;
    color: var(--m-text) !important;
    border-bottom: 1px solid rgba(51,65,85,0.5) !important;
    background: var(--m-navy) !important;
}
.dataframe tbody tr:nth-child(even) td {
    background: var(--m-navy-light) !important;
}
.dataframe tbody tr:hover td {
    background: var(--m-teal-glow) !important;
    transition: background var(--m-transition) !important;
}

/* ── Tabs ───────────────────────────────────────────────── */
.gr-tabs {
    border: none !important;
    background: transparent !important;
}
.gr-tab-nav {
    border-bottom: 1px solid var(--m-border) !important;
    background: transparent !important;
    gap: 0 !important;
}
.gr-tab-nav button {
    background: transparent !important;
    color: var(--m-text-3) !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    padding: 10px 18px !important;
    font-size: 0.82em !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    transition: all var(--m-transition) !important;
}
.gr-tab-nav button:hover {
    color: var(--m-text) !important;
}
.gr-tab-nav button.selected {
    color: var(--m-teal) !important;
    border-bottom-color: var(--m-teal) !important;
    font-weight: 600 !important;
}

/* ── Suggestion chips ───────────────────────────────────── */
.suggestions-row .gr-button,
.suggestions-row button {
    background: var(--m-surface) !important;
    color: var(--m-text-2) !important;
    border: 1px solid var(--m-border) !important;
    border-radius: 999px !important;
    font-size: 0.8em !important;
    padding: 6px 16px !important;
    transition: all var(--m-transition) !important;
}
.suggestions-row .gr-button:hover,
.suggestions-row button:hover {
    border-color: var(--m-teal) !important;
    color: var(--m-teal) !important;
    background: var(--m-teal-glow) !important;
}
.suggestions-label p {
    font-size: 0.75em !important;
    font-weight: 600 !important;
    color: var(--m-text-3) !important;
    margin: 4px 0 2px !important;
}

/* ── Export toolbar ──────────────────────────────────────── */
.export-row {
    flex-wrap: wrap !important;
    gap: 8px 12px !important;
    align-items: flex-start !important;
    padding-top: 10px !important;
    border-top: 1px solid var(--m-border) !important;
    margin-top: 4px !important;
}
.export-row > div {
    flex-shrink: 0 !important;
    min-width: 0 !important;
}
.export-row .gr-button,
.export-row button {
    background: transparent !important;
    color: var(--m-text-3) !important;
    border: 1px solid var(--m-border) !important;
    border-radius: 8px !important;
    font-size: 0.78em !important;
    padding: 6px 14px !important;
    transition: all var(--m-transition) !important;
    white-space: nowrap !important;
}
.export-row .gr-button:hover,
.export-row button:hover {
    color: var(--m-text-2) !important;
    border-color: var(--m-border-light) !important;
    background: var(--m-surface) !important;
}
/* File chips in export row */
.export-row .file-preview {
    background: var(--m-surface) !important;
    border: 1px solid var(--m-border) !important;
    border-radius: 8px !important;
    padding: 4px 10px !important;
    font-size: 0.78em !important;
    color: var(--m-text-2) !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    max-width: 200px !important;
}
@media (max-width: 1280px) {
    .export-row .file-preview { max-width: 160px !important; }
}

/* ── File download ──────────────────────────────────────── */
.gr-file {
    background: var(--m-surface) !important;
    border: 1px dashed var(--m-border) !important;
    border-radius: var(--m-radius) !important;
}
.gr-file .file-name {
    color: var(--m-text) !important;
}

/* ── JSON display ───────────────────────────────────────── */
.gr-json {
    background: var(--m-navy) !important;
    border: 1px solid var(--m-border) !important;
    border-radius: var(--m-radius) !important;
    color: var(--m-text) !important;
    font-family: var(--m-font-mono) !important;
}

/* ── Plot area ──────────────────────────────────────────── */
.gr-plot {
    background: var(--m-surface) !important;
    border: 1px solid var(--m-border) !important;
    border-radius: var(--m-radius-lg) !important;
    overflow: hidden !important;
}

/* ── History panel ──────────────────────────────────────── */
.history-table .dataframe thead th {
    background: transparent !important;
    font-size: 0.72em !important;
    padding: 6px 8px !important;
    border-bottom: 1px solid var(--m-border) !important;
}
.history-table .dataframe tbody td {
    padding: 7px 8px !important;
    font-size: 0.82em !important;
    color: var(--m-text-3) !important;
    background: transparent !important;
    cursor: pointer;
}
.history-table .dataframe tbody tr:hover td {
    color: var(--m-text) !important;
    background: var(--m-teal-glow) !important;
}

/* ── Scrollbar ──────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--m-border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--m-border-light); }

/* ── Animations ─────────────────────────────────────────── */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes slideDown {
    from { opacity: 0; transform: translateY(-8px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes shimmer {
    0%   { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
.loading-shimmer {
    background: linear-gradient(90deg, var(--m-surface) 25%, var(--m-surface-2) 50%, var(--m-surface) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.8s ease-in-out infinite;
    border-radius: var(--m-radius);
    height: 48px;
}

/* ── Responsive ─────────────────────────────────────────── */
@media (max-width: 768px) {
    .left-rail { display: none !important; }
    .topbar-tagline { display: none !important; }
    .meta-bar { gap: 4px; }
    .meta-chip { font-size: 0.72em; padding: 4px 8px; }
}
"""


# ---------------------------------------------------------------------------
# Module-level UI helpers (pure functions — no closure dependencies)
# ---------------------------------------------------------------------------

def _thinking_label(explain_on: bool) -> dict:
    """Return a gr.update-compatible dict for the submit button loading state.

    Delegates to app.ui.helpers.thinking_label_dict for the pure logic;
    the returned dict is accepted by Gradio wherever gr.update() is expected.
    Label is context-aware: "Analysing…" (Explain on) vs "Thinking…".
    """
    return _thinking_label_dict(explain_on)


def _pick_suggestion(idx: int, sugg: list, explain_on: bool = False):
    """Populate the question box from the suggestion list by index."""
    return _pick_suggestion_impl(idx, sugg, explain_on)


# ---------------------------------------------------------------------------
# UI Layout
# ---------------------------------------------------------------------------

def build_ui() -> gr.Blocks:
    """Build the Gradio Blocks UI with Meridian design system."""

    theme = gr.themes.Base(
        primary_hue=gr.themes.colors.teal,
        secondary_hue=gr.themes.colors.slate,
        neutral_hue=gr.themes.colors.slate,
        font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
    )

    with gr.Blocks(
        title="MERIDIAN \u2014 Intelligent Data Navigation",
        theme=theme,
        css=MERIDIAN_CSS,
        js=KEYBOARD_JS,
    ) as app:

        # ── Top bar ─────────────────────────────────────────────────
        gr.HTML(HEADER_HTML)

        # ── Search bar (full width, command-palette style) ──────────
        with gr.Row(elem_classes=["search-row"]):
            question = gr.Textbox(
                label="Navigate your data",
                placeholder="Ask a question... e.g. How many sales were made in the WEST region?",
                lines=1,
                max_lines=3,
                elem_id="meridian-search",
                scale=5,
            )
            submit_btn = gr.Button(
                "Ask",
                variant="primary",
                scale=1,
                elem_classes=["meridian-submit"],
            )
            clear_btn = gr.Button(
                "Clear",
                scale=1,
                elem_classes=["meridian-ghost"],
            )

        # ── Follow-up suggestions (below search, full width) ───────
        with gr.Group(visible=False, elem_classes=["suggestions-row"]) as suggestions_group:
            gr.Markdown("Follow up:", elem_classes=["suggestions-label"])
            with gr.Row():
                sugg_btn_0 = gr.Button("", size="sm", visible=False)
                sugg_btn_1 = gr.Button("", size="sm", visible=False)
                sugg_btn_2 = gr.Button("", size="sm", visible=False)

        # ── Main layout: left rail + main stage ─────────────────────
        with gr.Row():

            # ── Left rail ───────────────────────────────────────────
            with gr.Column(scale=1, elem_classes=["left-rail"], min_width=200):
                domain_choice = gr.Radio(
                    choices=[
                        ("Auto-detect", "Auto-detect"),
                        ("Sales", "Sales"),
                        ("Finance", "Finance"),
                        ("Operations", "Operations"),
                    ],
                    value="Auto-detect",
                    label="Domain",
                    elem_id="domain-nav",
                )

                with gr.Accordion("Advanced Options", open=False):
                    show_sql = gr.Checkbox(
                        label="Show SQL",
                        value=False,
                        info="Reveal the generated SQL query.",
                    )
                    show_explain = gr.Checkbox(
                        label="Explain mode",
                        value=False,
                        info="Show routing decisions and query details. Adds ~30–60 s per query (LLM analysis).",
                    )

                with gr.Accordion("Recent", open=True):
                    history_display = gr.Dataframe(
                        headers=["Recent Queries"],
                        datatype=["str"],
                        interactive=False,
                        wrap=True,
                        label="",
                        elem_classes=["history-table"],
                    )

            # ── Main stage ──────────────────────────────────────────
            with gr.Column(scale=4, elem_classes=["main-stage"]):

                error_box = gr.HTML(value="")
                metadata = gr.HTML(value="")

                # Welcome state
                with gr.Group(visible=True, elem_classes=["welcome-card"]) as welcome_group:
                    gr.HTML(value=EMPTY_STATE_HTML)
                    gr.HTML('<p class="quickstart-label">Try an example:</p>')
                    with gr.Row():
                        sample_btns = [gr.Button(q, size="sm") for q in SAMPLE_QUERIES]

                # Results area with tabs
                with gr.Tabs(visible=False) as results_tabs:
                    with gr.TabItem("Table"):
                        results_table = gr.Dataframe(
                            label="",
                            interactive=False,
                            wrap=True,
                        )
                    with gr.TabItem("Chart"):
                        results_plot = gr.Plot(label="")
                    with gr.TabItem("Explain"):
                        explain_panel = gr.JSON(label="")

                # Export toolbar
                with gr.Row(elem_classes=["export-row"]):
                    export_json_btn = gr.Button("Export JSON", size="sm", visible=False)
                    export_excel_btn = gr.Button("Export Excel", size="sm", visible=False)
                    download_file = gr.File(label="CSV", visible=False)
                    download_json = gr.File(label="JSON", visible=False)
                    download_excel = gr.File(label="Excel", visible=False)

        # ── Persistent state ────────────────────────────────────────
        history_state = gr.State([])
        conversation_state = gr.State(None)
        suggestions_state = gr.State([])
        raw_rows_state = gr.State([])

        # ── Helpers ─────────────────────────────────────────────────

        MAX_HISTORY = 10

        def build_history_data(history: list) -> list:
            if not history:
                return []
            return [[q] for q in reversed(history)]

        def run_query(question_val, domain_val, show_sql_val, show_explain_val, history_val, conv_id):
            if not question_val or not question_val.strip():
                return (
                    gr.update(),                                         # results_table
                    gr.update(),                                         # results_plot
                    "",                                                  # error_box
                    gr.update(),                                         # welcome_group
                    "",                                                  # metadata
                    gr.update(),                                         # download_file
                    gr.update(),                                         # download_json
                    gr.update(),                                         # download_excel
                    gr.update(),                                         # explain_panel
                    gr.update(),                                         # suggestions_group
                    gr.update(),                                         # sugg_btn_0
                    gr.update(),                                         # sugg_btn_1
                    gr.update(),                                         # sugg_btn_2
                    gr.update(),                                         # export_json_btn
                    gr.update(),                                         # export_excel_btn
                    gr.update(value="Ask", interactive=True),            # submit_btn
                    history_val,                                         # history_state
                    [[q] for q in reversed(history_val)] if history_val else [],
                    conv_id,                                             # conversation_state
                    gr.update(),                                         # suggestions_state
                    gr.update(),                                         # raw_rows_state
                    gr.update(),                                         # results_tabs
                )
            df, error_html, meta_html, csv_path, sugg_list, new_conv_id, explain_data, viz = process_query(
                question_val, domain_val, show_sql_val,
                show_explain=show_explain_val, conversation_id=conv_id,
            )

            new_history = list(history_val)
            q = question_val.strip()
            if q and (not new_history or new_history[-1] != q):
                new_history.append(q)
            new_history = new_history[-MAX_HISTORY:]

            have_suggs = bool(sugg_list)
            s0 = sugg_list[0] if len(sugg_list) > 0 else ""
            s1 = sugg_list[1] if len(sugg_list) > 1 else ""
            s2 = sugg_list[2] if len(sugg_list) > 2 else ""

            raw_rows = []
            if hasattr(df, "to_dict"):
                try:
                    raw_rows = df.to_dict(orient="records")
                except Exception:
                    pass

            fig = build_plotly_figure(raw_rows, viz)
            # Always show a chart panel — fall back to an informative empty state
            if fig is None:
                if not raw_rows:
                    chart_fig = build_empty_chart("No data to visualise")
                else:
                    chart_fig = build_empty_chart("Results are best viewed in the Table tab")
            else:
                chart_fig = fig
            # Only show result tabs when there is actual data.
            # Showing tabs on error-only responses would expose empty
            # Table / Chart / Explain panels, which is confusing.
            has_results = bool(raw_rows)

            return (
                gr.update(value=df, visible=True),                     # results_table
                gr.update(value=chart_fig, visible=True),              # results_plot
                error_html,                                             # error_box
                gr.update(visible=False),                               # welcome_group
                meta_html,                                              # metadata
                gr.update(value=csv_path, visible=bool(csv_path)),     # download_file
                gr.update(value=None, visible=False),                  # download_json
                gr.update(value=None, visible=False),                  # download_excel
                gr.update(value=explain_data if explain_data else None,
                          visible=bool(explain_data)),                 # explain_panel
                gr.update(visible=have_suggs),                         # suggestions_group
                gr.update(value=s0, visible=bool(s0)),                 # sugg_btn_0
                gr.update(value=s1, visible=bool(s1)),                 # sugg_btn_1
                gr.update(value=s2, visible=bool(s2)),                 # sugg_btn_2
                gr.update(visible=bool(raw_rows)),                     # export_json_btn
                gr.update(visible=bool(raw_rows)),                     # export_excel_btn
                gr.update(value="Ask", interactive=True),              # submit_btn
                new_history,                                            # history_state
                build_history_data(new_history),                       # history_display
                new_conv_id,                                            # conversation_state
                sugg_list,                                              # suggestions_state
                raw_rows,                                               # raw_rows_state
                gr.update(visible=has_results),                        # results_tabs
            )

        def clear_all(history_val):
            return (
                gr.update(value=pd.DataFrame(), visible=False),    # results_table
                gr.update(value=None, visible=False),              # results_plot
                "",                                                 # error_box
                gr.update(visible=True),                            # welcome_group
                "",                                                 # metadata
                gr.update(value=None, visible=False),              # download_file
                gr.update(value=None, visible=False),              # download_json
                gr.update(value=None, visible=False),              # download_excel
                gr.update(value=None, visible=False),              # explain_panel
                gr.update(visible=False),                           # suggestions_group
                gr.update(value="", visible=False),                 # sugg_btn_0
                gr.update(value="", visible=False),                 # sugg_btn_1
                gr.update(value="", visible=False),                 # sugg_btn_2
                gr.update(visible=False),                           # export_json_btn
                gr.update(visible=False),                           # export_excel_btn
                gr.update(value=""),                                # question
                gr.update(value="Ask", interactive=True),          # submit_btn
                None,                                               # conversation_state
                [],                                                 # suggestions_state
                [],                                                 # raw_rows_state
                gr.update(visible=False),                           # results_tabs
            )

        def do_export_json(raw_rows):
            path = export_results_as_json(raw_rows)
            return gr.update(value=path, visible=bool(path))

        def do_export_excel(raw_rows):
            path = export_results_as_excel(raw_rows)
            return gr.update(value=path, visible=bool(path))

        # ── Output lists ────────────────────────────────────────────

        CORE_OUTPUTS = [
            results_table, results_plot, error_box, welcome_group, metadata,
            download_file, download_json, download_excel, explain_panel,
            suggestions_group, sugg_btn_0, sugg_btn_1, sugg_btn_2,
            export_json_btn, export_excel_btn,
        ]
        QUERY_OUTPUTS = CORE_OUTPUTS + [
            submit_btn, history_state, history_display,
            conversation_state, suggestions_state, raw_rows_state,
            results_tabs,
        ]

        # ── Event wiring ────────────────────────────────────────────

        RUN_INPUTS = [question, domain_choice, show_sql, show_explain, history_state, conversation_state]

        submit_btn.click(
            fn=_thinking_label,
            inputs=[show_explain],
            outputs=submit_btn,
        ).then(
            fn=run_query,
            inputs=RUN_INPUTS,
            outputs=QUERY_OUTPUTS,
        )

        question.submit(
            fn=_thinking_label,
            inputs=[show_explain],
            outputs=submit_btn,
        ).then(
            fn=run_query,
            inputs=RUN_INPUTS,
            outputs=QUERY_OUTPUTS,
        )

        clear_btn.click(
            fn=clear_all,
            inputs=[history_state],
            outputs=CORE_OUTPUTS + [question, submit_btn, conversation_state, suggestions_state, raw_rows_state, results_tabs],
        )

        for btn, q in zip(sample_btns, SAMPLE_QUERIES):
            btn.click(
                fn=lambda explain_on, query=q: (query, _thinking_label(explain_on)),
                inputs=[show_explain],
                outputs=[question, submit_btn],
            ).then(
                fn=run_query,
                inputs=RUN_INPUTS,
                outputs=QUERY_OUTPUTS,
            )

        # ── Export buttons ──────────────────────────────────────────
        export_json_btn.click(
            fn=do_export_json,
            inputs=[raw_rows_state],
            outputs=[download_json],
        )
        export_excel_btn.click(
            fn=do_export_excel,
            inputs=[raw_rows_state],
            outputs=[download_excel],
        )

        # ── Suggestion button clicks ────────────────────────────────
        for btn_idx, sugg_btn in enumerate([sugg_btn_0, sugg_btn_1, sugg_btn_2]):
            sugg_btn.click(
                fn=lambda s, e, i=btn_idx: _pick_suggestion(i, s, e),
                inputs=[suggestions_state, show_explain],
                outputs=[question, submit_btn],
            ).then(
                fn=run_query,
                inputs=RUN_INPUTS,
                outputs=QUERY_OUTPUTS,
            )

        # History item click re-populates the question textbox
        def on_history_select(evt: gr.SelectData):
            return gr.update(value=evt.value)

        history_display.select(fn=on_history_select, outputs=question)

    return app


if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
    )
