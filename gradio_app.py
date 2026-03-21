"""
MERIDIAN Gradio UI

Chat-based interface for querying business data using natural language.
Results are always displayed in clean tabular format.
"""

import logging
import os
import tempfile
import pandas as pd
import gradio as gr

from app.config import settings
from app.views.registry import get_registry
from app.database.connection import get_db
from app.agents.orchestrator import Orchestrator

logging.basicConfig(level=logging.WARNING)
logging.getLogger("app").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

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


def format_result_as_table(result: list) -> pd.DataFrame:
    """Convert a list-of-dicts query result into a DataFrame."""
    if not result:
        return pd.DataFrame({"Info": ["No results found."]})
    return pd.DataFrame(result)


def build_metadata_html(result: dict, show_sql: bool) -> str:
    """Build styled HTML badge row for query metadata."""
    domain = result.get("domain", "unknown").capitalize()
    routing_conf = result.get("routing_confidence", 0) or 0
    confidence = result.get("confidence", 0) or 0
    row_count = result.get("row_count", 0) or 0
    views_list = result.get("views") or []
    views = ", ".join(views_list) if views_list else "—"

    html = f"""
    <div class="meta-row">
      <span class="badge badge-domain" title="Domain that handled this query">🗂 {domain}</span>
      <span class="badge badge-routing" title="How confident the router was in selecting this domain">
        🎯 Routing {routing_conf:.0%}
      </span>
      <span class="badge badge-accuracy" title="How confident the agent is in the accuracy of the answer">
        ✅ Accuracy {confidence:.0%}
      </span>
      <span class="badge badge-rows">📊 {row_count} row{"s" if row_count != 1 else ""}</span>
      <span class="badge badge-views" title="Database views accessed">🔍 {views}</span>
    </div>
    """
    if show_sql and result.get("sql"):
        import html as html_lib
        safe_sql = html_lib.escape(result["sql"])
        html += f"""
    <details class="sql-details">
      <summary>View generated SQL ▾</summary>
      <pre><code>{safe_sql}</code></pre>
    </details>
    """
    return html


def process_query(question: str, domain_choice: str, show_sql: bool):
    """
    Process a natural language query and return tabular results + metadata.

    Returns:
        Tuple of (DataFrame, error_html, metadata_html, csv_file_path)
    """
    empty_df = pd.DataFrame()

    if not question.strip():
        return empty_df, "", "", None

    try:
        # Route manually or auto
        if domain_choice == "Auto-detect":
            result = orchestrator.process_query(question)
        else:
            # Force domain by directly calling the domain agent
            domain_key = domain_choice.lower()
            agent = orchestrator.domain_agents.get(domain_key)
            if not agent:
                error_html = (
                    f'<div class="error-alert">'
                    f'⚠️ Unknown domain: <strong>{domain_choice}</strong>. '
                    f'Please choose a valid domain or use Auto-detect.'
                    f'</div>'
                )
                return empty_df, error_html, "", None
            result = agent.process_query(question)
            result["domain"] = domain_key
            result["routing_confidence"] = 1.0
            result["state"] = "complete"

        # Handle errors returned by the agent
        if "error" in result and result["error"]:
            error_html = f'<div class="error-alert">⚠️ {result["error"]}</div>'
            return empty_df, error_html, "", None

        # Build results table
        raw_results = result.get("result", [])
        df = format_result_as_table(raw_results)

        # Build styled metadata badges
        metadata_html = build_metadata_html(result, show_sql)

        # Generate CSV for download (only when there are real data rows)
        csv_path = None
        if raw_results:
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=".csv", prefix="meridian_results_"
            )
            df.to_csv(tmp.name, index=False)
            csv_path = tmp.name

        return df, "", metadata_html, csv_path

    except Exception as e:
        logger.error(f"UI query failed: {e}", exc_info=True)
        error_html = (
            f'<div class="error-alert">'
            f'⚠️ An unexpected error occurred: <strong>{str(e)}</strong>. '
            f'Try rephrasing your question.'
            f'</div>'
        )
        return empty_df, error_html, "", None


# ---------------------------------------------------------------------------
# UI Layout
# ---------------------------------------------------------------------------

FAVICON_PATH = "assets/favicon.svg"

# Inline SVG compass logo for the header (36 px, matches brand palette)
LOGO_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none"
     style="width:36px;height:36px;vertical-align:middle;margin-right:10px">
  <circle cx="32" cy="32" r="30" fill="#eef2ff" stroke="#6366f1" stroke-width="3"/>
  <line x1="32" y1="5"  x2="32" y2="11" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="32" y1="53" x2="32" y2="59" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="5"  y1="32" x2="11" y2="32" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round"/>
  <line x1="53" y1="32" x2="59" y2="32" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round"/>
  <polygon points="32,12 27,34 32,30 37,34" fill="#6366f1"/>
  <polygon points="32,52 27,30 32,34 37,30" fill="#a5b4fc"/>
  <circle cx="32" cy="32" r="3.5" fill="#4338ca"/>
