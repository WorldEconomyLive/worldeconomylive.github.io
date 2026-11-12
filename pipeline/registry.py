"""What we track. Add an economy or indicator here and it flows through the whole site.

Each monthly indicator lists candidate sources, tried in order. The first one that
returns fresh data (last point within MAX_STALE_MONTHS) wins. This keeps the site
alive when any single source changes a code.
"""

MAX_STALE_MONTHS = 15

ECONOMIES = {
    # iso3: (name, iso2, eurostat geo or None, flag of euro area member)
    "USA": ("United States", "US", None),
    "CHN": ("China", "CN", None),
    "JPN": ("Japan", "JP", None),
    "DEU": ("Germany", "DE", "DE"),
    "GBR": ("United Kingdom", "GB", None),
    "FRA": ("France", "FR", "FR"),
    "ITA": ("Italy", "IT", "IT"),
    "CAN": ("Canada", "CA", None),
    "IND": ("India", "IN", None),
}


def monthly_candidates(iso3):
    """Return {indicator: [(kind, code), ...]} for one economy.
    kinds: fred, fred_yoy, dbn, dbn_yoy (yoy = compute 12-month % change)."""
    name, iso2, geo = ECONOMIES[iso3]
    bis = "XM" if geo else iso2  # euro members share the ECB rate
    c = {"gdp": [], "inflation": [], "unemployment": [], "industry": [], "policy_rate": [],
         "long_rate": []}

    if iso3 == "USA":
        c["inflation"] += [("fred_yoy", "CPIAUCSL")]
        c["unemployment"] += [("fred", "UNRATE")]
        c["industry"] += [("fred_yoy", "INDPRO")]
        c["policy_rate"] += [("fred", "FEDFUNDS")]
        c["gdp"] += [("fred_yoyq", "GDPC1")]
        c["long_rate"] += [("fred", "GS10")]
    if geo:
        c["inflation"] += [("dbn", f"Eurostat/prc_hicp_manr/M.RCH_A.CP00.{geo}")]
        c["unemployment"] += [("dbn", f"Eurostat/une_rt_m/M.SA.TOTAL.PC_ACT.T.{geo}")]
        c["industry"] += [("dbn_yoy", f"Eurostat/sts_inpr_m/M.PROD.B-D.SCA.I21.{geo}"),
                          ("dbn_yoy", f"Eurostat/sts_inpr_m/M.PROD.B-D.SCA.I15.{geo}")]
        c["gdp"] += [("dbn", f"Eurostat/namq_10_gdp/Q.CLV_PCH_SM.SCA.B1GQ.{geo}")]
    # OECD mirrors on FRED (broad coverage; some may be stale -> skipped automatically)
    c["gdp"] += [("fred", f"NAEXKP01{iso2}Q659S"), ("fred_yoyq", f"NGDPRSAXDC{iso2}Q")]
    c["long_rate"] += [("fred", f"IRLTLT01{iso2}M156N")]
    c["inflation"] += [("fred", f"CPALTT01{iso2}M659N")]
    c["unemployment"] += [("fred", f"LRHUTTTT{iso2}M156S")]
    c["industry"] += [("fred_yoy", f"PRINTO01{iso2}M661S")]
    # BIS central bank policy rates via DBnomics
    c["policy_rate"] += [("dbn", f"BIS/WS_CBPOL/M.{bis}"), ("dbn", f"BIS/WS_CBPOL_M/M.{bis}")]
    return c


# Annual "vital signs" from the World Bank (people, health, structure). Always available.
VITALS = {
    "population":        ("SP.POP.TOTL",       "Population", "people"),
    "pop_growth":        ("SP.POP.GROW",       "Population growth", "%"),
    "age65":             ("SP.POP.65UP.TO.ZS", "Aged 65+", "% of pop."),
    "fertility":         ("SP.DYN.TFRT.IN",    "Births per woman", ""),
    "life_exp":          ("SP.DYN.LE00.IN",    "Life expectancy", "years"),
    "health_spend":      ("SH.XPD.CHEX.GD.ZS", "Health spending", "% of GDP"),
    "net_migration":     ("SM.POP.NETM",       "Net migration", "people"),
    "gdp_pc":            ("NY.GDP.PCAP.CD",    "GDP per person", "US$"),
    "gdp_growth":        ("NY.GDP.MKTP.KD.ZG", "GDP growth", "%"),
    "inflation_a":       ("FP.CPI.TOTL.ZG",    "Inflation (annual)", "%"),
    "unemployment_a":    ("SL.UEM.TOTL.ZS",    "Unemployment (annual)", "%"),
    "trade_open":        ("NE.TRD.GNFS.ZS",    "Trade", "% of GDP"),
    "gini":              ("SI.POV.GINI",       "Inequality (Gini)", "0-100"),
}

# Commodity and freight prices (FRED). Grouped by the ship type that carries them.
PRICES = {
    "Brent crude":        ("DCOILBRENTEU",    "tanker"),
    "WTI crude":          ("DCOILWTICO",      "tanker"),
    "US natural gas":     ("DHHNGSP",         "tanker"),
    "Asia LNG":           ("PNGASJPUSDM",     "tanker"),
    "Iron ore":           ("PIORECRUSDM",     "dry_bulk"),
    "Coal":               ("PCOALAUUSDM",     "dry_bulk"),
    "Wheat":              ("PWHEAMTUSDM",     "dry_bulk"),
    "Soybeans":           ("PSOYBUSDM",       "dry_bulk"),
    "Copper":             ("PCOPPUSDM",       "dry_bulk"),
    "US import prices":   ("IR",              "container"),
    "Ocean freight cost": ("PCU483111483111", None),
    "Truckload cost":     ("PCU484121484121", None),
}

