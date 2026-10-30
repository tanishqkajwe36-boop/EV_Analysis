from pathlib import Path
import json, os, sqlite3
from flask import Flask, render_template, request
from dotenv import load_dotenv
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import pandas as pd
import plotly.express as px
import plotly.io as pio

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-key-plum-theme-ev')

DB_PATH = Path(os.getenv('DATABASE_PATH', str(ROOT / 'data' / 'ev_market.db')))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH

OUT = ROOT / 'outputs'
DASHBOARD_URL = os.getenv('TABLEAU_DASHBOARD_URL', '').strip()
STORY_URL = os.getenv('TABLEAU_STORY_URL', '').strip()

def tableau_embed_url(url):
    if not url:
        return ''
    parsed = urlsplit(url)
    params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {'publish', 'display_count', ':display_count', ':sid', ':redirect', ':origin', ':showVizHome', ':embed'}
    ]
    params.extend([(':showVizHome', 'no'), (':embed', 'true')])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(params, safe=':'), ''))

# Authentic Plum & Mulberry Theme Colors
THEME_PRIMARY = '#7e2258'
THEME_ACCENT = '#b83274'
THEME_DARK = '#2c1626'
THEME_MUTED = '#745f6e'
THEME_GRID = '#f3e7ed'
PLUM_PIE_PALETTE = ['#501838', '#7e2258', '#9e2d6f', '#be3a78', '#d95d93', '#eeb2ce']
PLUM_SCATTER_PALETTE = ['#7e2258', '#b83274', '#9333ea', '#db2777', '#c026d3', '#a21caf', '#701a75', '#4c0519', '#831843']

def get_kpis():
    p = OUT / 'data_quality_report.json'
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            pass
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as con:
            row = con.execute(
                'SELECT COUNT(*), COUNT(DISTINCT manufacturer), COUNT(DISTINCT category), '
                'AVG(customer_rating), AVG(range_km), AVG(battery_capacity_kwh), SUM(annual_sales_units) '
                'FROM ev_market'
            ).fetchone()
        return dict(
            cleaned_rows=row[0] or 0,
            unique_manufacturers=row[1] or 0,
            unique_categories=row[2] or 0,
            avg_customer_rating=row[3] or 0,
            avg_range_km=row[4] or 0,
            avg_battery_capacity_kwh=row[5] or 0,
            total_annual_sales_units=row[6] or 0
        )
    return {}

def read_agg(name):
    p = OUT / f'{name}.csv'
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

def chart_html(name, df, kind, x, y, title, color=None):
    if df.empty:
        return '<div class="empty">Run <code>python src/build_data.py</code> to generate aggregate data.</div>'
    
    if kind == 'bar':
        fig = px.bar(
            df, x=x, y=y, color=color, title=title,
            template='plotly_white',
            color_discrete_sequence=[THEME_PRIMARY] if not color else PLUM_SCATTER_PALETTE
        )
        fig.update_traces(
            marker_line_width=0,
            hoverlabel=dict(bgcolor='#ffffff', font_color=THEME_DARK, font_size=12, bordercolor='#eddce5')
        )
    elif kind == 'line':
        fig = px.line(
            df, x=x, y=y, markers=True, title=title,
            template='plotly_white',
            color_discrete_sequence=[THEME_PRIMARY]
        )
        fig.update_traces(
            line=dict(width=3, color=THEME_PRIMARY),
            marker=dict(size=8, color=THEME_ACCENT, line=dict(width=2, color='#ffffff')),
            hoverlabel=dict(bgcolor='#ffffff', font_color=THEME_DARK, font_size=12, bordercolor='#eddce5')
        )
    elif kind == 'pie':
        fig = px.pie(
            df, names=x, values=y, title=title, hole=0.48,
            template='plotly_white',
            color_discrete_sequence=PLUM_PIE_PALETTE
        )
        fig.update_traces(
            textposition='inside',
            textinfo='percent+label',
            marker=dict(line=dict(color='#ffffff', width=2)),
            hoverlabel=dict(bgcolor='#ffffff', font_color=THEME_DARK, font_size=12, bordercolor='#eddce5')
        )
    elif kind == 'scatter':
        fig = px.scatter(
            df, x=x, y=y, color=color, title=title,
            template='plotly_white',
            color_discrete_sequence=PLUM_SCATTER_PALETTE
        )
        fig.update_traces(
            marker=dict(size=9, opacity=0.88, line=dict(width=1, color='#ffffff')),
            hoverlabel=dict(bgcolor='#ffffff', font_color=THEME_DARK, font_size=12, bordercolor='#eddce5')
        )
    else:
        return ''

    fig.update_layout(
        margin=dict(l=45, r=25, t=55, b=45),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='Plus Jakarta Sans, sans-serif', color=THEME_DARK, size=12),
        title=dict(font=dict(family='Outfit, sans-serif', size=15, color=THEME_DARK), x=0.02, y=0.96),
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
            title_text='',
            font=dict(size=11)
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor=THEME_GRID,
            zeroline=False,
            linecolor='#dfcbd6',
            tickfont=dict(color=THEME_MUTED, size=11)
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=THEME_GRID,
            zeroline=False,
            linecolor='#dfcbd6',
            tickfont=dict(color=THEME_MUTED, size=11)
        )
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs='cdn', config={'displayModeBar': False, 'responsive': True})