</svg>
"""

EMPTY_STATE_HTML = """
<div class="empty-state">
  <div class="empty-icon">🧭</div>
  <p class="empty-title">Ready to navigate your data</p>
  <p class="empty-hint">Type a question above, or jump in with an example below:</p>
</div>
"""

MERIDIAN_CSS = """
/* ── Header ─────────────────────────────────────────────── */
.meridian-header {
    text-align: center;
    padding: 16px 0 8px;
    border-bottom: 1px solid #e5e7eb;
    margin-bottom: 8px;
}
.meridian-logo-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    margin-bottom: 4px;
}
.meridian-title {
    font-size: 1.9em;
    font-weight: 800;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #6366f1 0%, #4338ca 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.meridian-subtitle {
    font-size: 0.9em;
    color: #6b7280;
    margin: 0;
}

/* ── Welcome card (empty state + quick-start combined) ───── */
.welcome-card {
    border: 1px solid #e5e7eb !important;
    border-radius: 12px !important;
    background: #fafafa !important;
    padding: 4px 16px 16px !important;
    margin-top: 8px !important;
}

/* ── Quick-start label ───────────────────────────────────── */
.quickstart-label {
    font-size: 0.82em;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 2px 0 4px !important;
    padding: 0 !important;
}

/* ── Error alert ─────────────────────────────────────────── */
.error-alert {
    background: #fff1f2;
    border: 1px solid #fecdd3;
    border-left: 4px solid #f43f5e;
    border-radius: 6px;
    padding: 10px 14px;
    color: #be123c;
    font-size: 0.92em;
    margin: 8px 0;
}

/* ── Empty state ─────────────────────────────────────────── */
.empty-state {
    text-align: center;
    padding: 32px 24px 12px;
    color: #9ca3af;
}
.empty-icon  { font-size: 2.8em; margin-bottom: 8px; }
.empty-title { font-size: 1.05em; font-weight: 600; color: #6b7280; margin: 0 0 4px; }
.empty-hint  { font-size: 0.88em; margin: 0; }

/* ── Metadata badge row ──────────────────────────────────── */
.meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 8px 0 4px;
}
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.8em;
    font-weight: 500;
    white-space: nowrap;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}
.badge-domain   { background: #ede9fe; color: #5b21b6; }
.badge-routing  { background: #dbeafe; color: #1d4ed8; }
.badge-accuracy { background: #d1fae5; color: #065f46; }
.badge-rows     { background: #fef3c7; color: #92400e; }
.badge-views    { background: #f3f4f6; color: #374151; }

/* ── SQL details ─────────────────────────────────────────── */
.sql-details {
    margin-top: 8px;
    font-size: 0.85em;
}
.sql-details summary {
    cursor: pointer;
    color: #4b5563;
    font-weight: 500;
    padding: 4px 0;
    user-select: none;
}
.sql-details pre {
    background: #1e293b;
    color: #e2e8f0;
    border-radius: 6px;
    padding: 10px 14px;
    overflow-x: auto;
    margin-top: 6px;
    font-size: 0.9em;
}
.sql-details code { font-family: 'JetBrains Mono', 'Fira Code', monospace; }

/* ── Results table polish ────────────────────────────────── */
.dataframe table {
    border-collapse: separate !important;
    border-spacing: 0 !important;
    width: 100% !important;
}
.dataframe thead th {
    background: #f1f5f9 !important;
    color: #374151 !important;
    font-weight: 600 !important;
    font-size: 0.82em !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
    padding: 10px 14px !important;
    border-bottom: 2px solid #e2e8f0 !important;
    white-space: nowrap !important;
}
.dataframe tbody td {
    padding: 9px 14px !important;
    font-size: 0.9em !important;
    color: #1f2937 !important;
    border-bottom: 1px solid #f3f4f6 !important;
}
.dataframe tbody tr:nth-child(even) td {
    background: #f8fafc !important;
}
.dataframe tbody tr:hover td {
    background: #eff6ff !important;
    transition: background 0.12s ease !important;
}

/* ── Sidebar domain selector as cards ───────────────────── */
/* Hide the radio circle; style the whole label as a card.  */
#domain-radio input[type="radio"] {
    display: none !important;
}
#domain-radio label {
    display: flex !important;
    align-items: flex-start !important;
    padding: 10px 14px !important;
    border: 1.5px solid #e5e7eb !important;
    border-radius: 10px !important;
    margin-bottom: 6px !important;
    cursor: pointer !important;
    transition: border-color 0.15s ease, background 0.15s ease !important;
    background: #ffffff !important;
    line-height: 1.4 !important;
}
#domain-radio label:hover {
    border-color: #a5b4fc !important;
    background: #f5f3ff !important;
}
#domain-radio label:has(input[type="radio"]:checked) {
    border-color: #6366f1 !important;
    background: #eef2ff !important;
}
#domain-radio label:has(input[type="radio"]:checked) span {
    color: #4338ca !important;
    font-weight: 600 !important;
}

