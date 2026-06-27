"""
Global Health Indicators Dashboard
Python Shiny app — country-level health metrics, 2010-2020.

"""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from shiny import App, reactive, render, req, ui
from ipyleaflet import Map, Marker, basemaps
from faicons import icon_svg
from shinywidgets import output_widget, render_widget, render_plotly

from shared import BASEMAPS, country_coordinates

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
data = pd.read_csv("cleaned_global_health_data2.csv", encoding="utf-8")
data["year"] = data["year"].astype(int)

AVAILABLE_COUNTRIES = set(data["Country"].unique())
WORLD_CENTER = (20.0, 0.0)  # sensible fallback instead of "Tokyo"

# Each indicator: (friendly label, accent color matching its value box).
INDICATOR_META = {
    "Happiness_Score":       ("Happiness Score", "#8e44ad"),
    "Depression_Prevalence": ("Depression Prevalence", "#3949ab"),
    "Life_Expectancy":       ("Life Expectancy", "#27ae60"),
    "Mortality_Rate":        ("Adult Mortality", "#c0392b"),
    "Population":             ("Population", "#d4a017"),
}


# ---------------------------------------------------------------------------
# Offline geo helpers (replace Nominatim entirely)
# ---------------------------------------------------------------------------
def country_centroid(country: str):
    """Static lookup; no network call."""
    return country_coordinates.get(country, WORLD_CENTER)


def _fmt(value, suffix="", decimals=2):
    """Format a numeric cell, returning 'N/A' for missing values."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    return f"{value:.{decimals}f}{suffix}"


def _hex_to_rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _hover_style(mode):
    """Legible tooltip in either theme (fixes white-on-white hover boxes)."""
    if mode == "light":
        return dict(bgcolor="rgba(255,255,255,0.95)", font=dict(color="#111"),
                    bordercolor="rgba(120,120,120,0.6)")
    return dict(bgcolor="rgba(30,30,30,0.95)", font=dict(color="#fff"),
                bordercolor="rgba(120,120,120,0.6)")


def build_trend_figure(country, indicator, cur_year, mode="dark"):
    """Pure figure builder (no Shiny deps) so it can be unit-tested.
    Plots one indicator over 2010-2020 for a country, with the slider's
    current year highlighted."""
    label, color = INDICATOR_META[indicator]
    df = data[data["Country"] == country].sort_values("year")
    template = "plotly_white" if mode == "light" else "plotly_dark"
    axis_color = "#333" if mode == "light" else "#ddd"
    fig = go.Figure()

    # No data at all for this indicator/country -> friendly placeholder.
    if df[indicator].notna().sum() == 0:
        fig.update_layout(
            template=template, autosize=True,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            annotations=[dict(
                text=f"No {label} data available for {country}",
                xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                font=dict(size=16, color=axis_color))],
        )
        return fig

    # Pad the y-range so trends are readable (don't force a 0 baseline).
    valid = df[indicator].dropna()
    ymin, ymax = float(valid.min()), float(valid.max())
    span = ymax - ymin
    pad = span * 0.15 if span > 0 else (abs(ymax) * 0.1 if ymax != 0 else 1.0)

    # Main trend line with a soft area fill.
    fig.add_trace(go.Scatter(
        x=df["year"].tolist(), y=df[indicator].tolist(),
        mode="lines+markers", line=dict(color=color, width=3),
        marker=dict(size=7, color=color), fill="tozeroy",
        fillcolor=_hex_to_rgba(color, 0.15), connectgaps=False, name=label,
        hovertemplate="%{x}<br>" + label + ": %{y:,.2f}<extra></extra>",
    ))

    # Highlight the slider's current year.
    cur = df[df["year"] == cur_year]
    if not cur.empty and pd.notna(cur[indicator].iloc[0]):
        cv = float(cur[indicator].iloc[0])
        fig.add_trace(go.Scatter(
            x=[cur_year], y=[cv], mode="markers",
            marker=dict(size=15, color=color, line=dict(width=2.5, color="white")),
            showlegend=False,
            hovertemplate="%{x}<br>" + label + ": %{y:,.2f}<extra></extra>",
        ))
        fig.add_annotation(
            x=cur_year, y=cv, text=f"<b>{cv:,.2f}</b>",
            showarrow=True, arrowhead=0, ax=0, ay=-28,
            font=dict(color=axis_color, size=13),
        )

    fig.update_layout(
        template=template, autosize=True, hovermode="x unified", showlegend=False,
        hoverlabel=_hover_style(mode),
        margin=dict(l=60, r=25, t=55, b=45),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        title=dict(text=f"{label} in {country}", x=0.02, xanchor="left",
                   font=dict(size=18)),
        xaxis=dict(title="Year", dtick=2, tickmode="linear", showgrid=False,
                   color=axis_color),
        yaxis=dict(range=[ymin - pad, ymax + pad], showgrid=True,
                   gridcolor="rgba(128,128,128,0.2)", color=axis_color),
    )
    return fig


def _lighten(hex_color, amount):
    """Blend a hex color toward white by `amount` in [0, 1] (for map scales)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (
        f"rgb({int(r + (255 - r) * amount)},"
        f"{int(g + (255 - g) * amount)},"
        f"{int(b + (255 - b) * amount)})"
    )


