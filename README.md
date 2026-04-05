# GPU Price Tracker Dashboard

Real-time dashboard for monitoring cloud GPU pricing trends.

## Features

- **Price trends** - Line charts showing price changes over time
- **Provider comparison** - Bar charts comparing current prices across providers
- **Price distribution** - Histogram showing price spread
- **Filters** - GPU model, time range, provider selection
- **Raw data** - Exportable table of all price points

## Tracked GPUs

- H100, H200, B200, B300, RTX 5090

## Data Source

- GetDeploying (scraped weekly via Firecrawl)
- Stored in Supabase

## Deployment

### Streamlit Cloud (Recommended)

1. Push this folder to a GitHub repository
2. Go to https://streamlit.io/cloud
3. Connect your GitHub account
4. Select this repository
5. Deploy

### Local Testing

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Configuration

Update Supabase credentials in `app.py`:
- `SUPABASE_URL`
- `SUPABASE_KEY`

## Updates

Data refreshes weekly on Mondays at 2 AM GMT+7.