# US high-frequency activity (FRED). Public-domain series only on the public site.
US_FAST = {
    "Jobless claims (weekly)": "ICSA",
    "Rail carloads":           "RAILFRTCARLOADSD11",
    "Rail intermodal":         "RAILFRTINTERMODAL",
    "Freight services index":  "TSIFRGHT",
    "Consumer sentiment":      "UMCSENT",
}

# Port regions (ISO3 lists). Top ports by traffic are picked automatically.
REGIONS = {
    "China": ["CHN", "HKG"], "NE Asia": ["JPN", "KOR", "TWN"],
    "SE Asia": ["SGP", "MYS", "VNM", "THA", "IDN", "PHL"],
    "South Asia": ["IND", "PAK", "BGD", "LKA"], "Middle East": ["ARE", "SAU", "OMN", "QAT"],
    "Europe": ["NLD", "BEL", "DEU", "ESP", "FRA", "ITA", "GBR", "GRC", "POL"],
    "US": ["USA"], "LatAm": ["BRA", "MEX", "CHL", "PER", "COL", "PAN"],
    "Africa": ["ZAF", "EGY", "MAR", "NGA", "KEN"],
}
PORTS_PER_REGION = 5
PORTS_PER_ECONOMY = 4
PRODUCTS = {
    "tanker": "Oil, fuel, gas, chemicals",
    "container": "Manufactured goods",
    "dry_bulk": "Ores, coal, grain",
    "general_cargo": "Steel, project cargo",
    "roro": "Vehicles",
}
CHOKEPOINTS = {
    "chokepoint1": "Suez Canal", "chokepoint2": "Panama Canal", "chokepoint3": "Bosporus",
    "chokepoint4": "Bab el-Mandeb", "chokepoint5": "Malacca Strait", "chokepoint6": "Strait of Hormuz",
    "chokepoint7": "Cape of Good Hope", "chokepoint8": "Gibraltar", "chokepoint9": "Dover Strait",
    "chokepoint10": "Oresund", "chokepoint11": "Taiwan Strait", "chokepoint12": "Korea Strait",
    "chokepoint13": "Tsugaru Strait", "chokepoint14": "Luzon Strait", "chokepoint15": "Lombok Strait",
    "chokepoint16": "Ombai Strait", "chokepoint17": "Bohai Strait", "chokepoint18": "Torres Strait",
    "chokepoint19": "Sunda Strait", "chokepoint20": "Makassar Strait", "chokepoint21": "Magellan Strait",
    "chokepoint22": "Yucatan Channel", "chokepoint23": "Windward Passage", "chokepoint24": "Mona Passage",
}
WINDOW_DAYS = 28   # YoY comparison window for port/chokepoint data
LAG_DAYS = 10      # PortWatch fills in late; ignore the most recent days


# Markets: daily/monthly series from FRED. Shown as latest, 1-month and 1-year change.
# NOTE: equity index levels are licensed by their owners (S&P, Nasdaq, Nikkei). We show
# % changes only, with attribution. Review before any commercial use.
MARKETS = {
    "FX (per US dollar unless noted)": {
        "Euro (USD per EUR)": "DEXUSEU", "British pound (USD per GBP)": "DEXUSUK",
        "Japanese yen": "DEXJPUS", "Chinese yuan": "DEXCHUS", "Indian rupee": "DEXINUS",
        "Canadian dollar": "DEXCAUS", "Swiss franc": "DEXSZUS", "Korean won": "DEXKOUS",
        "Mexican peso": "DEXMXUS", "Brazilian real": "DEXBZUS",
        "Broad dollar index": "DTWEXBGS",
    },
    "US rates": {
        "Fed funds": "DFF", "3-month T-bill": "DTB3", "2-year Treasury": "DGS2",
        "10-year Treasury": "DGS10", "30-year Treasury": "DGS30",
        "10y minus 2y spread": "T10Y2Y", "30-year mortgage": "MORTGAGE30US",
        "High-yield credit spread": "BAMLH0A0HYM2", "Inflation expectations (10y)": "T10YIE",
    },
    "Equity indices": {
        "S&P 500": "SP500", "Nasdaq Composite": "NASDAQCOM", "Dow Jones": "DJIA",
        "Nikkei 225": "NIKKEI225", "VIX (volatility)": "VIXCLS",
    },
    "More commodities": {
        "Aluminum": "PALUMUSDM", "Nickel": "PNICKUSDM", "Corn": "PMAIZMTUSDM",
        "Rice": "PRICENPQUSDM", "Sugar": "PSUGAISAUSDM", "Coffee": "PCOFFOTMUSDM",
        "Cotton": "PCOTTINDUSDM", "Beef": "PBEEFUSDQ", "Natural gas (Europe)": "PNGASEUUSDM",
        "Fertilizer (urea)": "PUREAUSDM",
    },
}