def build_choropleth_figure(indicator, year, selected, mode="dark"):
    """World choropleth of one indicator for one year, shaded with the
    indicator's accent color. The selected country is outlined in white."""
    label, color = INDICATOR_META[indicator]
    template = "plotly_white" if mode == "light" else "plotly_dark"
    axis_color = "#333" if mode == "light" else "#ddd"
    dfy = data[data["year"] == year].dropna(subset=[indicator])
    fig = go.Figure()

    if dfy.empty:
        fig.update_layout(
            template=template, autosize=True, paper_bgcolor="rgba(0,0,0,0)",
            annotations=[dict(
                text=f"No {label} data available for {year}",
                xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                font=dict(size=16, color=axis_color))],
        )
        return fig

    scale = [[0.0, _lighten(color, 0.82)], [1.0, color]]
    fig.add_trace(go.Choropleth(
        locations=dfy["Country_Code"], z=dfy[indicator], text=dfy["Country"],
        colorscale=scale, marker_line_color="rgba(120,120,120,0.5)",
        marker_line_width=0.3, colorbar=dict(title=label, thickness=14, len=0.7),
        hovertemplate="%{text}<br>" + label + ": %{z:,.2f}<extra></extra>",
    ))

    # Outline the currently selected country, if it has data this year.
    sel = dfy[dfy["Country"] == selected]
    if not sel.empty:
        fig.add_trace(go.Choropleth(
            locations=sel["Country_Code"], z=sel[indicator], text=sel["Country"],
            colorscale=scale, showscale=False,
            marker_line_color="white", marker_line_width=2.2,
            hovertemplate="%{text}<br>" + label + ": %{z:,.2f}<extra></extra>",
        ))

    fig.update_geos(
        projection_type="natural earth", showframe=False, showcoastlines=False,
        showland=True, landcolor="rgba(128,128,128,0.12)",
        bgcolor="rgba(0,0,0,0)", lakecolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        template=template, autosize=True,
        hoverlabel=_hover_style(mode),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=50, b=0),
        title=dict(text=f"{label} by country — {year}", x=0.02, xanchor="left",
                   font=dict(size=18)),
        geo=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


COMPARE_PALETTE = [
    "#0072B2", "#E69F00", "#009E73", "#D55E00",
    "#CC79A7", "#56B4E9", "#F0E442", "#000000",
]  # Okabe-Ito colorblind-safe qualitative palette


def build_compare_figure(countries, indicator, cur_year, mode="dark"):
    """Overlay several countries' trend lines for one indicator."""
    label, _ = INDICATOR_META[indicator]
    template = "plotly_white" if mode == "light" else "plotly_dark"
    axis_color = "#333" if mode == "light" else "#ddd"
    fig = go.Figure()

    if not countries:
        fig.update_layout(
            template=template, autosize=True, paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            annotations=[dict(
                text="Select one or more countries to compare",
                xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                font=dict(size=16, color=axis_color))],
        )
        return fig

    for i, country in enumerate(countries):
        df = data[data["Country"] == country].sort_values("year")
        color = COMPARE_PALETTE[i % len(COMPARE_PALETTE)]
        fig.add_trace(go.Scatter(
            x=df["year"].tolist(), y=df[indicator].tolist(),
            mode="lines+markers", name=country,
            line=dict(color=color, width=2.5), marker=dict(size=6),
            connectgaps=False,
            hovertemplate=country + "<br>%{x}: %{y:,.2f}<extra></extra>",
        ))

    # Mark the slider's current year across all lines.
    fig.add_vline(x=cur_year, line=dict(color="rgba(150,150,150,0.5)", dash="dash"))

    fig.update_layout(
        template=template, autosize=True, hovermode="x unified",
        hoverlabel=_hover_style(mode),
        margin=dict(l=60, r=25, t=55, b=45),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        title=dict(text=f"{label} — country comparison", x=0.02, xanchor="left",
                   font=dict(size=18)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Year", dtick=2, tickmode="linear", showgrid=False,
                   color=axis_color),
        yaxis=dict(title=label, showgrid=True, gridcolor="rgba(128,128,128,0.2)",
                   color=axis_color),
    )
    return fig


