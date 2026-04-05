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
billing_types = ["All", "on-demand", "reserved"]
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

# Convert datetime with error handling
df['scraped_at'] = pd.to_datetime(df['scraped_at'], errors='coerce')
df = df.dropna(subset=['scraped_at'])

df['price_per_gpu_hour'] = pd.to_numeric(df['price_per_gpu_hour'], errors='coerce')
df = df.dropna(subset=['price_per_gpu_hour'])

# Main title
st.title("📊 GPU Cloud Price Tracker")
st.markdown(f"**Last updated:** {df['scraped_at'].max().strftime('%Y-%m-%d %H:%M UTC')} | **Records:** {len(df):,} price points")
st.markdown("---")

# Get latest prices for all providers
latest_df = df.loc[df.groupby('provider')['scraped_at'].idxmax()]

# =============================================================================
# SECTION 1: Current Market Prices Table (TOP)
# =============================================================================
st.subheader("💰 Current Market Prices")

# Create pivot table for billing types
if 'billing_type' in df.columns and df['billing_type'].notna().any():
    latest_with_billing = latest_df.copy()
    latest_with_billing['billing_type'] = latest_with_billing['billing_type'].fillna('on-demand')
    
    # Pivot to show billing types as columns
    pivot_df = latest_with_billing.pivot_table(
        index='provider', 
        columns='billing_type', 
        values='price_per_gpu_hour',
        aggfunc='first'
    ).reset_index()
    
    # Calculate average price across billing types
    pivot_df['avg_price'] = pivot_df[['on-demand', 'reserved']].mean(axis=1, skipna=True)
    pivot_df = pivot_df.sort_values('avg_price')
    
    # Highlight cheapest in each column
    def highlight_cheapest(col):
        return ['background-color: #90CAF9' if v == col.name else '' for v in col]
    
    # Display table with cheapest highlighted
    def highlight_min(val):
        min_val = pivot_df[['on-demand', 'reserved']].min().min()
        return 'background-color: #90CAF9' if val == min_val else ''
    
    st.dataframe(
        pivot_df.style.format("{:.2f}").applymap(highlight_min),
        use_container_width=True,
        height=300
    )
else:
    # Fallback if no billing type data
    st.dataframe(
        latest_df[['provider', 'price_per_gpu_hour']].sort_values('price_per_gpu_hour'),
        use_container_width=True
    )

st.markdown("---")

# =============================================================================
# SECTION 2: Price Trends Over Time
# =============================================================================
st.subheader("📈 Price Trends Over Time")

if len(df) > 1:
    # Multi-line chart for selected providers
    fig_trend = px.line(
        df, 
        x='scraped_at', 
        y='price_per_gpu_hour',
        color='provider',
        title='GPU Price Trends by Provider',
        markers=True,
        hover_data={'scraped_at': '%Y-%m-%d'}
    )
    fig_trend.update_layout(
        height=450, 
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig_trend.update_yaxes(title_text='Price ($/hr)')
    fig_trend.update_xaxes(title_text='Date')
    st.plotly_chart(fig_trend, use_container_width=True)
    
    # Show % change from first to last data point
    first_date = df['scraped_at'].min()
    last_date = df['scraped_at'].max()
    
    first_prices = df[df['scraped_at'] == first_date].groupby('provider')['price_per_gpu_hour'].first()
    last_prices = df[df['scraped_at'] == last_date].groupby('provider')['price_per_gpu_hour'].last()
    
    changes = ((last_prices - first_prices) / first_prices * 100).round(2)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Price Change (Period Start to End)**")
        st.write(changes.to_string())
else:
    st.info("Not enough data to show trends.")

st.markdown("---")

# =============================================================================
# SECTION 3: Provider Price Comparison (Bar Chart)
# =============================================================================
st.subheader("🏢 Provider Price Comparison")

# Use latest prices only
latest_prices = latest_df.sort_values('price_per_gpu_hour')

# Create color scale based on price ranking
colors = [(i / len(latest_prices)) for i in range(len(latest_prices))]

fig_bar = px.bar(
    latest_prices,
    x='price_per_gpu_hour',
    y='provider',
    orientation='h',
    title='Current Prices by Provider (Latest Data)',
    color='price_per_gpu_hour',
    color_continuous_scale='Blues',
    text='price_per_gpu_hour'
)
fig_bar.update_layout(
    height=min(500, len(latest_prices) * 30), 
    yaxis={'categoryorder': 'total ascending'},
    showlegend=False
)
fig_bar.update_xaxes(title_text='Price ($/hr)')
fig_bar.update_traces(texttemplate='$%{text:.2f}', textposition='outside')
st.plotly_chart(fig_bar, use_container_width=True)

# =============================================================================
# SECTION 4: Key Metrics
# =============================================================================
st.markdown("---")
st.subheader("📊 Key Metrics")

col1, col2, col3, col4 = st.columns(4)

with col1:
    avg_price = df['price_per_gpu_hour'].mean()
    st.metric("Avg Price", f"${avg_price:.2f}/hr")

with col2:
    min_price = df['price_per_gpu_hour'].min()
    cheapest_provider = latest_df.loc[latest_df['price_per_gpu_hour'].idxmin()]['provider']
    st.metric("Lowest", f"${min_price:.2f}/hr", delta=f"{cheapest_provider}")

with col3:
    max_price = df['price_per_gpu_hour'].max()
    st.metric("Highest", f"${max_price:.2f}/hr")

with col4:
    provider_count = df['provider'].nunique()
    st.metric("Providers", provider_count)

# =============================================================================
# SECTION 5: Raw Data
# =============================================================================
st.markdown("---")
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
