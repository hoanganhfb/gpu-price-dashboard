# GPU Price Tracker Dashboard

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

# Page config
st.set_page_config(
    page_title="GPU Price Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Supabase config
SUPABASE_URL = "https://kbjnialjdwprwgrfggwa.supabase.co"
SUPABASE_KEY = "sb_publishable_8H9ZdKjQqS_ip1OjPTjA_g_2PfSehnB"

# Cache data
@st.cache_data(ttl=300)
def fetch_gpu_prices(gpu_model=None, days=None):
    """Fetch GPU prices from Supabase"""
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}'
    }
    
    base_url = f"{SUPABASE_URL}/rest/v1/gpu_prices?select=*"
    
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        base_url += f"&scraped_at=gte.{cutoff}"
    
    if gpu_model:
        base_url += f"&gpu_model=eq.{gpu_model}"
    
    base_url += "&order=scraped_at.desc"
    
    response = requests.get(base_url, headers=headers)
    return response.json()

# Sidebar
st.sidebar.title("📊 GPU Price Tracker")
st.sidebar.markdown("Monitor cloud GPU pricing trends")

st.sidebar.markdown("---")

# GPU model filter
gpu_models = ["All", "H100", "H200", "B200", "B300", "RTX 5090"]
selected_gpu = st.sidebar.selectbox("GPU Model", gpu_models)

# Billing type filter
billing_types = ["All", "on-demand", "reserved", "spot", "custom"]
selected_billing = st.sidebar.selectbox("Billing Type", billing_types)

# Time range
time_options = {"7 days": 7, "30 days": 30, "All time": None}
selected_time = st.sidebar.selectbox("Time Range", list(time_options.keys()))
days_filter = time_options[selected_time]

# Provider filter (only show providers for selected GPU)
if selected_gpu != "All":
    all_data = fetch_gpu_prices(gpu_model=selected_gpu)
    providers = sorted(set([p['provider'] for p in all_data]))
    selected_providers = st.sidebar.multiselect("Providers", providers, default=providers)
else:
    all_data = fetch_gpu_prices()
    providers = sorted(set([p['provider'] for p in all_data]))
    selected_providers = st.sidebar.multiselect("Providers", providers, default=providers)

# Fetch data
if selected_gpu == "All":
    data = fetch_gpu_prices(days=days_filter)
else:
    data = fetch_gpu_prices(gpu_model=selected_gpu, days=days_filter)

# Filter by providers
if selected_providers:
    data = [d for d in data if d['provider'] in selected_providers]

# Filter by billing type
if selected_billing != "All":
    data = [d for d in data if d.get('billing_type') == selected_billing]

# Convert to DataFrame
df = pd.DataFrame(data)

if df.empty:
    st.warning("No data found for the selected filters.")
    st.stop()

# Clean provider names (remove markdown)
df['provider'] = df['provider'].str.replace(r'\[([^\]]+)\]\(.*?\)', r'\1', regex=True)
df['provider'] = df['provider'].str.replace(r'!\[.*?\]\(.*?\)', '', regex=True)
df['scraped_at'] = pd.to_datetime(df['scraped_at'])
df['price_per_gpu_hour'] = pd.to_numeric(df['price_per_gpu_hour'], errors='coerce')

# Main title
st.title("📊 GPU Cloud Price Tracker")
st.markdown(f"**Last updated:** {df['scraped_at'].max().strftime('%Y-%m-%d %H:%M UTC')}")
st.markdown(f"**Records:** {len(df):,} price points")

st.markdown("---")

# Key metrics
col1, col2, col3, col4 = st.columns(4)

# Get latest prices
latest = df.loc[df.groupby('provider')['scraped_at'].idxmax()]

with col1:
    avg_price = df['price_per_gpu_hour'].mean()
    st.metric("Avg Price", f"${avg_price:.2f}/hr", delta=None)

with col2:
    min_price = df['price_per_gpu_hour'].min()
    st.metric("Lowest", f"${min_price:.2f}/hr", delta=None)

with col3:
    max_price = df['price_per_gpu_hour'].max()
    st.metric("Highest", f"${max_price:.2f}/hr", delta=None)

with col4:
    provider_count = df['provider'].nunique()
    st.metric("Providers", provider_count, delta=None)

st.markdown("---")

# Price trend chart
st.subheader("📈 Price Trends Over Time")

if len(df) > 1:
    # Average price over time
    daily_avg = df.groupby(df['scraped_at'].dt.date)['price_per_gpu_hour'].mean().reset_index()
    daily_avg.columns = ['date', 'avg_price']
    
    fig_trend = px.line(
        daily_avg, 
        x='date', 
        y='avg_price',
        title='Average GPU Price Over Time',
        markers=True
    )
    fig_trend.update_layout(height=400, hovermode='x unified')
    fig_trend.update_yaxes(title_text='Price ($/hr)')
    st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.info("Not enough data to show trends.")

# Provider comparison
st.subheader("🏢 Provider Price Comparison")

# Use latest prices only
latest_prices = df.loc[df.groupby('provider')['scraped_at'].idxmax()]
latest_prices = latest_prices.sort_values('price_per_gpu_hour')

fig_bar = px.bar(
    latest_prices,
    x='price_per_gpu_hour',
    y='provider',
    orientation='h',
    title='Current Prices by Provider (Latest Data)',
    color='price_per_gpu_hour',
    color_continuous_scale='Blues'
)
fig_bar.update_layout(height=min(500, len(latest_prices) * 30), yaxis={'categoryorder': 'total ascending'})
fig_bar.update_xaxes(title_text='Price ($/hr)')
st.plotly_chart(fig_bar, use_container_width=True)

# Price distribution
st.subheader("📊 Price Distribution")

fig_hist = px.histogram(
    df,
    x='price_per_gpu_hour',
    nbins=20,
    title='Distribution of GPU Prices',
    color_discrete_sequence=['#1f77b4']
)
fig_hist.update_layout(height=400)
fig_hist.update_xaxes(title_text='Price ($/hr)')
fig_hist.update_yaxes(title_text='Frequency')
st.plotly_chart(fig_hist, use_container_width=True)

# Detailed data table
with st.expander("📋 View Raw Data"):
    st.dataframe(
        df[['scraped_at', 'provider', 'gpu_model', 'gpu_variant', 'price_per_gpu_hour', 'billing_type']]
          .sort_values('scraped_at', ascending=False)
          .head(100),
        use_container_width=True
    )

# Footer
st.markdown("---")
st.caption("Data source: GetDeploying | Updated weekly on Mondays | Powered by Streamlit + Supabase")