/* ── Query history panel ─────────────────────────────────── */
.history-item {
    display: block;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.85em;
    color: #374151;
    cursor: pointer;
    border: none;
    background: transparent;
    text-align: left;
    width: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: background 0.1s ease;
}
.history-item:hover { background: #f3f4f6; }
.history-empty {
    font-size: 0.82em;
    color: #9ca3af;
    text-align: center;
    padding: 10px 0;
}

/* ── Dark mode ───────────────────────────────────────────── */
@media (prefers-color-scheme: dark) {
    .welcome-card   { border-color: #374151 !important; background: #1f2937 !important; }
    .empty-state    { color: #6b7280; }
    .empty-title    { color: #9ca3af; }
    .error-alert    { background: #2d1519; border-color: #7f1d1d; color: #fca5a5; }
    .badge-domain   { background: #2e1065; color: #c4b5fd; }
    .badge-routing  { background: #1e3a5f; color: #93c5fd; }
    .badge-accuracy { background: #064e3b; color: #6ee7b7; }
    .badge-rows     { background: #451a03; color: #fcd34d; }
    .badge-views    { background: #1f2937; color: #9ca3af; }
    .dataframe thead th { background: #1e293b !important; color: #cbd5e1 !important; border-color: #334155 !important; }
    .dataframe tbody td { color: #e2e8f0 !important; border-color: #1e293b !important; }
    .dataframe tbody tr:nth-child(even) td { background: #0f172a !important; }
    .dataframe tbody tr:hover td { background: #1e3a5f !important; }
    #domain-radio label { background: #1f2937 !important; border-color: #374151 !important; }
    #domain-radio label:hover { background: #2e1065 !important; border-color: #818cf8 !important; }
    #domain-radio label:has(input[type="radio"]:checked) { background: #1e1b4b !important; border-color: #6366f1 !important; }
    .history-item { color: #d1d5db; }
    .history-item:hover { background: #374151; }
}
"""


def build_ui() -> gr.Blocks:
    """Build the Gradio Blocks UI."""

    with gr.Blocks(
        title="MERIDIAN — Intelligent Data Navigation",
    ) as app:

        # ── Header ──────────────────────────────────────────────────────────
        gr.HTML(
            f"""
            <div class="meridian-header">
              <div class="meridian-logo-row">
                {LOGO_SVG}
                <span class="meridian-title">MERIDIAN</span>
              </div>
              <p class="meridian-subtitle">
                Intelligent Data Navigation Platform &mdash; Ask your data questions in plain English
              </p>
            </div>
            """
        )

        with gr.Row():

            # ── Main column (3x) ─────────────────────────────────────────────
            with gr.Column(scale=3):

                question = gr.Textbox(
                    label="Ask a question",
                    placeholder="e.g. How many sales were made in the WEST region?",
                    lines=2,
                )

                with gr.Row():
                    submit_btn = gr.Button("Ask", variant="primary", scale=2)
                    clear_btn = gr.Button("Clear", scale=1)

                # Error alert — empty until an error occurs
                error_box = gr.HTML(value="")

                # ── CHANGE 1: Metadata badges now sit ABOVE the results table ──
                # Users see confidence scores before they scan the data rows.
                metadata = gr.HTML(value="")

                # ── CHANGE 3: Welcome card = empty state + quick-start unified ─
                # Both live inside one Group that hides after the first query runs,
                # replacing the separate quickstart-label + loose button row.
                with gr.Group(visible=True, elem_classes=["welcome-card"]) as welcome_group:
                    gr.HTML(value=EMPTY_STATE_HTML)
                    gr.HTML('<p class="quickstart-label">Try an example:</p>')
                    with gr.Row():
                        sample_btns = [gr.Button(q, size="sm") for q in SAMPLE_QUERIES]

                # Results table — hidden until first query runs
                results_table = gr.Dataframe(
                    label="Results",
                    interactive=False,
                    wrap=True,
                    visible=False,
                )

                # CSV download — hidden until results with real data are returned
                download_file = gr.File(
                    label="Download Results (CSV)",
                    visible=False,
                )

            # ── Sidebar (1x) ─────────────────────────────────────────────────
            with gr.Column(scale=1):

                domain_choice = gr.Radio(
                    choices=[
                        ("🤖  Auto-detect — let MERIDIAN choose", "Auto-detect"),
                        ("📈  Sales — orders, customers, regions",  "Sales"),
                        ("💰  Finance — ledger, accounts",          "Finance"),
                        ("🏭  Operations — inventory, warehouses",  "Operations"),
                    ],
                    value="Auto-detect",
                    label="Domain",
                    elem_id="domain-radio",
                )

                with gr.Accordion("Advanced Options", open=False):
                    show_sql = gr.Checkbox(
                        label="Show generated SQL",
                        value=False,
                        info="Reveals the SQL query executed against the database.",
                    )

                gr.Markdown("---")

                with gr.Accordion("Recent Queries", open=True):
                    history_display = gr.HTML(
                        value='<p class="history-empty">No queries yet</p>',
                        label="",
                    )

        # History state — lives outside any column so it persists across interactions
        history_state = gr.State([])

        # ── Event helpers ────────────────────────────────────────────────────

        ALL_OUTPUTS = [results_table, error_box, welcome_group, metadata, download_file]

        # ── History helpers ───────────────────────────────────────────────────

        MAX_HISTORY = 10  # keep last N questions

        def build_history_html(history: list) -> str:
            """Render the history list as clickable pill items."""
            if not history:
                return '<p class="history-empty">No queries yet</p>'
            items = ""
            for q in reversed(history):
                import html as _h
                safe = _h.escape(q)
                # Truncate display label at 42 chars for readability
                label = (q[:42] + "…") if len(q) > 42 else q
                safe_label = _h.escape(label)
                items += (
                    f'<button class="history-item" '
                    f'title="{safe}" '
                    f'onclick="'
                    f'  var tb = document.querySelector(\'textarea[data-testid=\\\"textbox\\\"]\');"'
                    f'>{safe_label}</button>\n'
                )
            return items

        def run_query(question_val, domain_val, show_sql_val, history_val):
            """Run a query; update all outputs, history panel, and restore button."""
            df, error_html, meta_html, csv_path = process_query(
                question_val, domain_val, show_sql_val
            )
            # Append to history (deduplicate consecutive identical questions)
            new_history = list(history_val)
            q = question_val.strip()
            if q and (not new_history or new_history[-1] != q):
                new_history.append(q)
            new_history = new_history[-MAX_HISTORY:]  # cap length

            return (
                gr.update(value=df, visible=True),                    # results_table
                error_html,                                             # error_box
                gr.update(visible=False),                               # welcome_group
                meta_html,                                              # metadata
                gr.update(value=csv_path, visible=bool(csv_path)),    # download_file
                gr.update(value="Ask", interactive=True),              # submit_btn
                new_history,                                            # history_state
                build_history_html(new_history),                       # history_display
            )

        def clear_all(history_val):
            """Reset main panel; preserve history across clears."""
            return (
                gr.update(value=pd.DataFrame(), visible=False),   # results_table
                "",                                                # error_box
                gr.update(visible=True),                           # welcome_group
                "",                                                # metadata
                gr.update(value=None, visible=False),             # download_file
                gr.update(value=""),                              # question textbox
                gr.update(value="Ask", interactive=True),         # submit_btn
            )

        # ── Event wiring ─────────────────────────────────────────────────────

        QUERY_OUTPUTS = ALL_OUTPUTS + [submit_btn, history_state, history_display]

        submit_btn.click(
            fn=lambda: gr.update(value="Thinking…", interactive=False),
            outputs=submit_btn,
        ).then(
            fn=run_query,
            inputs=[question, domain_choice, show_sql, history_state],
            outputs=QUERY_OUTPUTS,
        )

        question.submit(
            fn=lambda: gr.update(value="Thinking…", interactive=False),
            outputs=submit_btn,
        ).then(
            fn=run_query,
            inputs=[question, domain_choice, show_sql, history_state],
            outputs=QUERY_OUTPUTS,
        )

        clear_btn.click(
            fn=clear_all,
            inputs=[history_state],
            outputs=ALL_OUTPUTS + [question, submit_btn],
        )

        for btn, q in zip(sample_btns, SAMPLE_QUERIES):
            btn.click(
                fn=lambda query=q: (query, gr.update(value="Thinking…", interactive=False)),
                outputs=[question, submit_btn],
            ).then(
                fn=run_query,
                inputs=[question, domain_choice, show_sql, history_state],
                outputs=QUERY_OUTPUTS,
            )

        # Clicking a history item re-populates the question textbox
        def recall_history_item(item_question: str):
            return gr.update(value=item_question)

        history_display.select(
            fn=recall_history_item,
            inputs=history_display,
            outputs=question,
        )

    return app


if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        theme=gr.themes.Soft(primary_hue="violet", secondary_hue="slate"),
        css=MERIDIAN_CSS,
    )
