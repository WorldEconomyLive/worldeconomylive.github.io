"""Development & environment: slow-moving annual indicators for every country, written to site/data/dev.json.

Only sources whose licence allows reuse with credit are used (each checked at the source):
World Bank WDI (CC BY 4.0, incl. FAO and ILO figures it republishes, both CC BY 4.0), Ember (CC BY 4.0), and
Our World in Data charts (OWID's processing CC BY 4.0) whose original data is itself open:
Maddison Project Database 2023 (CC BY 4.0), UNDP Human Development Report (CC BY 3.0 IGO),
Global Carbon Project (CC BY 4.0), Penn World Table 11.0 (CC BY 4.0), Jones et al. (CC BY 4.0).
Left out on purpose: Energy Institute Statistical Review (no licence stated), WHO-led series (non-commercial),
UNESCO UIS direct (share-alike), WID (no licence found).
"""
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import sources as S

# key: (source, code, label, unit, better (+1 higher is better, -1 lower is better, 0 neutral), decimals, credit)
DEV = {
    "rd":           ("wb", "GB.XPD.RSDV.GD.ZS", "R&D spending", "% of GDP", 1, 2,
                     "UNESCO Institute for Statistics (CC BY-SA 3.0 IGO), via World Bank World Development Indicators. Gross domestic spending on research and development."),
    "poverty":      ("wb", "SI.POV.DDAY", "Extreme poverty", "% of people", -1, 1,
                     "World Bank, Poverty and Inequality Platform (via World Development Indicators), CC BY 4.0. Share living below the World Bank's international poverty line."),
    "gdp_pc_long":  ("owid", "gdp-per-capita-maddison-project-database", "Income per person, long run", "int.-$ (2011 prices)", 1, 0,
                     "Bolt and van Zanden, Maddison Project Database 2023, CC BY 4.0 – with minor processing by Our World in Data."),
    "productivity": ("owid", "labor-productivity-per-hour-pennworldtable", "Output per hour worked", "int.-$ (2021 prices)", 1, 1,
                     "Feenstra, Inklaar and Timmer, Penn World Table 11.0, CC BY 4.0 (www.ggdc.net/pwt) – with major processing by Our World in Data."),
    "hdi":          ("owid", "human-development-index", "Human Development Index", "0–1", 1, 3,
                     "UNDP, Human Development Report, CC BY 3.0 IGO – with minor processing by Our World in Data."),
    "child_mort":   ("wb", "SH.DYN.MORT", "Child deaths before age 5", "per 1,000 births", -1, 1,
                     "UN Inter-agency Group for Child Mortality Estimation, via World Bank World Development Indicators, CC BY 4.0."),
    "school":       ("wb", "HD.HCI.LAYS", "Learning-adjusted years of school", "years", 1, 1,
                     "World Bank, Human Capital Index (via World Development Indicators), CC BY 4.0."),
    "undernourish": ("wb", "SN.ITK.DEFC.ZS", "Undernourished", "% of people", -1, 1,
                     "FAO, via World Bank World Development Indicators, CC BY 4.0."),
    "labor_part":   ("wb", "SL.TLF.CACT.ZS", "Labour force participation", "% of people 15+", 1, 1,
                     "ILO modelled estimates (ILOSTAT, CC BY 4.0), via World Bank World Development Indicators."),
    "female_lab":   ("wb", "SL.TLF.CACT.FE.ZS", "Women in the labour force", "% of women 15+", 1, 1,
                     "ILO modelled estimates (ILOSTAT, CC BY 4.0), via World Bank World Development Indicators."),
    "co2_pc":       ("owid", "co-emissions-per-capita", "CO₂ per person", "tonnes", -1, 2,
                     "Global Carbon Project, Global Carbon Budget, CC BY 4.0 – with major processing by Our World in Data."),
    "clean_elec":   ("ember", "clean", "Low-carbon electricity", "% of generation", 1, 1,
                     "Ember, Monthly Electricity Data, CC BY 4.0: renewables and nuclear as a share of generation, summed over each complete year by this site."),
    "warming":      ("owid", "contribution-temp-rise-degrees", "Contribution to global warming", "°C since 1850", -1, 3,
                     "Jones et al., National contributions to climate change, CC BY 4.0 – with major processing by Our World in Data."),
}
SINCE = 1960


def _fetch(key):
    src, code = DEV[key][0], DEV[key][1]
    if src == "wb":
        return S.worldbank_all(code, since=SINCE), f"wb:{code}"
    if src == "owid":
        return S.owid_grapher(code), f"owid:{code}"
    df = S.EMBER_CLEAN.get("df")
    if df is None:
        raise RuntimeError("Ember clean share not available")
    return df, "ember"


def build(names):
    """names: {iso3: display name} for every map country. Returns the dev.json object."""
    data, rel = {}, {}
    with ThreadPoolExecutor(4) as ex:
        fut = {k: ex.submit(_fetch, k) for k in DEV}
    for k, f in fut.items():
        try:
            df, rk = f.result()
            df = df[(df.year >= SINCE) & df.iso3.isin(names)]
            for iso3, g in df.groupby("iso3"):
                g = g.sort_values("year").drop_duplicates("year", keep="last")
                y0, y1 = int(g.year.iloc[0]), int(g.year.iloc[-1])
                by = dict(zip(g.year.astype(int), g.value.astype(float)))
                data.setdefault(iso3, {})[k] = [y0, [None if by.get(y) is None else float(f"{by[y]:.4g}") for y in range(y0, y1 + 1)]]
            rel[k] = rk
            S.log(f"dev.{k}", True, f"{df.iso3.nunique()} countries")
        except Exception as e:
            S.log(f"dev.{k}", False, e)
    keys = {k: {"label": v[2], "unit": v[3], "better": v[4], "dec": v[5], "credit": v[6], "rel": rel.get(k),
                "src": v[0]} for k, v in DEV.items() if k in rel}
    return {"keys": keys, "data": data, "names": {i: names[i] for i in data},
            "rel": {rk: S.REL.get(rk) for rk in rel.values() if S.REL.get(rk)}}