def build_scatter_figure(x_ind, y_ind, year, selected, mode="dark"):
    """Scatter of two indicators across countries for one year. Bubble size =
    Population, the selected country is highlighted, plus an OLS trend line and
    the Pearson correlation in the title."""
    x_label, _ = INDICATOR_META[x_ind]
    y_label, _ = INDICATOR_META[y_ind]
    template = "plotly_white" if mode == "light" else "plotly_dark"
    axis_color = "#333" if mode == "light" else "#ddd"
    fig = go.Figure()

    def _placeholder(msg):
        fig.update_layout(
            template=template, autosize=True, paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            annotations=[dict(text=msg, xref="paper", yref="paper", x=0.5, y=0.5,
                              showarrow=False, font=dict(size=16, color=axis_color))],
        )
        return fig

    if x_ind == y_ind:
        return _placeholder("Pick two different indicators for the axes")

    dfy = data[data["year"] == year].dropna(subset=[x_ind, y_ind])
    if dfy.empty:
        return _placeholder(f"No overlapping {x_label} / {y_label} data for {year}")

    # Bubble size from Population (area-scaled), with a fallback for missing pop.
    pop = dfy["Population"]
    has_pop = pop.notna().sum() > 0
    if has_pop:
        pop_filled = pop.fillna(pop.median())
        sizeref = 2.0 * pop_filled.max() / (42.0 ** 2)

    def marker_for(sub, color, opacity, line):
        if has_pop:
            return dict(size=pop_filled.loc[sub.index], sizemode="area",
                        sizeref=sizeref, sizemin=4, color=color, opacity=opacity,
                        line=line)
        return dict(size=10, color=color, opacity=opacity, line=line)

    hover = ("<b>%{text}</b><br>" + x_label + ": %{x:,.2f}<br>"
             + y_label + ": %{y:,.2f}<extra></extra>")

    is_sel = dfy["Country"] == selected
    base, sel = dfy[~is_sel], dfy[is_sel]

    fig.add_trace(go.Scatter(
        x=base[x_ind], y=base[y_ind], mode="markers", text=base["Country"],
        marker=marker_for(base, "#4c78a8", 0.6, dict(width=0.5, color="white")),
        hovertemplate=hover, name="",
    ))
    if not sel.empty:
        fig.add_trace(go.Scatter(
            x=sel[x_ind], y=sel[y_ind], mode="markers+text", text=sel["Country"],
            textposition="top center", textfont=dict(color=axis_color),
            marker=marker_for(sel, "#e74c3c", 1.0, dict(width=2, color="white")),
            hovertemplate=hover, name="",
        ))

    # OLS trend line + Pearson r.
    x = dfy[x_ind].to_numpy(dtype=float)
    y = dfy[y_ind].to_numpy(dtype=float)
    r_txt = ""
    if len(x) >= 2:
        slope, intercept = np.polyfit(x, y, 1)
        xs = np.array([x.min(), x.max()])
        fig.add_trace(go.Scatter(
            x=xs, y=slope * xs + intercept, mode="lines", showlegend=False,
            line=dict(color="rgba(150,150,150,0.8)", dash="dash", width=2),
            hoverinfo="skip", name="trend",
        ))
        r_txt = f"  (r = {np.corrcoef(x, y)[0, 1]:.2f})"

    fig.update_layout(
        template=template, autosize=True, showlegend=False,
        hoverlabel=_hover_style(mode),
        margin=dict(l=60, r=25, t=55, b=50),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        title=dict(text=f"{y_label} vs {x_label} — {year}{r_txt}", x=0.02,
                   xanchor="left", font=dict(size=18)),
        xaxis=dict(title=x_label, showgrid=True, gridcolor="rgba(128,128,128,0.15)",
                   color=axis_color),
        yaxis=dict(title=y_label, showgrid=True, gridcolor="rgba(128,128,128,0.15)",
                   color=axis_color),
    )
    return fig


