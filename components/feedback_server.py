"""
Component 9 – Feedback System (Local Web Admin)

FastAPI web server providing a dashboard to review evaluations, browse metas,
and submit corrections. Runs on the device's local network.
"""
import asyncio
from typing import Optional

import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import Environment, BaseLoader

from components.meta_discovery import MetaDiscovery
from components.meta_mapping import MetaMap
from config import config
from storage.store import Store
from utils.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Inline HTML templates (no separate template files needed)
# ---------------------------------------------------------------------------

_BASE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meta Coin Analyser</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, system-ui, sans-serif; background: #0f1117; color: #e2e8f0; }
  a { color: #63b3ed; text-decoration: none; }
  nav { background: #1a1f2e; padding: 12px 20px; display: flex; gap: 20px; align-items: center; }
  nav h1 { font-size: 1rem; color: #f6e05e; margin-right: auto; }
  nav a { font-size: 0.9rem; }
  .container { padding: 20px; max-width: 1100px; margin: 0 auto; }
  .card { background: #1a1f2e; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
  .strong_buy { background: #276749; color: #9ae6b4; }
  .buy { background: #2c5282; color: #90cdf4; }
  .watch { background: #744210; color: #fbd38d; }
  .avoid { background: #742a2a; color: #fc8181; }
  .score { font-size: 1.4rem; font-weight: 700; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #2d3748; }
  th { color: #a0aec0; font-size: 0.8rem; text-transform: uppercase; }
  input, textarea { background: #2d3748; color: #e2e8f0; border: 1px solid #4a5568;
                    border-radius: 4px; padding: 8px; width: 100%; margin-top: 4px; }
  button { background: #3182ce; color: white; border: none; border-radius: 4px;
           padding: 8px 20px; cursor: pointer; margin-top: 8px; }
  .meta-pill { display: inline-block; background: #2d3748; border-radius: 12px;
               padding: 2px 10px; margin: 2px; font-size: 0.8rem; }
  .emerging { border: 1px solid #ecc94b; }
  h2 { margin-bottom: 16px; font-size: 1.1rem; color: #a0aec0; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
  .stat { background: #1a1f2e; border-radius: 8px; padding: 16px; text-align: center; }
  .stat-val { font-size: 2rem; font-weight: 700; color: #f6e05e; }
  .stat-lbl { font-size: 0.8rem; color: #a0aec0; margin-top: 4px; }
  form label { font-size: 0.85rem; color: #a0aec0; }
</style>
</head>
<body>
<nav>
  <h1>⚡ Meta Coin Analyser</h1>
  <a href="/">Dashboard</a>
  <a href="/evaluations">Evaluations</a>
  <a href="/metas">Metas</a>
  <a href="/trends">Trends</a>
  <a href="/feedback">Feedback</a>
  <a href="/api/evaluations">API</a>
</nav>
<div class="container">
{% block content %}{% endblock %}
</div>
</body>
</html>
"""

_INDEX = _BASE.replace("{% block content %}{% endblock %}", """
<h2>Dashboard</h2>
<div class="grid">
  <div class="stat"><div class="stat-val">{{ total_evals }}</div><div class="stat-lbl">Total Evaluations</div></div>
  <div class="stat"><div class="stat-val">{{ total_metas }}</div><div class="stat-lbl">Known Metas</div></div>
  <div class="stat"><div class="stat-val">{{ emerging }}</div><div class="stat-lbl">Emerging Metas</div></div>
  <div class="stat"><div class="stat-val">{{ total_signals }}</div><div class="stat-lbl">Signals Processed</div></div>
</div>

<br>
<h2>Recent Evaluations</h2>
{% for ev in evaluations %}
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:start">
    <div>
      <strong>{{ ev.coin_name }}</strong> <span style="color:#a0aec0">${{ ev.coin_symbol }}</span>
      <span class="badge {{ ev.recommendation }}" style="margin-left:8px">{{ ev.recommendation.replace('_',' ').upper() }}</span>
    </div>
    <div class="score">{{ "%.0f"|format(ev.overall_score * 100) }}<span style="font-size:0.9rem;color:#a0aec0">%</span></div>
  </div>
  <div style="margin-top:8px">
    {% for m in ev.metas %}<span class="meta-pill">{{ m }}</span>{% endfor %}
  </div>
  <div style="margin-top:8px;font-size:0.85rem;color:#a0aec0">{{ ev.reasoning }}</div>
  <div style="margin-top:4px;font-size:0.75rem;color:#4a5568">{{ ev.timestamp[:19] }}</div>
</div>
{% else %}<p style="color:#4a5568">No evaluations yet. Waiting for Telegram signals...</p>
{% endfor %}
""")

_EVALUATIONS = _BASE.replace("{% block content %}{% endblock %}", """
<h2>All Evaluations</h2>
<table>
<thead><tr><th>Coin</th><th>Symbol</th><th>Metas</th><th>Score</th><th>Rec</th><th>Time</th></tr></thead>
<tbody>
{% for ev in evaluations %}
<tr>
  <td>{{ ev.coin_name }}</td>
  <td>${{ ev.coin_symbol }}</td>
  <td>{% for m in ev.metas %}<span class="meta-pill">{{ m }}</span>{% endfor %}</td>
  <td>{{ "%.0f"|format(ev.overall_score * 100) }}%</td>
  <td><span class="badge {{ ev.recommendation }}">{{ ev.recommendation }}</span></td>
  <td>{{ ev.timestamp[:19] }}</td>
</tr>
{% endfor %}
</tbody>
</table>
""")

_METAS = _BASE.replace("{% block content %}{% endblock %}", """
<h2>Meta Registry</h2>
<div class="grid">
{% for m in metas %}
<div class="card {% if m.is_emerging %}emerging{% endif %}">
  <div style="display:flex;justify-content:space-between">
    <strong>{{ m.name }}</strong>
    {% if m.is_emerging %}<span class="badge watch">EMERGING</span>{% endif %}
  </div>
  <div style="margin:6px 0;font-size:0.8rem;color:#a0aec0">{{ m.description }}</div>
  <div style="margin-bottom:6px">
    <span style="color:#a0aec0;font-size:0.75rem">Strength:</span>
    <span style="color:#f6e05e;font-weight:600"> {{ "%.0f"|format(m.strength * 100) }}%</span>
    &nbsp;
    <span style="color:#a0aec0;font-size:0.75rem">Trend:</span>
    <span style="color:#68d391;font-weight:600"> {{ "%.0f"|format(m.trend_alignment * 100) }}%</span>
  </div>
  <div>
    {% for c in m.coins[:8] %}<span class="meta-pill">${{ c }}</span>{% endfor %}
    {% if m.coins|length > 8 %}<span style="color:#a0aec0;font-size:0.75rem">+{{ m.coins|length - 8 }} more</span>{% endif %}
  </div>
</div>
{% else %}<p style="color:#4a5568">No metas yet.</p>
{% endfor %}
</div>
""")

_TRENDS = _BASE.replace("{% block content %}{% endblock %}", """
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
  <h2>Trend Sources</h2>
  <span style="font-size:0.8rem;color:#4a5568">Last collected: {{ stats.last_collected }}</span>
</div>

<div class="grid" style="margin-bottom:20px">
  <div class="stat"><div class="stat-val">{{ stats.total }}</div><div class="stat-lbl">Total Trend Items</div></div>
  <div class="stat"><div class="stat-val">{{ stats.source_count }}</div><div class="stat-lbl">Active Sources</div></div>
  <div class="stat"><div class="stat-val">{{ trends|length }}</div><div class="stat-lbl">Showing (last 200)</div></div>
</div>

<div style="margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap">
  <a href="/trends" style="padding:4px 12px;border-radius:4px;font-size:0.8rem;
     background:{% if not active_source %}#3182ce{% else %}#2d3748{% endif %};color:white">All</a>
  {% for src in sources %}
  <a href="/trends?source={{ src|urlencode }}"
     style="padding:4px 12px;border-radius:4px;font-size:0.8rem;
     background:{% if active_source == src %}#3182ce{% else %}#2d3748{% endif %};color:white">
    {{ src.replace('https://','').replace('http://','')[:40] }}
  </a>
  {% endfor %}
</div>

<table>
<thead><tr><th>Time</th><th>Source</th><th>Title</th><th>Keywords</th></tr></thead>
<tbody>
{% for t in trends %}
<tr>
  <td style="white-space:nowrap;font-size:0.75rem;color:#4a5568">
    {% if t.original_timestamp %}
      {{ t.original_timestamp[:19] }}
      <div style="color:#2d3748;font-size:0.7rem">collected {{ t.timestamp[:19] }}</div>
    {% else %}
      {{ t.timestamp[:19] }}
    {% endif %}
  </td>
  <td style="font-size:0.75rem;color:#a0aec0;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
      title="{{ t.source }}">
    {% if 'telegram:' in t.source %}
      📱 {{ t.source.replace('telegram:','') }}
    {% elif 'newsapi' in t.source %}
      📰 {{ t.source }}
    {% else %}
      🔗 {{ t.source.replace('https://','').replace('http://','')[:35] }}
    {% endif %}
  </td>
  <td style="font-size:0.85rem">{{ t.title[:100] }}{% if t.title|length > 100 %}…{% endif %}</td>
  <td>{% for kw in t.keywords[:6] %}<span class="meta-pill">{{ kw }}</span>{% endfor %}</td>
</tr>
{% else %}
<tr><td colspan="4" style="color:#4a5568;text-align:center;padding:24px">
  No trends collected yet. Waiting for first trend refresh cycle...
</td></tr>
{% endfor %}
</tbody>
</table>
""")

_FEEDBACK = _BASE.replace("{% block content %}{% endblock %}", """
<h2>Submit Feedback</h2>
<div class="card" style="max-width:500px">
<form method="post" action="/feedback">
  <label>Coin Symbol</label>
  <input name="coin_symbol" placeholder="e.g. MEOWDONALD" required>
  <br><br>
  <label>Correct Metas (comma-separated)</label>
  <input name="new_metas" placeholder="e.g. Animals/Memes, Food/Lifestyle">
  <br><br>
  <label>Note (optional)</label>
  <textarea name="note" rows="2" placeholder="Why this correction?"></textarea>
  <br>
  <button type="submit">Submit Correction</button>
</form>
</div>

<br>
<h2>Recent Feedback</h2>
<table>
<thead><tr><th>Symbol</th><th>Old Metas</th><th>New Metas</th><th>Note</th><th>Time</th></tr></thead>
<tbody>
{% for f in feedback %}
<tr>
  <td>${{ f.coin_symbol }}</td>
  <td>{{ f.old_metas }}</td>
  <td>{{ f.new_metas }}</td>
  <td>{{ f.note }}</td>
  <td>{{ f.timestamp[:19] }}</td>
</tr>
{% endfor %}
</tbody>
</table>
""")

_jinja = Environment(loader=BaseLoader())


def _render(template_str: str, **kwargs) -> str:
    return _jinja.from_string(template_str).render(**kwargs)


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------

def create_app(store: Store, meta_map: MetaMap, meta_discovery: MetaDiscovery) -> FastAPI:
    app = FastAPI(title="Meta Coin Analyser", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        evaluations = store.get_recent_evaluations(limit=10)
        all_metas = meta_map.get_all()
        all_signals = store.get_recent_signals(limit=1)
        total_signals = len(store.get_recent_signals(limit=10000))
        emerging = sum(1 for m in all_metas if m.is_emerging)
        return _render(
            _INDEX,
            evaluations=evaluations,
            total_evals=len(store.get_recent_evaluations(limit=10000)),
            total_metas=len(all_metas),
            emerging=emerging,
            total_signals=total_signals,
        )

    @app.get("/evaluations", response_class=HTMLResponse)
    async def evaluations_page():
        evaluations = store.get_recent_evaluations(limit=100)
        return _render(_EVALUATIONS, evaluations=evaluations)

    @app.get("/metas", response_class=HTMLResponse)
    async def metas_page():
        metas = [m.to_dict() for m in meta_map.get_all()]
        return _render(_METAS, metas=metas)

    @app.get("/trends", response_class=HTMLResponse)
    async def trends_page(request: Request, source: str = ""):
        trends = store.get_trends_for_display(limit=200, source_filter=source)
        sources = store.get_trend_sources()
        stats = store.get_trend_stats()
        return _render(
            _TRENDS,
            trends=trends,
            sources=sources,
            stats=stats,
            active_source=source,
        )

    @app.get("/feedback", response_class=HTMLResponse)
    async def feedback_page():
        feedback = store.get_recent_feedback(limit=30)
        return _render(_FEEDBACK, feedback=feedback)

    @app.post("/feedback")
    async def submit_feedback(
        coin_symbol: str = Form(...),
        new_metas: str = Form(""),
        note: str = Form(""),
    ):
        symbol = coin_symbol.strip().upper()
        new_meta_list = [m.strip() for m in new_metas.split(",") if m.strip()]
        old_evals = store.get_recent_evaluations(limit=200)
        old_metas = []
        for ev in old_evals:
            if ev.get("coin_symbol") == symbol:
                old_metas = ev.get("metas", [])
                break
        meta_discovery.apply_feedback(symbol, old_metas, new_meta_list, note)
        return RedirectResponse("/feedback", status_code=303)

    @app.get("/api/evaluations")
    async def api_evaluations(limit: int = 50):
        return JSONResponse(store.get_recent_evaluations(limit=min(limit, 500)))

    @app.get("/api/metas")
    async def api_metas():
        return JSONResponse([m.to_dict() for m in meta_map.get_all()])

    @app.get("/api/signals")
    async def api_signals(limit: int = 50):
        return JSONResponse(store.get_recent_signals(limit=min(limit, 200)))

    return app


class FeedbackServer:
    def __init__(
        self,
        store: Store,
        meta_map: MetaMap,
        meta_discovery: MetaDiscovery,
    ) -> None:
        self._store = store
        self._meta_map = meta_map
        self._meta_discovery = meta_discovery

    async def run(self) -> None:
        app = create_app(self._store, self._meta_map, self._meta_discovery)
        server_config = uvicorn.Config(
            app,
            host=config.FEEDBACK_HOST,
            port=config.FEEDBACK_PORT,
            log_level="warning",
        )
        server = uvicorn.Server(server_config)
        log.info(
            "FeedbackServer starting at http://%s:%d",
            config.FEEDBACK_HOST,
            config.FEEDBACK_PORT,
        )
        await server.serve()
