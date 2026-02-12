"""
KPI Monitoring Dashboard
Auto-calculates advertising KPI scores from P-tab data.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from channel_data_loader import (
    load_agent_performance_data,
    refresh_agent_performance_data,
    calculate_kpi_scores,
)
from config import (
    AGENT_PERFORMANCE_TABS,
    KPI_SCORING,
    KPI_MANUAL,
    KPI_ORDER,
    KPI_PHP_USD_RATE,
)

st.set_page_config(page_title="KPI Monitoring", page_icon="📊", layout="wide")
st.title("📊 KPI Monitoring")

# Sidebar
st.sidebar.header("KPI Settings")

agent_names = ["All Agents"] + [t['agent'] for t in AGENT_PERFORMANCE_TABS]
selected_agent = st.sidebar.selectbox("Agent", agent_names)

if st.sidebar.button("🔄 Refresh Data"):
    refresh_agent_performance_data()
    st.rerun()

# Load P-tab data
ptab_data = load_agent_performance_data()
monthly_df = ptab_data.get('monthly', pd.DataFrame()) if ptab_data else pd.DataFrame()
daily_df = ptab_data.get('daily', pd.DataFrame()) if ptab_data else pd.DataFrame()

# Calculate live scores from P-tab
live_scores = {}
for tab_info in AGENT_PERFORMANCE_TABS:
    agent = tab_info['agent']
    live_scores[agent] = calculate_kpi_scores(monthly_df, agent, daily_df=daily_df)


def score_color(score):
    if score >= 4:
        return "#22c55e"
    elif score >= 3:
        return "#eab308"
    elif score >= 2:
        return "#f97316"
    return "#ef4444"


def score_badge(score):
    if score == 0:
        return '<span style="color:#64748b">-</span>'
    color = score_color(score)
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold">{int(score)}</span>'


# ============================================================
# ALL AGENTS VIEW
# ============================================================
if selected_agent == "All Agents":
    st.subheader("Team KPI Overview")
    st.markdown(f"**ROAS Formula:** `ARPPU / {KPI_PHP_USD_RATE} / Cost_per_FTD`")

    rows = []
    for tab_info in AGENT_PERFORMANCE_TABS:
        agent = tab_info['agent']
        s = live_scores[agent]

        cpa_s = s.get('cpa', {}).get('score', 0)
        roas_s = s.get('roas', {}).get('score', 0)
        cvr_s = s.get('cvr', {}).get('score', 0)
        ctr_s = s.get('ctr', {}).get('score', 0)

        cpa_v = s.get('cpa', {}).get('value', 0)
        roas_v = s.get('roas', {}).get('value', 0)
        cvr_v = s.get('cvr', {}).get('value', 0)
        ctr_v = s.get('ctr', {}).get('value', 0)

        # Weighted total (CPA 25% + CVR 15% = 40%)
        auto_weighted = cpa_s * 0.25 + cvr_s * 0.15

        rows.append({
            'Agent': agent,
            'CPA': f"${cpa_v:.2f}" if cpa_v > 0 else "-",
            'CPA Score': cpa_s,
            'ROAS': f"{roas_v:.4f}x" if roas_v > 0 else "-",
            'ROAS Score': roas_s,
            'CVR': f"{cvr_v:.1f}%" if cvr_v > 0 else "-",
            'CVR Score': cvr_s,
            'CTR': f"{ctr_v:.2f}%" if ctr_v > 0 else "-",
            'CTR Score': ctr_s,
            'Weighted': round(auto_weighted, 2),
        })

    summary_df = pd.DataFrame(rows)

    # HTML table
    html = '<table style="width:100%;border-collapse:collapse;font-size:14px">'
    html += '<tr style="background:#1e293b;color:#fff">'
    for col in ['Agent', 'CPA', 'Score', 'ROAS', 'Score', 'CVR', 'Score', 'CTR', 'Score', 'Weighted']:
        html += f'<th style="padding:8px;text-align:center;border:1px solid #334155">{col}</th>'
    html += '</tr>'

    for _, r in summary_df.iterrows():
        html += '<tr style="border:1px solid #334155">'
        html += f'<td style="padding:6px;font-weight:bold;border:1px solid #334155">{r["Agent"]}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{r["CPA"]}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{score_badge(r["CPA Score"])}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{r["ROAS"]}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{score_badge(r["ROAS Score"])}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{r["CVR"]}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{score_badge(r["CVR Score"])}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{r["CTR"]}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{score_badge(r["CTR Score"])}</td>'
        wt = r["Weighted"]
        wt_color = "#22c55e" if wt >= 1.5 else "#f97316" if wt >= 1.0 else "#ef4444"
        html += f'<td style="padding:6px;text-align:center;font-weight:bold;border:1px solid #334155;color:{wt_color}">{wt}</td>'
        html += '</tr>'

    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)

    # Bar chart
    st.subheader("Scores by Agent")
    agents = summary_df['Agent'].tolist()
    fig = go.Figure()
    for metric, label, color in [
        ('CPA Score', 'CPA', '#3b82f6'),
        ('ROAS Score', 'ROAS', '#22c55e'),
        ('CVR Score', 'CVR', '#a855f7'),
        ('CTR Score', 'CTR', '#f59e0b'),
    ]:
        fig.add_trace(go.Bar(name=label, x=agents, y=summary_df[metric].tolist(), marker_color=color))

    fig.update_layout(
        barmode='group',
        yaxis=dict(title='Score (1-4)', range=[0, 4.5]),
        height=400,
        margin=dict(t=30, b=40),
        legend=dict(orientation='h', y=1.1),
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================================================
# INDIVIDUAL AGENT VIEW
# ============================================================
else:
    agent_name = selected_agent
    agent_scores = live_scores.get(agent_name, {})

    st.subheader(f"KPI Card: {agent_name}")
    st.markdown(f"**ROAS Formula:** `ARPPU / {KPI_PHP_USD_RATE} / Cost_per_FTD`")

    # KPI metric cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        v = agent_scores.get('cpa', {}).get('value', 0)
        s = agent_scores.get('cpa', {}).get('score', 0)
        st.metric("CPA", f"${v:.2f}", f"Score: {s}/4")
    with col2:
        v = agent_scores.get('roas', {}).get('value', 0)
        s = agent_scores.get('roas', {}).get('score', 0)
        st.metric("ROAS", f"{v:.4f}x", f"Score: {s}/4")
    with col3:
        v = agent_scores.get('cvr', {}).get('value', 0)
        s = agent_scores.get('cvr', {}).get('score', 0)
        st.metric("CVR", f"{v:.1f}%", f"Score: {s}/4")
    with col4:
        v = agent_scores.get('ctr', {}).get('value', 0)
        s = agent_scores.get('ctr', {}).get('score', 0)
        st.metric("CTR", f"{v:.2f}%", f"Score: {s}/4")

    st.divider()

    # Full KPI card table
    all_kpis = {**KPI_SCORING, **KPI_MANUAL}
    param_text = {
        'cpa': '4: $9-$9.9 | 3: $10-$13 | 2: $14-$15 | 1: >$15',
        'roas': '4: >0.40x | 3: 0.20-0.39x | 2: 0.10-0.19x | 1: <0.10x',
        'cvr': '4: 7-9% | 3: 4-6% | 2: 2-3% | 1: <2%',
        'campaign_setup': '4: 95-97% | 3: 90-94% | 2: 85-89% | 1: <85%',
        'ctr': '4: 3-4% | 3: 2-2.9% | 2: 1-1.9% | 1: <0.9%',
        'ab_testing': '4: 20-24/wk | 3: 11-19/wk | 2: 6-10/wk | 1: <6/wk',
        'reporting': 'Manager evaluation',
        'data_insights': 'Manager evaluation',
        'account_dev': 'Manager evaluation',
        'profile_dev': 'Manager evaluation',
        'collaboration': 'Manager evaluation',
        'communication': 'Manager evaluation',
    }

    html = '<table style="width:100%;border-collapse:collapse;font-size:13px">'
    html += '<tr style="background:#1e293b;color:#fff">'
    for col in ['KRs', 'KPI', 'Weight', 'Parameters', 'Score', 'Weighted', 'Raw Value']:
        html += f'<th style="padding:8px;text-align:center;border:1px solid #334155">{col}</th>'
    html += '</tr>'

    auto_weighted_total = 0
    prev_krs = ""

    for key in KPI_ORDER:
        kpi_info = all_kpis[key]
        krs = kpi_info['krs']
        name = kpi_info['name']
        weight = f"{int(kpi_info['weight'] * 100)}%" if kpi_info['weight'] > 0 else ''
        params = param_text.get(key, '')
        is_auto = key in KPI_SCORING

        if is_auto and key in agent_scores:
            score = agent_scores[key]['score']
            raw = agent_scores[key]['value']
            if key == 'cpa':
                raw_display = f"${raw:.2f}"
            elif key == 'roas':
                raw_display = f"{raw:.4f}x"
            elif key == 'cvr':
                raw_display = f"{raw:.1f}%"
            elif key == 'ctr':
                raw_display = f"{raw:.2f}%"
            else:
                raw_display = str(raw)
            weighted = round(score * kpi_info['weight'], 2) if kpi_info['weight'] > 0 else ''
            if weighted:
                auto_weighted_total += weighted
            score_html = score_badge(score)
        else:
            score_html = '<span style="color:#64748b">Manual</span>'
            raw_display = ''
            weighted = ''

        krs_display = krs if krs != prev_krs else ''
        prev_krs = krs

        bg = '#0f172a' if is_auto else '#1a1a2e'
        html += f'<tr style="background:{bg};border:1px solid #334155">'
        html += f'<td style="padding:6px;border:1px solid #334155;font-weight:bold">{krs_display}</td>'
        html += f'<td style="padding:6px;border:1px solid #334155">{name}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{weight}</td>'
        html += f'<td style="padding:6px;font-size:11px;border:1px solid #334155">{params}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{score_html}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{weighted}</td>'
        html += f'<td style="padding:6px;text-align:center;border:1px solid #334155">{raw_display}</td>'
        html += '</tr>'

    # Total row
    total = round(auto_weighted_total, 2)
    total_color = "#22c55e" if total >= 1.5 else "#f97316" if total >= 1.0 else "#ef4444"
    html += f'<tr style="background:#1e293b;color:#fff;font-weight:bold;border:1px solid #334155">'
    html += f'<td style="padding:8px;border:1px solid #334155">TOTAL (Auto)</td>'
    html += f'<td style="padding:8px;border:1px solid #334155"></td>'
    html += f'<td style="padding:8px;text-align:center;border:1px solid #334155">40%</td>'
    html += f'<td style="padding:8px;border:1px solid #334155"></td>'
    html += f'<td style="padding:8px;border:1px solid #334155"></td>'
    html += f'<td style="padding:8px;text-align:center;border:1px solid #334155;color:{total_color};font-size:16px">{total}</td>'
    html += f'<td style="padding:8px;border:1px solid #334155"></td>'
    html += '</tr></table>'

    st.markdown(html, unsafe_allow_html=True)

    st.divider()
    st.markdown(f"**Auto-calculated weighted score:** {total} / 1.60 max (CPA 25% + CVR 15%)")
    st.progress(min(total / 1.60, 1.0) if total > 0 else 0)