ABOUT_MD = """
## Global Health Indicators Dashboard
*Exploring health indicators around the globe*

---

### Problem Statement

Health and well-being indicators provide a comprehensive view of the progress and
challenges faced by populations worldwide. Metrics such as happiness scores,
depression prevalence, life expectancy, mortality rates, and population trends offer
insights into the socio-economic and health disparities across countries. This app
provides an interactive platform for exploring these key health indicators over time,
helping users identify patterns and relationships across different regions.

---

### Dataset Information

For this app, we follow several indicators to provide a unique lens for understanding
health and well-being:

- **Happiness Score** — overall life satisfaction from 0 to 10, based on survey responses. Higher scores indicate higher satisfaction.
- **Depression Prevalence** — estimated share of the population living with depression (%).
- **Adult Mortality** — the probability that a 15-year-old dies before reaching age 60, expressed per 1,000 people (World Bank adult mortality rate).
- **Life Expectancy** — measured from birth; estimates the average lifespan of individuals born in a given year.
- **Population** — total number of people residing in each country.

---

**Note:** The data spans 2010 to 2020 to ensure consistency across datasets. Each
dataset comes from a reliable source.

**Sources:**

- [World Happiness Report](https://worldhappiness.report/)
- [World Bank Group (Population & Mortality)](https://data.worldbank.org/)
- [Institute for Health Metrics and Evaluation (Depression Prevalence)](https://www.healthdata.org/)
- [World Health Organization (Life Expectancy)](https://www.who.int/data/gho)
"""


