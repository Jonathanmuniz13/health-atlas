# Global Health Indicators Dashboard (Health Atlas)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Shiny](https://img.shields.io/badge/Shiny%20for%20Python-app-1F7A63)
![Deployed](https://img.shields.io/badge/deployed-shinyapps.io-15433C)
![Status](https://img.shields.io/badge/status-live-success)

An interactive **Python (Shiny)** dashboard for exploring global health and well-being across **219 countries, 2010–2020** — integrating five indicators (happiness, depression prevalence, life expectancy, adult mortality, population) from four international sources into one explorable tool.

🚀 **[Launch the live app →](https://jonathanmuuf.shinyapps.io/health_atlas/)**
📊 **[Read the full project write-up →](https://github.com/Jonathanmuniz13/health-atlas)**

---

## What it does

Five tabs, each a different view of the same country-year panel:

- **Country Profile** — current indicator values + location map for a selected country/year
- **Trends** — one indicator's path across the decade for a single country
- **World Map** — choropleth shading every country by the chosen indicator/year
- **Compare** — overlaid trend lines for several countries at once
- **Relationships** — two-indicator scatter with population-sized bubbles, an OLS trend line, and Pearson *r* (life expectancy vs. adult mortality lands at r ≈ −0.93)

## Engineering highlights

- **Unified country-year panel:** 2,398 observations, 219 countries, assembled from the World Happiness Report, World Bank, WHO, and IHME — reconciled on standardized names + ISO-3 codes
- **Data-validation catch:** the mortality series (values ~50–680) was benchmarked against published figures and correctly re-identified as the **World Bank adult mortality rate** (probability a 15-year-old dies before 60, per 1,000), then relabeled throughout
- **Reliability refactor:** removed a live external geocoding dependency (slow, rate-limit-prone) in favor of a **static coordinate lookup** — the app now starts instantly and can't hang on a network call
- **Accessibility:** colorblind-safe (Okabe–Ito) palette, theme-aware Plotly charts (dark/light), indicator definitions surfaced in-app

## Repository structure

```
.
├── app.py                  # Shiny for Python app (UI + reactive server)
├── data/                   # cleaned country-year panel
├── requirements.txt        # dependencies
└── README.md
```

## How to run locally

Requires Python 3.12.

```bash
pip install -r requirements.txt
shiny run --reload app.py
```

Then open the local URL Shiny prints (usually `http://127.0.0.1:8000`).

## Tools

`Python` · `Shiny for Python` · `Plotly` · `pandas` · `NumPy` · `shinywidgets` · deployed on `shinyapps.io`

## Author

**Jonathan Muniz** — [Portfolio](https://jonathanmuniz13.github.io/PORTFOLIO-REPO/) · [LinkedIn](https://www.linkedin.com/in/jonathan-muniz-fl) · [GitHub](https://github.com/Jonathanmuniz13)
