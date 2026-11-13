"""What World Economy Live tracks. Add an economy or series here and it flows to the site.

Monthly data is fetched in BATCHES (one request per dataset for all economies) to stay
within source rate limits. Annual data (IMF WEO, World Bank) is fetched for every country.
"""

MAX_STALE_MONTHS = 15     # older than this = not used
FRESH_MONTHS = 4          # a source this fresh is accepted immediately; otherwise keep looking

# Economies with monthly tracking: OECD members + major partners.
# iso3: (name, iso2, eurostat geo or None if not in EU)
ECONOMIES = {
    "USA": ("United States", "US", None), "CHN": ("China", "CN", None), "JPN": ("Japan", "JP", None),
    "DEU": ("Germany", "DE", "DE"), "IND": ("India", "IN", None), "GBR": ("United Kingdom", "GB", None),
    "FRA": ("France", "FR", "FR"), "ITA": ("Italy", "IT", "IT"), "CAN": ("Canada", "CA", None),
    "BRA": ("Brazil", "BR", None), "KOR": ("South Korea", "KR", None), "AUS": ("Australia", "AU", None),
    "MEX": ("Mexico", "MX", None), "ESP": ("Spain", "ES", "ES"), "IDN": ("Indonesia", "ID", None),
    "TUR": ("Turkey", "TR", None), "SAU": ("Saudi Arabia", "SA", None), "NLD": ("Netherlands", "NL", "NL"),
    "CHE": ("Switzerland", "CH", None), "POL": ("Poland", "PL", "PL"), "ARG": ("Argentina", "AR", None),
    "BEL": ("Belgium", "BE", "BE"), "SWE": ("Sweden", "SE", "SE"), "IRL": ("Ireland", "IE", "IE"),
    "AUT": ("Austria", "AT", "AT"), "ISR": ("Israel", "IL", None), "NOR": ("Norway", "NO", None),
    "ZAF": ("South Africa", "ZA", None), "DNK": ("Denmark", "DK", "DK"), "COL": ("Colombia", "CO", None),
    "CHL": ("Chile", "CL", None), "FIN": ("Finland", "FI", "FI"), "CZE": ("Czechia", "CZ", "CZ"),
    "PRT": ("Portugal", "PT", "PT"), "NZL": ("New Zealand", "NZ", None), "GRC": ("Greece", "GR", "EL"),
    "HUN": ("Hungary", "HU", "HU"), "SVK": ("Slovakia", "SK", "SK"), "LUX": ("Luxembourg", "LU", "LU"),
    "SVN": ("Slovenia", "SI", "SI"), "LTU": ("Lithuania", "LT", "LT"), "LVA": ("Latvia", "LV", "LV"),
    "EST": ("Estonia", "EE", "EE"), "CRI": ("Costa Rica", "CR", None), "ISL": ("Iceland", "IS", None),
}
EURO = {"DEU", "FRA", "ITA", "ESP", "NLD", "BEL", "IRL", "AUT", "FIN", "PRT", "GRC", "SVK", "LUX", "SVN", "LTU", "LVA", "EST"}
G20 = ["USA", "CHN", "JPN", "DEU", "IND", "GBR", "FRA", "ITA", "CAN", "BRA", "KOR", "AUS", "MEX", "IDN", "TUR", "SAU", "ARG", "ZAF"]

