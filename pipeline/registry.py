"""What World Economy Live tracks. Add an economy or series here and it flows to the site.

Monthly indicators list candidate sources tried in order; the first with fresh data wins.
Kinds:
  ("oecd_key", flow, key, transform)        exact OECD series key
  ("oecd", flow, filters, prefer, transform) OECD with dimension discovery + preferences
  ("dbn", series_id, transform)            DBnomics (Eurostat, IMF ...)
  ("bis", country_code, transform)         BIS central bank policy rate
  ("wb", indicator, transform)             World Bank annual (last resort; shown, not scored)
transform: "level" | "yoy" (12-month % change) | "yoyq" (4-quarter % change)
"""

MAX_STALE_MONTHS = 15

# iso3: (name, iso2, eurostat geo, ISO numeric for the map)
ECONOMIES = {
    "USA": ("United States", "US", None, 840),
    "CHN": ("China", "CN", None, 156),
    "JPN": ("Japan", "JP", None, 392),
    "DEU": ("Germany", "DE", "DE", 276),
    "GBR": ("United Kingdom", "GB", None, 826),
    "FRA": ("France", "FR", "FR", 250),
    "ITA": ("Italy", "IT", "IT", 380),
    "CAN": ("Canada", "CA", None, 124),
    "IND": ("India", "IN", None, 356),
}

CPI = "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"
UNE = "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0"
STES_IND = "OECD.SDD.STES,DSD_STES@DF_INDSERV"
STES_FIN = "OECD.SDD.STES,DSD_STES@DF_FINMARK"
QNA = "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA"
IMTS = "OECD.SDD.TPS,DSD_IMTS@DF_IMTS"


def monthly_candidates(iso3):
    name, iso2, geo, _ = ECONOMIES[iso3]
    c = {}
    c["inflation"] = [("oecd_key", CPI, f"{iso3}.M.N.CPI.PA._T.N.GY", "level")]
    if geo:
        c["inflation"] += [("dbn", f"Eurostat/prc_hicp_manr/M.RCH_A.CP00.{geo}", "level")]
    c["inflation"] += [("wb", "FP.CPI.TOTL.ZG", "level")]

    c["unemployment"] = [("oecd_key", UNE, f"{iso3}.UNE_LF_M.PT_LF_SUB._Z.Y._T.Y_GE15._Z.M", "level")]
    if geo:
        c["unemployment"] += [("dbn", f"Eurostat/une_rt_m/M.SA.TOTAL.PC_ACT.T.{geo}", "level")]
    c["unemployment"] += [("wb", "SL.UEM.TOTL.ZS", "level")]

    c["industry"] = [("oecd", STES_IND, {"REF_AREA": iso3, "FREQ": "M", "MEASURE": "PRVM"},
                      {"ACTIVITY": ["BTE", "B-E", "C"], "ADJUSTMENT": ["Y", "S", "N"], "TRANSFORMATION": ["_Z", "N"]},
                      "yoy")]
    if geo:
        c["industry"] += [("dbn", f"Eurostat/sts_inpr_m/M.{i}.B-D.SCA.{u}.{geo}", "yoy")
                          for i in ("PRD", "PROD") for u in ("I21", "I15")]

    c["gdp"] = [("oecd", QNA, {"FREQ": "Q", "REF_AREA": iso3, "SECTOR": "S1", "TRANSACTION": "B1GQ"},
                 {"PRICE_BASE": ["LR", "L"], "ADJUSTMENT": ["Y", "S"], "TRANSFORMATION": ["N", "_Z"],
                  "UNIT_MEASURE": ["XDC", "USD_PPP", "USD_EXC"]}, "yoyq")]
    if geo:
        c["gdp"] += [("dbn", f"Eurostat/namq_10_gdp/Q.CLV_PCH_SM.{sa}.B1GQ.{geo}", "level") for sa in ("SCA", "NSA")]
    c["gdp"] += [("wb", "NY.GDP.MKTP.KD.ZG", "level")]

    c["policy_rate"] = [("bis", "XM" if geo else iso2, "level"),
                        ("oecd", STES_FIN, {"REF_AREA": iso3, "FREQ": "M", "MEASURE": "IRSTCI"}, {}, "level"),
                        ("oecd", STES_FIN, {"REF_AREA": iso3, "FREQ": "M", "MEASURE": "IR3TIB"}, {}, "level")]
    c["long_rate"] = [("oecd", STES_FIN, {"REF_AREA": iso3, "FREQ": "M", "MEASURE": "IRLT"}, {}, "level")]

    # Monthly merchandise trade (value, US$): exports, imports, balance
    trade_pref = {"COUNTERPART_AREA": ["W", "W00", "WLD"], "UNIT_MEASURE": ["USD", "USD_EXC"],
                  "ADJUSTMENT": ["Y", "S", "N"], "TRANSFORMATION": ["_Z", "N"], "FREQ": ["M", "Q"]}
    for ind, flow in (("exports", ["X", "C"]), ("imports", ["M", "D"]), ("trade_balance", ["B"])):
        c[ind] = [("oecd", IMTS, {"REF_AREA": iso3, "FREQ": "M"}, {"_require": ["TRADE_FLOW", "FLOW"], "TRADE_FLOW": flow, "FLOW": flow, **trade_pref},
                   "yoy" if ind != "trade_balance" else "usd_bn")]
    return c


