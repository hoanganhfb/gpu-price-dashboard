import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="GPU Price Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

SUPABASE_URL = "https://kbjnialjdwprwgrfggwa.supabase.co"
SUPABASE_KEY = "sb_publishable_8H9ZdKjQqS_ip1OjPTjA_g_2PfSehnB"
TARGET_GPUS = ["H100", "H200", "B200", "RTX 5090"]
EXCLUDED_PROVIDERS = ["AWS", "Google Cloud", "Azure", "Oracle Cloud"]


@st.cache_data(ttl=300)
def fetch_all_data():
    """Fetch all rows from Supabase with pagination (Supabase caps at 1000 per request)."""
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Range-Unit": "items",
            "Range": f"{offset}-{offset + page_size - 1}",
        }
        url = f"{SUPABASE_URL}/rest/v1/gpu_prices?select=*&order=scraped_at.desc"
        r = requests.get(url, headers=headers)
        if r.status_code not in (200, 206):
            break
        batch = r.json()
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
    df["price_per_gpu_hour"] = pd.to_numeric(df["price_per_gpu_hour"], errors="coerce")
    df["total_per_hour"] = pd.to_numeric(df["total_per_hour"], errors="coerce")
    df = df.dropna(subset=["scraped_at", "price_per_gpu_hour"])
    return df


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("📊 GPU Price Tracker")
st.sidebar.markdown("Data source: [GetDeploying.com](https://getdeploying.com)")
st.sidebar.markdown("---")

df_all = fetch_all_data()
if df_all.empty:
    st.warning("No data available.")
    st.stop()

scrape_dates = sorted(df_all["scraped_at"].dt.date.unique(), reverse=True)
latest_date = scrape_dates[0]
prev_date = scrape_dates[1] if len(scrape_dates) > 1 else None

st.sidebar.caption(
    f"Latest scrape: **{latest_date}**"
    + (f"  \nPrevious: **{prev_date}**" if prev_date else "")
    + f"  \nTotal records: {len(df_all):,}"
)
st.sidebar.markdown("---")
st.sidebar.caption("Powered by Streamlit + Supabase")

# ── Title ─────────────────────────────────────────────────────────────────────
st.title("📊 GPU Cloud Price Tracker")
st.markdown(
    f"**Last scraped:** {latest_date} &nbsp;|&nbsp; "
    f"**Providers:** {df_all['provider'].nunique()} &nbsp;|&nbsp; "
    f"**Records:** {len(df_all):,}"
)

# ── Navigation ────────────────────────────────────────────────────────────────
page_options = ["📋 Summary", "📊 Provider Price Comparison", "📄 Price Table"]
page_keys = ["Summary", "Provider Price Comparison", "Price Table"]

page_cols = st.columns(len(page_options))
if "active_page" not in st.session_state:
    st.session_state.active_page = "Summary"

for i, (label, key) in enumerate(zip(page_options, page_keys)):
    with page_cols[i]:
        if st.button(label, key=f"nav_{key}", use_container_width=True, type="primary" if st.session_state.active_page == key else "secondary"):
            st.session_state.active_page = key
            st.rerun()

page = st.session_state.active_page
st.markdown("---")