# ---------------- OECD monthly / quarterly datasets (batched) ----------------
# filters: fixed dimension values (REF_AREA is filled with all economies).
# prefer: ordered acceptable values per column; "_strict" columns must match or the row is dropped.
# transform: level | yoy | yoyq ; if the chosen row already has TRANSFORMATION GY it is used as-is.
IMTS_FILTERS = [{"FREQ": "M", "COUNTERPART_AREA": "W"}, {"FREQ": "M", "COUNTERPART_AREA": "W00"}, {"FREQ": "M"}]
OECD_SPECS = {
    "inflation": {"flow": "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
                  "key": "{areas}.M.N.CPI.PA._T.N.GY", "transform": "level"},
    "unemployment": {"flow": "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0",
                     "key": "{areas}.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.M", "transform": "level"},
    "industry": {"flow": "OECD.SDD.STES,DSD_STES@DF_INDSERV",
                 "filters": {"FREQ": "M", "MEASURE": "PRVM"},
                 "prefer": {"ACTIVITY": ["BTE", "B-E", "C"], "ADJUSTMENT": ["Y", "S", "N"],
                            "TRANSFORMATION": ["_Z", "N", "GY"], "_strict": ["ACTIVITY"]},
                 "transform": "yoy", "bounds": 40},
    "gdp": {"flow": "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA",
            "filters": {"FREQ": "Q", "SECTOR": "S1", "TRANSACTION": "B1GQ"},
            "prefer": {"PRICE_BASE": ["LR", "L"], "ADJUSTMENT": ["Y", "S"], "TRANSFORMATION": ["N", "_Z", "GY"],
                       "UNIT_MEASURE": ["XDC", "USD_PPP", "USD_EXC"], "_strict": ["PRICE_BASE"]},
            "transform": "yoyq", "bounds": 25},
    "long_rate": {"flow": "OECD.SDD.STES,DSD_STES@DF_FINMARK",
                  "filters": {"FREQ": "M", "MEASURE": "IRLT"}, "prefer": {}, "transform": "level", "bounds": 60},
    "short_rate": {"flow": "OECD.SDD.STES,DSD_STES@DF_FINMARK",
                   "filters": {"FREQ": "M", "MEASURE": "IR3TIB"}, "prefer": {}, "transform": "level", "bounds": 80},
    "exports_usd": {"flow": "OECD.SDD.TPS,DSD_IMTS@DF_IMTS",
                    "filters_alt": IMTS_FILTERS,
                    "prefer": {"TRADE_FLOW": ["X", "C"], "FLOW": ["X", "C"], "COUNTERPART_AREA": ["W", "W00", "WLD"],
                               "UNIT_MEASURE": ["USD", "USD_EXC"], "ADJUSTMENT": ["Y", "S", "N"],
                               "TRANSFORMATION": ["_Z", "N"], "_strict": ["TRADE_FLOW", "FLOW", "UNIT_MEASURE"]},
                    "transform": "usd_bn"},
    "imports_usd": {"flow": "OECD.SDD.TPS,DSD_IMTS@DF_IMTS",
                    "filters_alt": IMTS_FILTERS,
                    "prefer": {"TRADE_FLOW": ["M", "D"], "FLOW": ["M", "D"], "COUNTERPART_AREA": ["W", "W00", "WLD"],
                               "UNIT_MEASURE": ["USD", "USD_EXC"], "ADJUSTMENT": ["Y", "S", "N"],
                               "TRANSFORMATION": ["_Z", "N"], "_strict": ["TRADE_FLOW", "FLOW", "UNIT_MEASURE"]},
                    "transform": "usd_bn"},
}

# Per-economy fallbacks if OECD has nothing fresh: Eurostat (EU), World Bank annual (all).
def fallbacks(iso3):
    name, iso2, geo = ECONOMIES[iso3]
    f = {"inflation": [], "unemployment": [], "industry": [], "gdp": []}
    if geo:
        f["inflation"] += [("dbn", f"Eurostat/prc_hicp_manr/M.RCH_A.CP00.{geo}", "level")]
        f["unemployment"] += [("dbn", f"Eurostat/une_rt_m/M.SA.TOTAL.PC_ACT.T.{geo}", "level")]
        f["industry"] += [("dbn", f"Eurostat/sts_inpr_m/M.{i}.B-D.SCA.{u}.{geo}", "yoy") for i in ("PRD", "PROD") for u in ("I21", "I15")]
        f["gdp"] += [("dbn", f"Eurostat/namq_10_gdp/Q.CLV_PCH_SM.{sa}.B1GQ.{geo}", "level") for sa in ("SCA", "NSA")]
    f["inflation"] += [("wb", "FP.CPI.TOTL.ZG", "level")]
    f["unemployment"] += [("wb", "SL.UEM.TOTL.ZS", "level")]
    f["gdp"] += [("wb", "NY.GDP.MKTP.KD.ZG", "level")]
    return f