@app.route('/')
def home():
    k = get_kpis()
    charts = [
        ('Category Distribution', 'category_performance', 'bar', 'category', 'model_count', 'Vehicle models by EV category', None, 'Volume'),
        ('Manufacturer Portfolios', 'manufacturer_performance', 'bar', 'manufacturer', 'model_count', 'Top OEMs by active vehicle models', None, 'Competitive'),
        ('Battery Technology Mix', 'battery_mix', 'pie', 'battery_type', 'model_count', 'Battery chemistry breakdown', None, 'Technology'),
        ('Model-Year Trajectory', 'sales_by_year', 'line', 'model_year', 'model_records', 'Fleet adoption & records over time', None, 'Growth'),
        ('Global Manufacturing Footprint', 'country_footprint', 'bar', 'manufacturing_country', 'model_count', 'Vehicle models by manufacturing country', None, 'Geography'),
        ('Price vs Driving Range', 'price_range_by_category', 'scatter', 'avg_price_usd', 'avg_range_km', 'Average retail price vs rated range (km)', 'category', 'Efficiency'),
    ]
    built = []
    for title, file, kind, x, y, chart_title, color, tag in charts:
        df = read_agg(file)
        if file == 'manufacturer_performance':
            df = df.head(12)
        built.append({
            'title': title,
            'tag': tag,
            'desc': chart_title,
            'html': chart_html(file, df, kind, x, y, chart_title, color)
        })
    
    # Top Category Table Data
    cat_df = read_agg('category_performance')
    top_categories = []
    if not cat_df.empty:
        top_categories = cat_df.head(8).to_dict(orient='records')
        
    return render_template(
        'index.html',
        k=k,
        charts=built,
        top_categories=top_categories,
        dashboard_url=DASHBOARD_URL,
        story_url=STORY_URL,
        active_page='overview'
    )

@app.route('/dashboard')
def dashboard():
    return render_template(
        'tableau.html',
        page_title='Interactive Tableau Dashboard',
        subtitle='Real-time embedded analytics with parameter controls, segment filters, and multi-metric drilldowns.',
        embed_url=tableau_embed_url(DASHBOARD_URL),
        kind='dashboard',
        active_page='dashboard'
    )

@app.route('/story')
def story():
    return render_template(
        'tableau.html',
        page_title='EV Market Intelligence Story',
        subtitle='An 8-part narrative walkthrough detailing adoption curves, OEM landscape, battery evolution, and country insights.',
        embed_url=tableau_embed_url(STORY_URL),
        kind='story',
        active_page='story'
    )

@app.route('/about')
def about():
    k = get_kpis()
    return render_template('about.html', k=k, active_page='about')

@app.route('/health')
def health():
    return {
        'status': 'ok',
        'theme': 'Authentic Plum',
        'database_exists': DB_PATH.exists(),
        'database_path': str(DB_PATH),
        'tableau_dashboard_configured': bool(DASHBOARD_URL),
        'tableau_story_configured': bool(STORY_URL)
    }

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5000')), debug=False)