# Annual "vital signs" from the World Bank.
VITALS = {
    "population":     ("SP.POP.TOTL",       "Population", "people"),
    "pop_growth":     ("SP.POP.GROW",       "Population growth", "%"),
    "age65":          ("SP.POP.65UP.TO.ZS", "Aged 65+", "% of pop."),
    "fertility":      ("SP.DYN.TFRT.IN",    "Births per woman", ""),
    "life_exp":       ("SP.DYN.LE00.IN",    "Life expectancy", "years"),
    "health_spend":   ("SH.XPD.CHEX.GD.ZS", "Health spending", "% of GDP"),
    "net_migration":  ("SM.POP.NETM",       "Net migration", "people"),
    "gdp_pc":         ("NY.GDP.PCAP.CD",    "GDP per person", "US$"),
    "gini":           ("SI.POV.GINI",       "Inequality (Gini)", "0-100"),
    "urban":          ("SP.URB.TOTL.IN.ZS", "Urban population", "% of pop."),
}

# Annual fundamentals. "weo" = IMF World Economic Outlook via DBnomics (incl. current-year estimates).
WEO_RELEASES = ["WEO:latest", "WEO:2026-10", "WEO:2026-04", "WEO:2025-10", "WEO:2025-04"]
FUNDAMENTALS = {
    "gdp_usd":         ("GDP", "US$", [("weo", "NGDPD.us_dollars", 1e9), ("wb", "NY.GDP.MKTP.CD", 1)]),
    "gov_debt":        ("Government debt", "% of GDP", [("weo", "GGXWDG_NGDP.pcent_gdp", 1), ("wb", "GC.DOD.TOTL.GD.ZS", 1)]),
    "gov_balance":     ("Budget balance", "% of GDP", [("weo", "GGXCNL_NGDP.pcent_gdp", 1), ("wb", "GC.NLD.TOTL.GD.ZS", 1)]),
    "primary_balance": ("Primary balance", "% of GDP", [("weo", "GGXONLB_NGDP.pcent_gdp", 1)]),
    "revenue":         ("Government revenue", "% of GDP", [("weo", "GGR_NGDP.pcent_gdp", 1), ("wb", "GC.REV.XGRT.GD.ZS", 1)]),
    "spending":        ("Government spending", "% of GDP", [("weo", "GGX_NGDP.pcent_gdp", 1), ("wb", "GC.XPN.TOTL.GD.ZS", 1)]),
    "current_account": ("Current account", "% of GDP", [("weo", "BCA_NGDPD.pcent_gdp", 1), ("wb", "BN.CAB.XOKA.GD.ZS", 1)]),
    "exports_usd":     ("Exports", "US$", [("wb", "NE.EXP.GNFS.CD", 1)]),
    "imports_usd":     ("Imports", "US$", [("wb", "NE.IMP.GNFS.CD", 1)]),
    "net_exports":     ("Net exports", "% of GDP", [("wb", "NE.RSB.GNFS.ZS", 1)]),
    "consumption":     ("Household consumption (C)", "% of GDP", [("wb", "NE.CON.PRVT.ZS", 1)]),
    "investment":      ("Investment (I)", "% of GDP", [("wb", "NE.GDI.TOTL.ZS", 1)]),
    "gov_consumption": ("Government consumption (G)", "% of GDP", [("wb", "NE.CON.GOVT.ZS", 1)]),
    "savings":         ("National savings (S)", "% of GDP", [("weo", "NGSD_NGDP.pcent_gdp", 1), ("wb", "NY.GNS.ICTR.ZS", 1)]),
    "reserves_usd":    ("FX reserves", "US$", [("wb", "FI.RES.TOTL.CD", 1)]),
    "reserves_months": ("Reserves", "months of imports", [("wb", "FI.RES.TOTL.MO", 1)]),
    "private_credit":  ("Bank credit to private sector", "% of GDP", [("wb", "FS.AST.PRVT.GD.ZS", 1)]),
}