# ---------------- Annual: IMF World Economic Outlook (all countries, via DBnomics) ----------------
WEO_RELEASES = ["WEO:latest", "WEO:2026-10", "WEO:2026-04", "WEO:2025-10"]
WEO = {  # key: (WEO subject.unit, label, unit, scale)
    "gdp_growth":      ("NGDP_RPCH.pcent_change", "Real GDP growth", "%", 1),
    "inflation_a":     ("PCPIPCH.pcent_change", "Inflation (annual avg.)", "%", 1),
    "unemployment_a":  ("LUR.pcent_total_labor_force", "Unemployment", "%", 1),
    "gdp_usd":         ("NGDPD.us_dollars", "GDP", "US$", 1e9),
    "gov_debt":        ("GGXWDG_NGDP.pcent_gdp", "Government debt", "% of GDP", 1),
    "gov_balance":     ("GGXCNL_NGDP.pcent_gdp", "Budget balance", "% of GDP", 1),
    "primary_balance": ("GGXONLB_NGDP.pcent_gdp", "Primary balance", "% of GDP", 1),
    "revenue":         ("GGR_NGDP.pcent_gdp", "Government revenue", "% of GDP", 1),
    "spending":        ("GGX_NGDP.pcent_gdp", "Government spending", "% of GDP", 1),
    "current_account": ("BCA_NGDPD.pcent_gdp", "Current account", "% of GDP", 1),
    "savings":         ("NGSD_NGDP.pcent_gdp", "National savings (S)", "% of GDP", 1),
    "investment_weo":  ("NID_NGDP.pcent_gdp", "Total investment", "% of GDP", 1),
}

# ---------------- Annual: World Bank WDI (all countries, CC BY 4.0) ----------------
WB = {  # key: (indicator, label, unit)
    "population":      ("SP.POP.TOTL", "Population", "people"),
    "pop_growth":      ("SP.POP.GROW", "Population growth", "%"),
    "age65":           ("SP.POP.65UP.TO.ZS", "Aged 65+", "% of pop."),
    "fertility":       ("SP.DYN.TFRT.IN", "Births per woman", ""),
    "life_exp":        ("SP.DYN.LE00.IN", "Life expectancy", "years"),
    "health_spend":    ("SH.XPD.CHEX.GD.ZS", "Health spending", "% of GDP"),
    "net_migration":   ("SM.POP.NETM", "Net migration", "people"),
    "gdp_pc":          ("NY.GDP.PCAP.CD", "GDP per person", "US$"),
    "gini":            ("SI.POV.GINI", "Inequality (Gini)", "0-100"),
    "urban":           ("SP.URB.TOTL.IN.ZS", "Urban population", "% of pop."),
    "exports_usd_a":   ("NE.EXP.GNFS.CD", "Exports, goods & services", "US$"),
    "imports_usd_a":   ("NE.IMP.GNFS.CD", "Imports, goods & services", "US$"),
    "net_exports":     ("NE.RSB.GNFS.ZS", "Net exports (X − M)", "% of GDP"),
    "consumption":     ("NE.CON.PRVT.ZS", "Household consumption (C)", "% of GDP"),
    "investment":      ("NE.GDI.TOTL.ZS", "Investment (I)", "% of GDP"),
    "gov_consumption": ("NE.CON.GOVT.ZS", "Government consumption (G)", "% of GDP"),
    "reserves_usd":    ("FI.RES.TOTL.CD", "FX reserves", "US$"),
    "reserves_months": ("FI.RES.TOTL.MO", "Reserves", "months of imports"),
    "private_credit":  ("FS.AST.PRVT.GD.ZS", "Bank credit to private sector", "% of GDP"),
    "debt_wb":         ("GC.DOD.TOTL.GD.ZS", "Central government debt", "% of GDP"),
    # World Bank stand-ins where the IMF WEO has no series for a country (they count toward scores)
    "gdp_growth_wb":   ("NY.GDP.MKTP.KD.ZG", "GDP growth", "%"),
    "inflation_wb":    ("FP.CPI.TOTL.ZG", "Inflation (consumer prices)", "%"),
    "unemployment_wb": ("SL.UEM.TOTL.ZS", "Unemployment (ILO estimate)", "%"),
    "gdp_usd_wb":      ("NY.GDP.MKTP.CD", "GDP", "US$"),
}
WB_FALLBACK = {"gdp_growth": "gdp_growth_wb", "inflation_a": "inflation_wb", "unemployment_a": "unemployment_wb",
               "gdp_usd": "gdp_usd_wb", "gov_debt": "debt_wb"}