def info_modal():
    """Welcome / about modal shown on startup."""
    ui.modal_show(
        ui.modal(
            ui.markdown(ABOUT_MD),
            easy_close=True,
            size="l",
            footer=ui.modal_button("Explore the dashboard"),
        )
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
app_ui = ui.page_navbar(
    ui.nav_panel(
        "Country Profile",
        ui.layout_column_wrap(
            ui.value_box(
                "Happiness Score",
                ui.output_text("Happiness_Score"),
                theme="gradient-purple-indigo",
                showcase=icon_svg("face-smile"),
            ),
            ui.value_box(
                "Depression Prevalence",
                ui.output_text("Depression_Prevalence"),
                theme="gradient-blue-indigo",
                showcase=icon_svg("face-sad-cry"),
            ),
            ui.value_box(
                "Life Expectancy",
                ui.output_text("Life_Expectancy"),
                theme="gradient-green-indigo",
                showcase=icon_svg("heart-pulse"),
            ),
            ui.value_box(
                "Adult Mortality",
                ui.output_text("Mortality_Rate"),
                theme="gradient-red-indigo",
                showcase=icon_svg("skull"),
            ),
            ui.value_box(
                "Population",
                ui.output_text("Population"),
                theme="gradient-yellow-indigo",
                showcase=icon_svg("user"),
            ),
            fill=False,
        ),
        ui.card(
            ui.card_header("Selected country location"),
            ui.input_selectize(
                "basemap",
                "Basemap:",
                choices=list(BASEMAPS.keys()),
                selected="WorldImagery",
            ),
            output_widget("map"),
        ),
    ),
    ui.nav_panel(
        "Trends",
        ui.card(
            ui.card_header("Indicator trend, 2010–2020"),
            output_widget("trend_chart"),
        ),
    ),
    ui.nav_panel(
        "World Map",
        ui.card(
            ui.card_header("Indicator by country"),
            output_widget("choropleth"),
        ),
    ),
    ui.nav_panel(
        "Compare",
        ui.input_selectize(
            "compare_countries",
            "Countries to compare (2–5 works best):",
            choices=sorted(AVAILABLE_COUNTRIES),
            multiple=True,
            selected=["Japan", "United States", "Germany"],
        ),
        ui.card(
            ui.card_header("Country comparison over time"),
            output_widget("compare_chart"),
        ),
    ),
    ui.nav_panel(
        "Relationships",
        ui.card(
            ui.card_header("Indicator relationships across countries"),
            ui.layout_columns(
                ui.input_selectize(
                    "x_indicator",
                    "X axis:",
                    choices={col: label for col, (label, _) in INDICATOR_META.items()},
                    selected="Life_Expectancy",
                ),
                ui.input_selectize(
                    "y_indicator",
                    "Y axis:",
                    choices={col: label for col, (label, _) in INDICATOR_META.items()},
                    selected="Happiness_Score",
                ),
                col_widths=[6, 6],
                fill=False,
            ),
            ui.tags.p(
                "Each bubble is a country, and its size reflects population. The dashed "
                "line shows the overall trend, with the Pearson correlation (r) in the "
                "title — values near +1 or −1 indicate a strong relationship, and values "
                "near 0 indicate little. Your selected country is highlighted in red.",
                class_="text-muted",
                style="font-size: 0.9rem; margin-top: 0.25rem;",
            ),
            output_widget("scatter_chart"),
        ),
    ),
    sidebar=ui.sidebar(
        ui.input_selectize(
            "country_select",
            "Select Country:",
            choices=sorted(AVAILABLE_COUNTRIES),
            selected="Japan",
        ),
        ui.input_slider(
            "year_select",
            "Select Year:",
            min=int(data["year"].min()),
            max=int(data["year"].max()),
            value=int(data["year"].max()),
            step=1,
            ticks=True,
            sep="",
        ),
        ui.input_selectize(
            "indicator_select",
            "Trend Chart Indicator:",
            choices={col: label for col, (label, _) in INDICATOR_META.items()},
            selected="Life_Expectancy",
        ),
        ui.tags.div(
            ui.markdown(
                "**What the numbers mean**\n\n"
                "- **Happiness:** 0–10 scale (higher = happier)\n"
                "- **Depression:** share of people affected (%)\n"
                "- **Life Expectancy:** average lifespan, in years\n"
                "- **Adult Mortality:** chance of dying between 15 and 60, per 1,000\n"
                "- **Population:** total residents"
            ),
            class_="text-muted",
            style="font-size: 0.82rem; margin-top: 0.25rem;",
        ),
        ui.input_dark_mode(id="dark_mode", mode="dark"),
    ),
    title="Global Health Indicators Dashboard",
    fillable=True,
    id="main_tabs",
)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
def server(input, output, session):
    info_modal()

    # Single source of truth for which country is selected.
    selected_country = reactive.Value("Japan")
    current_coordinates = reactive.Value(country_centroid("Japan"))

    # Dropdown -> selected_country
    @reactive.Effect
    @reactive.event(input.country_select)
    def _on_dropdown():
        req(input.country_select())
        selected_country.set(input.country_select())

    # selected_country -> coordinates + keep the dropdown in sync.
    # The guard stops the update<->event loop after one cycle.
    @reactive.Effect
    def _sync_from_selected_country():
        country = selected_country()
        current_coordinates.set(country_centroid(country))
        if input.country_select() != country:
            ui.update_selectize("country_select", selected=country)

    # The single row for the current country + year (or None).
    @reactive.Calc
    def selected_data():
        country = selected_country()
        req(country, input.year_select())
        df = data[(data["Country"] == country) & (data["year"] == input.year_select())]
        return None if df.empty else df.iloc[0]

    @render_widget
    def map():
        lat, lon = current_coordinates()
        basemap = BASEMAPS.get(input.basemap(), basemaps.OpenStreetMap.Mapnik)  # type: ignore
        m = Map(basemap=basemap, center=(lat, lon), zoom=4, scroll_wheel_zoom=True)
        marker = Marker(location=(lat, lon), draggable=False)
        m.add_layer(marker)
        return m

    @render_plotly
    def trend_chart():
        country = selected_country()
        req(country)
        return build_trend_figure(
            country,
            input.indicator_select(),
            input.year_select(),
            input.dark_mode(),
        )

    @render_plotly
    def choropleth():
        return build_choropleth_figure(
            input.indicator_select(),
            input.year_select(),
            selected_country(),
            input.dark_mode(),
        )

    @render_plotly
    def compare_chart():
        return build_compare_figure(
            input.compare_countries(),
            input.indicator_select(),
            input.year_select(),
            input.dark_mode(),
        )

    @render_plotly
    def scatter_chart():
        return build_scatter_figure(
            input.x_indicator(),
            input.y_indicator(),
            input.year_select(),
            selected_country(),
            input.dark_mode(),
        )

    @render.text
    def Happiness_Score():
        row = selected_data()
        return _fmt(row["Happiness_Score"]) if row is not None else "N/A"

    @render.text
    def Depression_Prevalence():
        row = selected_data()
        return _fmt(row["Depression_Prevalence"], suffix="%") if row is not None else "N/A"

    @render.text
    def Life_Expectancy():
        row = selected_data()
        return _fmt(row["Life_Expectancy"], suffix=" years") if row is not None else "N/A"

    @render.text
    def Mortality_Rate():
        row = selected_data()
        return _fmt(row["Mortality_Rate"]) if row is not None else "N/A"

    @render.text
    def Population():
        row = selected_data()
        if row is None or pd.isna(row["Population"]):
            return "N/A"
        return f"{int(row['Population']):,}"


app = App(app_ui, server)
