import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="GPU Price Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

SUPABASE_URL = "https://kbjnialjdwprwgrfggwa.supabase.co"
SUPABASE_KEY = "sb_publishable_8H9ZdKjQqS_ip1OjPTjA_g_2PfSehnB"

TARGET_GPUS = ["H100", "H200", "B200", "B300"]

@st.cache_data(ttl=300)
def fetch_all_data(days=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    url = f"{SUPABASE_URL}/rest/v1/gpu_prices?select=*&order=scraped_at.desc&limit=5000"
    if days:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        url += f"&scraped_at=gte.{cutoff}"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        st.error(f"Failed to fetch data: {r.status_code}")
        return pd.DataFrame()
    df = pd.DataFrame(r.json())
    if df.empty:
        return df
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce", utc=True)
    df["price_per_gpu_hour"] = pd.to_numeric(df["price_per_gpu_hour"], errors="coerce")
    df = df.dropna(subset=["scraped_at", "price_per_gpu_hour"])
    # Clean provider names (strip markdown artifacts)
    df["provider"] = df["provider"].str.replace(r"\[([^\]]+)\]\(.*?\)", r"\1", regex=True)
    df["provider"] = df["provider"].str.replace(r"!\[.*?\]\(.*?\)", "", regex=True).str.strip()
    return df


def get_latest_per_provider_model(df):
    """Return one row per (provider, gpu_model) — the most recent scrape."""
    idx = df.groupby(["provider", "gpu_model"])["scraped_at"].idxmax()
    return df.loc[idx].reset_index(drop=True)


def render_gpu_tab(df_model, model_name):
    if df_model.empty:
        st.info(f"No data for {model_name}.")
        return

    latest = get_latest_per_provider_model(df_model)
    on_demand = latest[latest["billing_type"] == "on-demand"].sort_values("price_per_gpu_hour")
    reserved = latest[latest["billing_type"] == "reserved"].sort_values("price_per_gpu_hour")

    # ── Key Metrics ──────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    od_prices = on_demand["price_per_gpu_hour"]
    with col1:
        st.metric("Providers tracked", latest["provider"].nunique())
    with col2:
        if not od_prices.empty:
            best = on_demand.iloc[0]
            st.metric("Cheapest on-demand", f"${best['price_per_gpu_hour']:.2f}/hr", delta=best["provider"])
        else:
            st.metric("Cheapest on-demand", "N/A")
    with col3:
        if not od_prices.empty:
            st.metric("Avg on-demand", f"${od_prices.mean():.2f}/hr")
        else:
            st.metric("Avg on-demand", "N/A")
    with col4:
        if not od_prices.empty:
            spread = od_prices.max() - od_prices.min()
            st.metric("Price spread", f"${spread:.2f}/hr")
        else:
            st.metric("Price spread", "N/A")

    st.markdown("---")

    # ── Price Comparison Table ────────────────────────────────────────────────
    st.subheader(f"💰 Current Prices — {model_name}")

    # Build comparison table: one row per provider, columns = billing types
    pivot = latest.pivot_table(
        index="provider",
        columns="billing_type",
        values="price_per_gpu_hour",
        aggfunc="min",
    ).reset_index()
    pivot.columns.name = None

    # Add GPU model column for context
    for col in ["on-demand", "reserved", "spot"]:
        if col not in pivot.columns:
            pivot[col] = None

    available_billing = [c for c in ["on-demand", "reserved", "spot"] if c in pivot.columns and pivot[c].notna().any()]
    if available_billing:
        pivot["cheapest"] = pivot[available_billing].min(axis=1)
        pivot = pivot.sort_values("cheapest")

    # Format for display
    display_cols = ["provider"] + available_billing
    display = pivot[display_cols].copy()
    for c in available_billing:
        display[c] = display[c].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "—")

    st.dataframe(display.set_index("provider"), use_container_width=True, height=300)

    st.markdown("---")

    # ── Bar Chart ─────────────────────────────────────────────────────────────
    st.subheader(f"🏢 Provider Price Comparison — {model_name}")

    if not on_demand.empty:
        fig = px.bar(
            on_demand,
            x="price_per_gpu_hour",
            y="provider",
            orientation="h",
            color="price_per_gpu_hour",
            color_continuous_scale="Blues_r",
            text="price_per_gpu_hour",
            title=f"{model_name} — On-Demand Price by Provider",
        )
        fig.update_traces(texttemplate="$%{text:.2f}", textposition="outside")
        fig.update_layout(
            height=max(300, len(on_demand) * 32),
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
            coloraxis_showscale=False,
        )
        fig.update_xaxes(title_text="$/hr")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No on-demand prices available.")

    st.markdown("---")

    # ── Price Trend Over Time ─────────────────────────────────────────────────
    st.subheader(f"📈 Price Trends — {model_name}")

    od_df = df_model[df_model["billing_type"] == "on-demand"].copy()
    if len(od_df["scraped_at"].dt.date.unique()) > 1:
        # Daily average per provider
        od_df["date"] = od_df["scraped_at"].dt.date
        trend = od_df.groupby(["date", "provider"])["price_per_gpu_hour"].mean().reset_index()
        trend["date"] = pd.to_datetime(trend["date"])

        fig2 = px.line(
            trend,
            x="date",
            y="price_per_gpu_hour",
            color="provider",
            title=f"{model_name} — Daily Avg On-Demand Price",
            markers=True,
        )
        fig2.update_layout(
            height=400,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        fig2.update_yaxes(title_text="$/hr")
        fig2.update_xaxes(title_text="Date")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Only one scrape date — trend chart will appear once more data is collected.")

    # ── Raw Data ──────────────────────────────────────────────────────────────
    with st.expander("📋 Raw data"):
        cols = ["scraped_at", "provider", "gpu_model", "gpu_variant", "price_per_gpu_hour", "billing_type", "num_gpus", "availability"]
        cols = [c for c in cols if c in df_model.columns]
        st.dataframe(
            df_model[cols].sort_values("scraped_at", ascending=False).head(200),
            use_container_width=True,
        )


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("📊 GPU Price Tracker")
st.sidebar.markdown("Monitor cloud GPU rental prices across providers.")
st.sidebar.markdown("---")

time_options = {"24 hours": 1, "7 days": 7, "30 days": 30, "All time": None}
selected_time = st.sidebar.selectbox("Time range", list(time_options.keys()), index=1)
days_filter = time_options[selected_time]

billing_filter = st.sidebar.selectbox("Billing type", ["on-demand", "reserved", "All"])

df_all = fetch_all_data(days=days_filter)

if not df_all.empty:
    all_providers = sorted(df_all["provider"].unique())
    selected_providers = st.sidebar.multiselect("Providers", all_providers, default=all_providers)
else:
    selected_providers = []

st.sidebar.markdown("---")
st.sidebar.caption(f"Source: GetDeploying.com  \nPowered by Streamlit + Supabase")

# ── Main ──────────────────────────────────────────────────────────────────────
st.title("📊 GPU Cloud Price Tracker")

if df_all.empty:
    st.warning("No data available. Check your Supabase connection.")
    st.stop()

# Apply filters
df = df_all.copy()
if selected_providers:
    df = df[df["provider"].isin(selected_providers)]
if billing_filter != "All":
    df = df[df["billing_type"] == billing_filter]

last_updated = df["scraped_at"].max()
st.markdown(
    f"**Last scraped:** {last_updated.strftime('%Y-%m-%d %H:%M UTC')} &nbsp;|&nbsp; "
    f"**Total records:** {len(df_all):,} &nbsp;|&nbsp; "
    f"**Providers:** {df_all['provider'].nunique()}"
)
st.markdown("---")

# ── Cross-GPU Overview ────────────────────────────────────────────────────────
st.subheader("🔍 Side-by-Side: Cheapest On-Demand Price per GPU")

overview_rows = []
latest_all = get_latest_per_provider_model(df_all)
od_latest = latest_all[latest_all["billing_type"] == "on-demand"]

for model in TARGET_GPUS:
    subset = od_latest[od_latest["gpu_model"] == model]
    if subset.empty:
        overview_rows.append({"GPU": model, "Cheapest $/hr": None, "Provider": "No data", "# Providers": 0})
    else:
        best = subset.loc[subset["price_per_gpu_hour"].idxmin()]
        overview_rows.append({
            "GPU": model,
            "Cheapest $/hr": best["price_per_gpu_hour"],
            "Provider": best["provider"],
            "# Providers": subset["provider"].nunique(),
        })

overview_df = pd.DataFrame(overview_rows)
cols_ov = st.columns(len(TARGET_GPUS))
for i, row in overview_df.iterrows():
    with cols_ov[i]:
        price_str = f"${row['Cheapest $/hr']:.2f}/hr" if pd.notna(row["Cheapest $/hr"]) else "N/A"
        st.metric(row["GPU"], price_str, delta=row["Provider"] if row["Provider"] != "No data" else None)

st.markdown("---")

# ── Per-GPU Tabs ──────────────────────────────────────────────────────────────
tabs = st.tabs(TARGET_GPUS)
for tab, model in zip(tabs, TARGET_GPUS):
    with tab:
        df_model = df[df["gpu_model"] == model]
        render_gpu_tab(df_model, model)