# Scores on annual data use completed calendar years only (never the current-year forecast), and need
# a completed year no older than this many years before the view year.
ANNUAL_MAX_AGE = 2
VITAL_KEYS = ["population", "pop_growth", "age65", "fertility", "life_exp", "health_spend", "net_migration", "gdp_pc", "gini", "urban"]

# ---------------- Commodities (World Bank Pink Sheet) ----------------
COMMODITIES = [
    ("Crude oil, Brent", "Brent crude", "tanker", "$/bbl"), ("Crude oil, WTI", "WTI crude", "tanker", "$/bbl"),
    ("Natural gas, US", "US natural gas", "tanker", "$/mmbtu"), ("Natural gas, Europe", "Europe natural gas", "tanker", "$/mmbtu"),
    ("Liquefied natural gas, Japan", "Asia LNG", "tanker", "$/mmbtu"), ("Coal, Australia", "Coal", "dry_bulk", "$/mt"),
    ("Iron ore", "Iron ore", "dry_bulk", "$/dmtu"), ("Copper", "Copper", "dry_bulk", "$/mt"),
    ("Aluminum", "Aluminum", "dry_bulk", "$/mt"), ("Nickel", "Nickel", "dry_bulk", "$/mt"),
    ("Wheat, US HRW", "Wheat", "dry_bulk", "$/mt"), ("Maize", "Corn", "dry_bulk", "$/mt"),
    ("Rice, Thai 5", "Rice", "dry_bulk", "$/mt"), ("Soybeans", "Soybeans", "dry_bulk", "$/mt"),
    ("Sugar, world", "Sugar", "dry_bulk", "$/kg"), ("Coffee, Arabica", "Coffee", "container", "$/kg"),
    ("Cocoa", "Cocoa", "container", "$/kg"), ("Cotton", "Cotton", "container", "$/kg"),
    ("Beef", "Beef", "container", "$/kg"), ("Urea", "Fertilizer (urea)", "dry_bulk", "$/mt"),
    ("Gold", "Gold", None, "$/troy oz"), ("Silver", "Silver", None, "$/troy oz"),
]

# ---------------- FX (ECB reference rates, quoted per 1 EUR at 14:15 CET) ----------------
FX = ["USD", "GBP", "JPY", "CNY", "INR", "CAD", "CHF", "KRW", "MXN", "BRL", "AUD", "ZAR", "TRY", "IDR", "SEK", "NOK", "PLN", "NZD", "SGD", "HKD"]
FX_NAMES = {"EUR": "Euro", "GBP": "British pound", "JPY": "Japanese yen", "CNY": "Chinese yuan", "INR": "Indian rupee",
            "CAD": "Canadian dollar", "CHF": "Swiss franc", "KRW": "Korean won", "MXN": "Mexican peso", "BRL": "Brazilian real",
            "AUD": "Australian dollar", "ZAR": "South African rand", "TRY": "Turkish lira", "IDR": "Indonesian rupiah",
            "SEK": "Swedish krona", "NOK": "Norwegian krone", "PLN": "Polish zloty", "NZD": "New Zealand dollar",
            "SGD": "Singapore dollar", "HKD": "Hong Kong dollar"}
FX_UNITS = {"EUR": "euro", "GBP": "pound", "JPY": "yen", "CNY": "yuan", "INR": "rupees", "CAD": "Canadian dollars",
            "CHF": "Swiss francs", "KRW": "won", "MXN": "Mexican pesos", "BRL": "reais", "AUD": "Australian dollar",
            "ZAR": "rand", "TRY": "lira", "IDR": "rupiah", "SEK": "kronor", "NOK": "kroner", "PLN": "zloty",
            "NZD": "New Zealand dollar", "SGD": "Singapore dollars", "HKD": "Hong Kong dollars"}
FX_BASE_IS_FOREIGN = {"EUR", "GBP", "AUD", "NZD"}   # market convention: quoted as USD per 1 unit

