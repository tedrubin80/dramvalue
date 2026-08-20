# DramValue Portfolio Demo

Static case study site for the DramValue (WTracker) project — deployable to Vercel when production is sunset from the VPS.

## Pages

| Path | Content |
|------|---------|
| `/` | Overview, stats, timeline, stack |
| `/ingestion` | Scrapers, pipeline stages, sources |
| `/analysis` | Bottle matching, site features, market stats |
| `/platform` | Docker architecture, API, SEO, ops |
| `/data` | Open datasets (Hugging Face + Kaggle) |

## Deploy to Vercel

1. Import the GitHub repo in [Vercel](https://vercel.com/new)
2. Set **Root Directory** to `demo`
3. Framework preset: **Other** (static site, no build step)
4. Deploy

Or from the CLI:

```bash
cd demo
npx vercel
```

## Local preview

```bash
cd demo
python3 -m http.server 8080
# open http://localhost:8080
```

Note: absolute asset paths (`/assets/...`) require serving from the demo root, not opening HTML files directly.

## Updating stats

Edit the numbers in each HTML page when a new export is published, or extend `scripts/dataset_card.py` to generate static pages in a future iteration.