# =============================================================================
# PAGE 1: SUMMARY
# =============================================================================
if page == "Summary":
    st.subheader("📋 Summary — Mean & Median by GPU and Billing Type")
    st.caption(
        f"Excludes {', '.join(EXCLUDED_PROVIDERS)} (outlier pricing). "
        f"Only On-Demand and Reserved. Spot/Custom excluded."
    )

    # Filter for summary
    df_summary = df_all[
        (~df_all["provider"].isin(EXCLUDED_PROVIDERS))
        & (df_all["billing_type"].isin(["On-Demand", "Reserved"]))
    ].copy()

    # ── Date columns logic ────────────────────────────────────────────────────
    # Fixed baseline dates (always shown)
    from datetime import date as date_type
    BASELINE_1 = date_type(2026, 3, 9)
    BASELINE_2 = date_type(2026, 4, 5)

    all_dates = sorted(df_summary["scraped_at"].dt.date.unique())

    # "This week" = most recent scrape date
    # "Last week" = second most recent, but only if we have > 2 dates
    this_week_date = all_dates[-1] if all_dates else None
    last_week_date = all_dates[-2] if len(all_dates) > 2 else None

    def get_stats(gpu, billing, target_date):
        if target_date is None:
            return np.nan, np.nan, 0
        subset = df_summary[
            (df_summary["gpu_model"] == gpu)
            & (df_summary["billing_type"] == billing)
            & (df_summary["scraped_at"].dt.date == target_date)
        ]["price_per_gpu_hour"]
        if len(subset) == 0:
            return np.nan, np.nan, 0
        return subset.mean(), subset.median(), len(subset)

    rows = []
    for gpu in TARGET_GPUS:
        for billing in ["On-Demand", "Reserved"]:
            b1_mean, b1_median, _ = get_stats(gpu, billing, BASELINE_1)
            b2_mean, b2_median, _ = get_stats(gpu, billing, BASELINE_2)
            lw_mean, lw_median, _ = get_stats(gpu, billing, last_week_date)
            tw_mean, tw_median, tw_n = get_stats(gpu, billing, this_week_date)

            # % change: this week vs last week
            mean_chg = (tw_mean - lw_mean) / lw_mean if pd.notna(lw_mean) and lw_mean != 0 and pd.notna(tw_mean) else np.nan
            median_chg = (tw_median - lw_median) / lw_median if pd.notna(lw_median) and lw_median != 0 and pd.notna(tw_median) else np.nan

            rows.append({
                "GPU": gpu, "Billing": billing, "Statistic": "Mean",
                "Mar 09": b1_mean, "Apr 05": b2_mean,
                "Last week": lw_mean, "This week": tw_mean,
                "% Change": mean_chg, "n": tw_n,
            })
            rows.append({
                "GPU": gpu, "Billing": billing, "Statistic": "Median",
                "Mar 09": b1_median, "Apr 05": b2_median,
                "Last week": lw_median, "This week": tw_median,
                "% Change": median_chg, "n": tw_n,
            })

    summary_df = pd.DataFrame(rows)

    # Column header with actual dates
    lw_label = f"Last week ({last_week_date.strftime('%b %d')})" if last_week_date else "Last week"
    tw_label = f"This week ({this_week_date.strftime('%b %d')})" if this_week_date else "This week"

    # Show as per-GPU sections
    for gpu in TARGET_GPUS:
        st.markdown(f"#### {gpu}")
        gpu_df = summary_df[summary_df["GPU"] == gpu].drop(columns=["GPU"]).reset_index(drop=True)

        display = gpu_df.copy()
        # Rename rolling columns to include dates
        display = display.rename(columns={"Last week": lw_label, "This week": tw_label})

        # Format price columns
        for col in ["Mar 09", "Apr 05", lw_label, tw_label]:
            display[col] = display[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "—")
        display["% Change"] = display["% Change"].apply(
            lambda x: f"{'🟢' if x > 0 else '🔴'} {x:+.1%}" if pd.notna(x) else "—"
        )

        st.dataframe(display, use_container_width=True, hide_index=True, height=220)

    # ── Quick highlights ──────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔍 Quick Highlights — Cheapest On-Demand (This Week)")

    highlight_date = this_week_date or latest_date
    latest_od = df_all[
        (df_all["scraped_at"].dt.date == highlight_date)
        & (df_all["billing_type"] == "On-Demand")
        & (~df_all["provider"].isin(EXCLUDED_PROVIDERS))
    ]

    cols = st.columns(len(TARGET_GPUS))
    for i, gpu in enumerate(TARGET_GPUS):
        with cols[i]:
            subset = latest_od[latest_od["gpu_model"] == gpu]
            if not subset.empty:
                best = subset.loc[subset["price_per_gpu_hour"].idxmin()]
                st.metric(gpu, f"${best['price_per_gpu_hour']:.2f}/hr", delta=best["provider"])
            else:
                st.metric(gpu, "N/A")