# ---------------- PortWatch ----------------
REGIONS = {
    "China": ["CHN", "HKG"], "NE Asia": ["JPN", "KOR", "TWN"],
    "SE Asia": ["SGP", "MYS", "VNM", "THA", "IDN", "PHL"], "South Asia": ["IND", "PAK", "BGD", "LKA"],
    "Middle East": ["ARE", "SAU", "OMN", "QAT", "KWT", "IRN", "IRQ"],
    "Europe": ["NLD", "BEL", "DEU", "ESP", "FRA", "ITA", "GBR", "GRC", "POL", "PRT", "SWE", "NOR", "DNK", "FIN", "IRL", "TUR"],
    "US": ["USA"], "Canada": ["CAN"], "LatAm": ["BRA", "MEX", "CHL", "PER", "COL", "PAN", "ARG", "ECU", "URY"],
    "Africa": ["ZAF", "EGY", "MAR", "NGA", "KEN", "GHA", "TZA", "AGO", "DZA"], "Oceania": ["AUS", "NZL"],
}
PORTS_PER_REGION, PORTS_PER_ECONOMY = 5, 2
PRODUCTS = {"tanker": "Oil, fuel, gas, chemicals", "container": "Manufactured goods",
            "dry_bulk": "Ores, coal, grain", "general_cargo": "Steel, project cargo", "roro": "Vehicles"}
CHOKEPOINTS = {  # id: (name, lon, lat)
    "chokepoint1": ("Suez Canal", 32.35, 30.6), "chokepoint2": ("Panama Canal", -79.7, 9.1),
    "chokepoint3": ("Bosporus", 29.05, 41.1), "chokepoint4": ("Bab el-Mandeb", 43.4, 12.6),
    "chokepoint5": ("Malacca Strait", 100.4, 3.2), "chokepoint6": ("Strait of Hormuz", 56.4, 26.6),
    "chokepoint7": ("Cape of Good Hope", 18.5, -34.4), "chokepoint8": ("Gibraltar", -5.6, 35.95),
    "chokepoint9": ("Dover Strait", 1.45, 51.0), "chokepoint10": ("Oresund", 12.7, 55.9),
    "chokepoint11": ("Taiwan Strait", 119.5, 24.3), "chokepoint12": ("Korea Strait", 129.0, 34.5),
    "chokepoint13": ("Tsugaru Strait", 140.6, 41.5), "chokepoint14": ("Luzon Strait", 121.0, 20.5),
    "chokepoint15": ("Lombok Strait", 115.7, -8.6), "chokepoint16": ("Ombai Strait", 125.0, -8.4),
    "chokepoint17": ("Bohai Strait", 121.0, 38.3), "chokepoint18": ("Torres Strait", 142.4, -10.3),
    "chokepoint19": ("Sunda Strait", 105.8, -6.0), "chokepoint20": ("Makassar Strait", 118.0, -2.0),
    "chokepoint21": ("Magellan Strait", -70.5, -53.5), "chokepoint22": ("Yucatan Channel", -85.8, 21.8),
    "chokepoint23": ("Windward Passage", -73.9, 20.0), "chokepoint24": ("Mona Passage", -67.8, 18.3),
}
WINDOW_DAYS, LAG_DAYS = 28, 10

# ---------------- Release timing for viewing past dates ----------------
# When the site is rebuilt for a past date, a figure counts as released this many days after the end of the
# period it covers (each source's usual publication delay). Annual sources have their own rules below.
LAGS = {
    "oecd:DSD_PRICES@DF_PRICES_ALL": 40, "oecd:DSD_LFS@DF_IALFS_UNE_M": 45, "oecd:DSD_STES@DF_INDSERV": 45,
    "oecd:DSD_NAMAIN1@DF_QNA": 60, "oecd:DSD_STES@DF_FINMARK": 10, "oecd:DSD_IMTS@DF_IMTS": 50,
    "bis": 5, "dbn:Eurostat/prc_hicp_manr": 20, "dbn:Eurostat/une_rt_m": 30, "dbn:Eurostat/sts_inpr_m": 45,
    "dbn:Eurostat/namq_10_gdp": 45, "pink": 5, "ecb": 0, "treasury": 0, "nyfed": 1, "fiscaldata": 1, "mts": 12,
    "ember": 45, "bts": 75, "eurostat:avia_gooc": 100, "eurostat:rail_go_quartal": 120, "statcan": 55, "portwatch": 7,
}
DEFAULT_LAG = 45
# IMF WEO: figures for year Y count as released with the October WEO of year Y (15 October).
# World Bank WDI: figures for year Y count as released on 1 July of year Y+1.
WEO_RELEASE_MD, WB_RELEASE_MD = (10, 15), (7, 1)
HISTORY_START = "1980-01-01"     # first day the score rebuild looks at
