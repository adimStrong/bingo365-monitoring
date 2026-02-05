"""
Channel ROI - Roll Back
Shows Facebook and Google Roll Back performance comparison
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from channel_data_loader import load_fb_channel_data, load_google_channel_data, refresh_channel_data
from config import CHANNEL_ROI_ENABLED

st.set_page_config(page_title="Roll Back", page_icon="🔄", layout="wide")

st.markdown("""
<style>
    .fb-card {
        background: linear-gradient(135deg, #1877f2 0%, #42a5f5 100%);
        padding: 20px; border-radius: 15px; color: white; text-align: center;
    }
    .google-card {
        background: linear-gradient(135deg, #fbbc05 0%, #f9a825 100%);
        padding: 20px; border-radius: 15px; color: white; text-align: center;
    }
    .section-header {
        background: linear-gradient(135deg, #fbbc05 0%, #f9a825 100%);
        color: white; padding: 15px; border-radius: 10px; margin: 20px 0 10px 0;
    }
</style>
""", unsafe_allow_html=True)


def format_currency(value):
    if pd.isna(value) or value == 0:
        return "$0.00"
    return f"${value:,.2f}"


def format_number(value):
    if pd.isna(value):
        return "0"
    return f"{int(value):,}"


def main():
    st.title("🔄 Roll Back Dashboard")
    st.markdown("Facebook vs Google - Roll Back Performance Comparison")

    if not CHANNEL_ROI_ENABLED:
        st.warning("Channel ROI Dashboard is disabled.")
        return

    # Load data
    with st.spinner("Loading data..."):
        fb_df = load_fb_channel_data()  # FB data for comparison
        google_data = load_google_channel_data()
        google_df = google_data.get('roll_back', pd.DataFrame())

    has_fb = not fb_df.empty
    has_google = not google_df.empty

    # Sidebar
    with st.sidebar:
        st.header("Controls")

        if st.button("🔄 Refresh", type="primary", use_container_width=True):
            refresh_channel_data()
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.subheader("Other Reports")
        st.page_link("pages/5_Daily_ROI.py", label="📊 Daily ROI", icon="📈")
        st.page_link("pages/7_Violet.py", label="💜 Violet", icon="📈")

    # Check data availability
    if not has_google:
        st.warning("⚠️ No Google Roll Back data available in the source spreadsheet.")
        st.info("The Roll Back section may not exist or have no data.")

        # Still show FB data if available
        if has_fb:
            st.markdown("---")
            st.subheader("📘 Facebook Data Available")

            fb_df['date'] = pd.to_datetime(fb_df['date'])
            yesterday = datetime.now().date() - timedelta(days=1)
            fb_df = fb_df[fb_df['date'].dt.date <= yesterday]

            if not fb_df.empty:
                totals = {
                    'cost': fb_df['cost'].sum(),
                    'register': fb_df['register'].sum(),
                    'ftd': fb_df['ftd'].sum(),
                }
                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Cost", format_currency(totals['cost']))
                col2.metric("📝 Register", format_number(totals['register']))
                col3.metric("💳 FTD", format_number(totals['ftd']))
        return

    # Prepare dates
    google_df['date'] = pd.to_datetime(google_df['date'])
    data_min_date = google_df['date'].min().date()
    data_max_date = google_df['date'].max().date()
    yesterday = datetime.now().date() - timedelta(days=1)
    max_selectable_date = min(data_max_date, yesterday)

    # Date filter in sidebar
    with st.sidebar:
        st.markdown("---")
        st.subheader("📅 Date Range")
        default_start = max(data_min_date, max_selectable_date - timedelta(days=30))
        date_from = st.date_input("From", value=default_start, min_value=data_min_date, max_value=max_selectable_date)
        date_to = st.date_input("To", value=max_selectable_date, min_value=data_min_date, max_value=max_selectable_date)

    # Filter by date
    google_df = google_df[(google_df['date'].dt.date >= date_from) & (google_df['date'].dt.date <= date_to)]

    if google_df.empty:
        st.warning("No data in selected date range.")
        return

    # Summary
    st.markdown('<div class="section-header"><h3>🔄 ROLL BACK SUMMARY</h3></div>', unsafe_allow_html=True)

    totals = {
        'cost': google_df['cost'].sum(),
        'register': google_df['register'].sum(),
        'ftd': google_df['ftd'].sum(),
    }
    totals['cpr'] = totals['cost'] / totals['register'] if totals['register'] > 0 else 0
    totals['cost_ftd'] = totals['cost'] / totals['ftd'] if totals['ftd'] > 0 else 0
    totals['conv_rate'] = (totals['ftd'] / totals['register'] * 100) if totals['register'] > 0 else 0

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("💰 Cost", format_currency(totals['cost']))
    col2.metric("📝 Register", format_number(totals['register']))
    col3.metric("💳 FTD", format_number(totals['ftd']))
    col4.metric("📈 CPR", format_currency(totals['cpr']))
    col5.metric("💵 Cost/FTD", format_currency(totals['cost_ftd']))
    col6.metric("🎯 Conv Rate", f"{totals['conv_rate']:.2f}%")

    st.markdown("---")

    # Daily trend
    st.markdown('<div class="section-header"><h3>📅 DAILY TREND</h3></div>', unsafe_allow_html=True)

    daily_df = google_df.groupby(google_df['date'].dt.date).agg({
        'cost': 'sum', 'ftd': 'sum', 'register': 'sum'
    }).reset_index()
    daily_df['cpr'] = daily_df.apply(lambda x: x['cost'] / x['register'] if x['register'] > 0 else 0, axis=1)
    daily_df['cost_ftd'] = daily_df.apply(lambda x: x['cost'] / x['ftd'] if x['ftd'] > 0 else 0, axis=1)

    col1, col2, col3 = st.columns(3)
    with col1:
        fig = px.line(daily_df, x='date', y='cost', markers=True, title='Daily Cost')
        fig.update_traces(line_color='#fbbc05')
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.line(daily_df, x='date', y='register', markers=True, title='Daily Register')
        fig.update_traces(line_color='#f9a825')
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col3:
        fig = px.line(daily_df, x='date', y='ftd', markers=True, title='Daily FTD')
        fig.update_traces(line_color='#ff8f00')
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.line(daily_df, x='date', y='cpr', markers=True, title='Daily CPR')
        fig.update_traces(line_color='#fbbc05')
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.line(daily_df, x='date', y='cost_ftd', markers=True, title='Daily Cost/FTD')
        fig.update_traces(line_color='#f9a825')
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Weekly Summary
    st.markdown('<div class="section-header"><h3>📆 WEEKLY SUMMARY</h3></div>', unsafe_allow_html=True)

    weekly_df = google_df.copy()
    weekly_df['week'] = weekly_df['date'].dt.isocalendar().week
    weekly_df['year'] = weekly_df['date'].dt.isocalendar().year
    weekly_df['week_label'] = weekly_df.apply(lambda x: f"{x['year']}-W{x['week']:02d}", axis=1)
    weekly_agg = weekly_df.groupby('week_label').agg({'cost': 'sum', 'ftd': 'sum', 'register': 'sum'}).reset_index()
    weekly_agg = weekly_agg.sort_values('week_label')
    weekly_agg['cpr'] = weekly_agg.apply(lambda x: x['cost'] / x['register'] if x['register'] > 0 else 0, axis=1)
    weekly_agg['cost_ftd'] = weekly_agg.apply(lambda x: x['cost'] / x['ftd'] if x['ftd'] > 0 else 0, axis=1)

    col1, col2, col3 = st.columns(3)
    with col1:
        fig = px.bar(weekly_agg, x='week_label', y='cost', title='Weekly Cost')
        fig.update_traces(marker_color='#fbbc05')
        fig.update_layout(height=300, xaxis_title="Week", yaxis_title="Cost (USD)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(weekly_agg, x='week_label', y='register', title='Weekly Register')
        fig.update_traces(marker_color='#f9a825')
        fig.update_layout(height=300, xaxis_title="Week", yaxis_title="Register")
        st.plotly_chart(fig, use_container_width=True)

    with col3:
        fig = px.bar(weekly_agg, x='week_label', y='ftd', title='Weekly FTD')
        fig.update_traces(marker_color='#ff8f00')
        fig.update_layout(height=300, xaxis_title="Week", yaxis_title="FTD")
        st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(weekly_agg, x='week_label', y='cpr', title='Weekly CPR')
        fig.update_traces(marker_color='#fbbc05')
        fig.update_layout(height=300, xaxis_title="Week", yaxis_title="CPR (USD)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(weekly_agg, x='week_label', y='cost_ftd', title='Weekly Cost/FTD')
        fig.update_traces(marker_color='#f9a825')
        fig.update_layout(height=300, xaxis_title="Week", yaxis_title="Cost/FTD (USD)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Monthly Summary
    st.markdown('<div class="section-header"><h3>📊 MONTHLY SUMMARY</h3></div>', unsafe_allow_html=True)

    monthly_df = google_df.copy()
    monthly_df['month'] = monthly_df['date'].dt.to_period('M').astype(str)
    monthly_agg = monthly_df.groupby('month').agg({'cost': 'sum', 'ftd': 'sum', 'register': 'sum'}).reset_index()
    monthly_agg = monthly_agg.sort_values('month')
    monthly_agg['cpr'] = monthly_agg.apply(lambda x: x['cost'] / x['register'] if x['register'] > 0 else 0, axis=1)
    monthly_agg['cost_ftd'] = monthly_agg.apply(lambda x: x['cost'] / x['ftd'] if x['ftd'] > 0 else 0, axis=1)

    col1, col2, col3 = st.columns(3)
    with col1:
        fig = px.bar(monthly_agg, x='month', y='cost', title='Monthly Cost')
        fig.update_traces(marker_color='#fbbc05')
        fig.update_layout(height=300, xaxis_title="Month", yaxis_title="Cost (USD)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(monthly_agg, x='month', y='register', title='Monthly Register')
        fig.update_traces(marker_color='#f9a825')
        fig.update_layout(height=300, xaxis_title="Month", yaxis_title="Register")
        st.plotly_chart(fig, use_container_width=True)

    with col3:
        fig = px.bar(monthly_agg, x='month', y='ftd', title='Monthly FTD')
        fig.update_traces(marker_color='#ff8f00')
        fig.update_layout(height=300, xaxis_title="Month", yaxis_title="FTD")
        st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(monthly_agg, x='month', y='cpr', title='Monthly CPR')
        fig.update_traces(marker_color='#fbbc05')
        fig.update_layout(height=300, xaxis_title="Month", yaxis_title="CPR (USD)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(monthly_agg, x='month', y='cost_ftd', title='Monthly Cost/FTD')
        fig.update_traces(marker_color='#f9a825')
        fig.update_layout(height=300, xaxis_title="Month", yaxis_title="Cost/FTD (USD)")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Data table
    with st.expander("📋 View All Data", expanded=False):
        display_df = google_df[['date', 'register', 'ftd', 'ftd_recharge', 'cost', 'cpr', 'roas']].copy()
        display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
        display_df = display_df.sort_values('date', ascending=False)
        display_df.columns = ['Date', 'Register', 'FTD', 'Recharge (PHP)', 'Cost (USD)', 'CPR', 'ROAS']
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.download_button("📥 Download CSV", display_df.to_csv(index=False), f"roll_back_{datetime.now():%Y%m%d}.csv")

    st.caption(f"Roll Back Dashboard | {date_from} to {date_to} | {len(google_df)} records")


if __name__ == "__main__":
    main()