# World Bank Pink Sheet columns (matched by prefix, case-insensitive) -> (display name, ship type)
COMMODITIES = [
    ("Crude oil, Brent", "Brent crude", "tanker"),
    ("Crude oil, WTI", "WTI crude", "tanker"),
    ("Natural gas, US", "US natural gas", "tanker"),
    ("Natural gas, Europe", "Europe natural gas", "tanker"),
    ("Liquefied natural gas, Japan", "Asia LNG", "tanker"),
    ("Coal, Australia", "Coal", "dry_bulk"),
    ("Iron ore", "Iron ore", "dry_bulk"),
    ("Copper", "Copper", "dry_bulk"),
    ("Aluminum", "Aluminum", "dry_bulk"),
    ("Nickel", "Nickel", "dry_bulk"),
    ("Wheat, US HRW", "Wheat", "dry_bulk"),
    ("Maize", "Corn", "dry_bulk"),
    ("Rice, Thai 5", "Rice", "dry_bulk"),
    ("Soybeans", "Soybeans", "dry_bulk"),
    ("Sugar, world", "Sugar", "dry_bulk"),
    ("Coffee, Arabica", "Coffee", "container"),
    ("Cocoa", "Cocoa", "container"),
    ("Cotton", "Cotton", "container"),
    ("Beef", "Beef", "container"),
    ("Urea", "Fertilizer (urea)", "dry_bulk"),
    ("Gold", "Gold", None),
    ("Silver", "Silver", None),
]

# ECB reference rates (per EUR). Shown as per US dollar unless noted.
FX = ["USD", "GBP", "JPY", "CNY", "INR", "CAD", "CHF", "KRW", "MXN", "BRL", "AUD", "ZAR", "TRY"]
FX_NAMES = {"EUR": "Euro (USD per EUR)", "GBP": "British pound (USD per GBP)", "JPY": "Japanese yen",
            "CNY": "Chinese yuan", "INR": "Indian rupee", "CAD": "Canadian dollar", "CHF": "Swiss franc",
            "KRW": "Korean won", "MXN": "Mexican peso", "BRL": "Brazilian real", "AUD": "Australian dollar",
            "ZAR": "South African rand", "TRY": "Turkish lira"}

# PortWatch
REGIONS = {
    "China": ["CHN", "HKG"], "NE Asia": ["JPN", "KOR", "TWN"],
    "SE Asia": ["SGP", "MYS", "VNM", "THA", "IDN", "PHL"],
    "South Asia": ["IND", "PAK", "BGD", "LKA"], "Middle East": ["ARE", "SAU", "OMN", "QAT"],
    "Europe": ["NLD", "BEL", "DEU", "ESP", "FRA", "ITA", "GBR", "GRC", "POL"],
    "US": ["USA"], "Canada": ["CAN"], "LatAm": ["BRA", "MEX", "CHL", "PER", "COL", "PAN"],
    "Africa": ["ZAF", "EGY", "MAR", "NGA", "KEN"],
}
PORTS_PER_REGION, PORTS_PER_ECONOMY = 5, 4
PRODUCTS = {"tanker": "Oil, fuel, gas, chemicals", "container": "Manufactured goods",
            "dry_bulk": "Ores, coal, grain", "general_cargo": "Steel, project cargo", "roro": "Vehicles"}
# id: (name, lon, lat)
CHOKEPOINTS = {
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

# ISO3 -> ISO numeric (for the world map; covers every country we may color)
ISO_NUM = {"USA": 840, "CHN": 156, "JPN": 392, "DEU": 276, "GBR": 826, "FRA": 250, "ITA": 380, "CAN": 124,
           "IND": 356, "HKG": 344, "KOR": 410, "TWN": 158, "SGP": 702, "MYS": 458, "VNM": 704, "THA": 764,
           "IDN": 360, "PHL": 608, "PAK": 586, "BGD": 50, "LKA": 144, "ARE": 784, "SAU": 682, "OMN": 512,
           "QAT": 634, "NLD": 528, "BEL": 56, "ESP": 724, "GRC": 300, "POL": 616, "BRA": 76, "MEX": 484,
           "CHL": 152, "PER": 604, "COL": 170, "PAN": 591, "ZAF": 710, "EGY": 818, "MAR": 504, "NGA": 566,
           "KEN": 404, "AUS": 36, "TUR": 792, "RUS": 643}