# =============================================================================
# PAGE 2 & 3: Shared filters
# =============================================================================
elif page in ("Provider Price Comparison", "Price Table"):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        selected_gpu = st.selectbox("GPU Model", TARGET_GPUS)
    with col_f2:
        selected_billing = st.selectbox("Billing Type", ["On-Demand", "Reserved"])

    # Filter data: most recent scrape date, selected GPU, selected billing type
    most_recent = sorted(df_all["scraped_at"].dt.date.unique())[-1]
    df_filtered = df_all[
        (df_all["scraped_at"].dt.date == most_recent)
        & (df_all["gpu_model"] == selected_gpu)
    ].copy()

    if selected_billing == "Reserved":
        df_filtered = df_filtered[df_filtered["billing_type"] == "Reserved"]
    else:
        df_filtered = df_filtered[df_filtered["billing_type"] == "On-Demand"]

    # =========================================================================
    # PAGE 2: PROVIDER PRICE COMPARISON (Bar Chart)
    # =========================================================================
    if page == "Provider Price Comparison":
        st.subheader(f"🏢 {selected_gpu} — {selected_billing} Price by Provider")

        if df_filtered.empty:
            st.info("No data for this selection.")
        else:
            # For bar chart: use lowest $/GPU/h per provider (some have multiple configs)
            bar_data = (
                df_filtered.groupby("provider")["price_per_gpu_hour"]
                .min()
                .reset_index()
                .sort_values("price_per_gpu_hour")
            )

            fig = px.bar(
                bar_data,
                x="price_per_gpu_hour",
                y="provider",
                orientation="h",
                color="price_per_gpu_hour",
                color_continuous_scale="Blues_r",
                text="price_per_gpu_hour",
            )
            fig.update_traces(texttemplate="$%{text:.2f}", textposition="outside")
            fig.update_layout(
                height=max(400, len(bar_data) * 30),
                yaxis={"categoryorder": "total ascending"},
                showlegend=False,
                coloraxis_showscale=False,
                margin=dict(l=0, r=80),
            )
            fig.update_xaxes(title_text="$/GPU/hr")
            fig.update_yaxes(title_text="")
            st.plotly_chart(fig, use_container_width=True)

            # Show count
            st.caption(f"{len(bar_data)} providers | Showing lowest $/GPU/h per provider")

    # =========================================================================
    # PAGE 3: PRICE TABLE (matching getdeploying.com format)
    # =========================================================================
    elif page == "Price Table":
        st.subheader(f"📋 {selected_gpu} — {selected_billing} Price Table")

        if df_filtered.empty:
            st.info("No data for this selection.")
        else:
            # Build table matching getdeploying.com
            table = df_filtered[
                ["provider", "gpus", "total_vram", "vcpus", "ram", "billing", "price_per_gpu_hour", "total_per_hour"]
            ].copy()

            table = table.rename(columns={
                "provider": "Provider",
                "gpus": "GPUs",
                "total_vram": "Total VRAM",
                "vcpus": "vCPUs",
                "ram": "RAM",
                "billing": "Billing",
                "price_per_gpu_hour": "$/GPU/h",
                "total_per_hour": "Total/h",
            })

            # Format prices
            table["$/GPU/h"] = table["$/GPU/h"].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "—")
            table["Total/h"] = table["Total/h"].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "—")
            table["vCPUs"] = table["vCPUs"].apply(lambda x: str(int(x)) if pd.notna(x) else "--")

            # Sort by raw price (extract number for sorting)
            table["_sort"] = df_filtered["price_per_gpu_hour"].values
            table = table.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

            st.dataframe(
                table,
                use_container_width=True,
                height=min(800, 40 + len(table) * 35),
                hide_index=True,
            )

            st.caption(f"{len(table)} entries | Data from GetDeploying.com | {most_recent}")
