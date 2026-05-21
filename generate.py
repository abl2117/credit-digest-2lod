import anthropic
import json
import os
import re
from datetime import datetime, timedelta
import pytz

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("WARNING: yfinance not installed; falling back to Claude-sourced market data.")

try:
    import sec_edgar
    SEC_EDGAR_AVAILABLE = True
except ImportError:
    SEC_EDGAR_AVAILABLE = False
    print("WARNING: sec_edgar module not found; financials will use Claude data only.")

try:
    import run_log
    RUN_LOG_AVAILABLE = True
except ImportError:
    RUN_LOG_AVAILABLE = False

try:
    import red_flags
    RED_FLAGS_AVAILABLE = True
except ImportError:
    RED_FLAGS_AVAILABLE = False
    print("WARNING: red_flags module not found; Red Flags tab will remain placeholder.")

try:
    import fred
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False
    print("WARNING: fred module not found; Macro tab will be empty.")

try:
    import census_construction
    CENSUS_AVAILABLE = True
except ImportError:
    CENSUS_AVAILABLE = False
    print("WARNING: census_construction module not found; Data Center construction chart will be empty.")

try:
    import sector_snapshot
    SECTOR_SNAPSHOT_AVAILABLE = True
except ImportError:
    SECTOR_SNAPSHOT_AVAILABLE = False
    print("WARNING: sector_snapshot module not found; Sector Snapshot panel will not render.")

et = pytz.timezone('America/New_York')
now = datetime.now(et)
datetime_str = now.strftime('%B %d, %Y at %I:%M %p ET')
today = now.date()

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
DASHBOARD_URL = "https://abl2117.github.io/credit-digest-2lod"

RATINGS_OVERRIDE = {}
if os.path.exists('ratings_override.json'):
    try:
        with open('ratings_override.json', 'r', encoding='utf-8') as f:
            RATINGS_OVERRIDE = json.load(f)
        print(f"Loaded ratings_override.json with {sum(1 for k in RATINGS_OVERRIDE if not k.startswith('_'))} manual overrides.")
    except Exception as e:
        print(f"WARNING: ratings_override.json failed to parse: {e}")

# news_override.json: per-company key_dev override for cases where Claude's
# search missed a material development. Structure:
# {
#   "Flex Ltd": {
#     "key_dev": "Announced spin-off of data center EMS business and acquisition of Electrical Power Products; S&P affirmed BBB-/Stable May 6 2026.",
#     "expires": "2026-07-06"  # optional; falls off after this date
#   }
# }
NEWS_OVERRIDE = {}
if os.path.exists('news_override.json'):
    try:
        with open('news_override.json', 'r', encoding='utf-8') as f:
            NEWS_OVERRIDE = json.load(f)
        active_count = sum(1 for k in NEWS_OVERRIDE if not k.startswith('_'))
        print(f"Loaded news_override.json with {active_count} news overrides.")
    except Exception as e:
        print(f"WARNING: news_override.json failed to parse: {e}")

WATCHLIST = {
    # ===== EXISTING 81 NAMES (preserved) =====
    "AT&T":                    {"ticker": "T",     "filer_type": "10-K", "sector": "Telecom"},
    "Verizon":                 {"ticker": "VZ",    "filer_type": "10-K", "sector": "Telecom"},
    "Comcast":                 {"ticker": "CMCSA", "filer_type": "10-K", "sector": "Telecom"},
    "Disney":                  {"ticker": "DIS",   "filer_type": "10-K", "sector": "Media"},
    "Warner Bros. Discovery":  {"ticker": "WBD",   "filer_type": "10-K", "sector": "Media"},
    "Netflix":                 {"ticker": "NFLX",  "filer_type": "10-K", "sector": "Media"},
    "Amazon":                  {"ticker": "AMZN",  "filer_type": "10-K", "sector": "Tech"},
    "Alphabet":                {"ticker": "GOOGL", "filer_type": "10-K", "sector": "Tech"},
    "Microsoft":               {"ticker": "MSFT",  "filer_type": "10-K", "sector": "Tech"},
    "Oracle":                  {"ticker": "ORCL",  "filer_type": "10-K", "sector": "Tech"},
    "Salesforce":              {"ticker": "CRM",   "filer_type": "10-K", "sector": "Tech"},
    "IBM":                     {"ticker": "IBM",   "filer_type": "10-K", "sector": "Tech"},
    "HP Inc":                  {"ticker": "HPQ",   "filer_type": "10-K", "sector": "Hardware"},
    "HPE":                     {"ticker": "HPE",   "filer_type": "10-K", "sector": "Hardware"},
    "Dell":                    {"ticker": "DELL",  "filer_type": "10-K", "sector": "Hardware"},
    "Nextracker":              {"ticker": "NXT",   "filer_type": "10-K", "sector": "Hardware"},
    "Sanmina":                 {"ticker": "SANM",  "filer_type": "10-K", "sector": "EMS"},
    "Flex Ltd":                {"ticker": "FLEX",  "filer_type": "10-K", "sector": "EMS"},
    "Jabil":                   {"ticker": "JBL",   "filer_type": "10-K", "sector": "EMS"},
    "Arrow Electronics":       {"ticker": "ARW",   "filer_type": "10-K", "sector": "Distribution"},
    "TD Synnex":               {"ticker": "SNX",   "filer_type": "10-K", "sector": "Distribution"},
    "Ingram Micro":            {"ticker": "INGM",  "filer_type": "10-K", "sector": "Distribution"},
    "Kyndryl":                 {"ticker": "KD",    "filer_type": "10-K", "sector": "IT Services"},
    "Cognizant":               {"ticker": "CTSH",  "filer_type": "10-K", "sector": "IT Services"},
    "Equinix":                 {"ticker": "EQIX",  "filer_type": "10-K", "sector": "Datacenter"},
    "Digital Realty":          {"ticker": "DLR",   "filer_type": "10-K", "sector": "Datacenter"},
    "American Tower":          {"ticker": "AMT",   "filer_type": "10-K", "sector": "Towers"},
    "PayPal":                  {"ticker": "PYPL",  "filer_type": "10-K", "sector": "Payments"},
    "Corpay":                  {"ticker": "CPAY",  "filer_type": "10-K", "sector": "Payments"},
    "Booking Holdings":        {"ticker": "BKNG",  "filer_type": "10-K", "sector": "Travel"},
    "Uber":                    {"ticker": "UBER",  "filer_type": "10-K", "sector": "Travel"},
    "Delta":                   {"ticker": "DAL",   "filer_type": "10-K", "sector": "Travel"},
    "Carnival":                {"ticker": "CCL",   "filer_type": "10-K", "sector": "Travel"},
    "Royal Caribbean":         {"ticker": "RCL",   "filer_type": "10-K", "sector": "Travel"},
    "Norwegian Cruise Line":   {"ticker": "NCLH",  "filer_type": "10-K", "sector": "Travel"},
    "General Motors":          {"ticker": "GM",    "filer_type": "10-K", "sector": "Auto"},
    "Tesla":                   {"ticker": "TSLA",  "filer_type": "10-K", "sector": "Auto"},
    "Ford":                    {"ticker": "F",     "filer_type": "10-K", "sector": "Auto"},
    "Toyota":                  {"ticker": "TM",    "filer_type": "20-F", "sector": "Auto"},
    "Nissan":                  {"ticker": "NSANY", "filer_type": None,   "sector": "Auto"},
    "Boeing":                  {"ticker": "BA",    "filer_type": "10-K", "sector": "Aerospace"},
    "GE Aerospace":            {"ticker": "GE",    "filer_type": "10-K", "sector": "Aerospace"},
    "Walmart":                 {"ticker": "WMT",   "filer_type": "10-K", "sector": "Retail"},
    "AutoZone":                {"ticker": "AZO",   "filer_type": "10-K", "sector": "Retail"},
    "Genuine Parts":           {"ticker": "GPC",   "filer_type": "10-K", "sector": "Retail"},
    "Coca-Cola":               {"ticker": "KO",    "filer_type": "10-K", "sector": "Beverage"},
    "Anheuser-Busch InBev":    {"ticker": "BUD",   "filer_type": "20-F", "sector": "Beverage"},
    "Philip Morris":           {"ticker": "PM",    "filer_type": "10-K", "sector": "Tobacco"},
    "Altria":                  {"ticker": "MO",    "filer_type": "10-K", "sector": "Tobacco"},
    "Imperial Brands":         {"ticker": "IMBBY", "filer_type": None,   "sector": "Tobacco"},
    "Universal Corporation":   {"ticker": "UVV",   "filer_type": "10-K", "sector": "Tobacco"},
    "Nike":                    {"ticker": "NKE",   "filer_type": "10-K", "sector": "Consumer"},
    "Kimberly-Clark":          {"ticker": "KMB",   "filer_type": "10-K", "sector": "Consumer"},
    "Whirlpool":               {"ticker": "WHR",   "filer_type": "10-K", "sector": "Consumer"},
    "Mondelez":                {"ticker": "MDLZ",  "filer_type": "10-K", "sector": "Consumer"},
    "Ball Corp":               {"ticker": "BALL",  "filer_type": "10-K", "sector": "Packaging"},
    "Crown Holdings":          {"ticker": "CCK",   "filer_type": "10-K", "sector": "Packaging"},
    "International Paper":     {"ticker": "IP",    "filer_type": "10-K", "sector": "Packaging"},
    "Chevron":                 {"ticker": "CVX",   "filer_type": "10-K", "sector": "Energy"},
    "BP":                      {"ticker": "BP",    "filer_type": "20-F", "sector": "Energy"},
    "Exxon":                   {"ticker": "XOM",   "filer_type": "10-K", "sector": "Energy"},
    "NextEra Energy":          {"ticker": "NEE",   "filer_type": "10-K", "sector": "Utilities"},
    "Duke Energy":             {"ticker": "DUK",   "filer_type": "10-K", "sector": "Utilities"},
    "Sempra Energy":           {"ticker": "SRE",   "filer_type": "10-K", "sector": "Utilities"},
    "Caterpillar":             {"ticker": "CAT",   "filer_type": "10-K", "sector": "Industrials"},
    "Deere":                   {"ticker": "DE",    "filer_type": "10-K", "sector": "Industrials"},
    "Danaher":                 {"ticker": "DHR",   "filer_type": "10-K", "sector": "Industrials"},
    "GE Vernova":              {"ticker": "GEV",   "filer_type": "10-K", "sector": "Industrials"},
    "Honeywell":               {"ticker": "HON",   "filer_type": "10-K", "sector": "Industrials"},
    "Otis":                    {"ticker": "OTIS",  "filer_type": "10-K", "sector": "Industrials"},
    "Air Products":            {"ticker": "APD",   "filer_type": "10-K", "sector": "Industrials"},
    "Corteva":                 {"ticker": "CTVA",  "filer_type": "10-K", "sector": "Industrials"},
    "DuPont":                  {"ticker": "DD",    "filer_type": "10-K", "sector": "Industrials"},
    "Apple":                   {"ticker": "AAPL",  "filer_type": "10-K", "sector": "Tech"},
    "Nutanix":                 {"ticker": "NTNX",  "filer_type": "10-K", "sector": "Software"},
    "Mastercard":              {"ticker": "MA",    "filer_type": "10-K", "sector": "Payments"},
    "Visa":                    {"ticker": "V",     "filer_type": "10-K", "sector": "Payments"},
    "Avnet":                   {"ticker": "AVT",   "filer_type": "10-K", "sector": "Distribution"},
    "CDW":                     {"ticker": "CDW",   "filer_type": "10-K", "sector": "Distribution"},
    "Amrize":                  {"ticker": "AMRZ",  "filer_type": "10-K", "sector": "Materials"},
    "CEMEX":                   {"ticker": "CX",    "filer_type": "20-F", "sector": "Materials"},

    # ===== EXPANSION (105 new names, May 21, 2026) =====

    # AGRIBUSINESS
    "Archer-Daniels-Midland":  {"ticker": "ADM",   "filer_type": "10-K", "sector": "Agribusiness"},
    "Bunge":                   {"ticker": "BG",    "filer_type": "10-K", "sector": "Agribusiness"},
    "Ingredion":               {"ticker": "INGR",  "filer_type": "10-K", "sector": "Agribusiness"},

    # PERSONAL CARE
    "Colgate-Palmolive":       {"ticker": "CL",    "filer_type": "10-K", "sector": "Personal Care"},
    "Kenvue":                  {"ticker": "KVUE",  "filer_type": "10-K", "sector": "Personal Care"},
    "Coty":                    {"ticker": "COTY",  "filer_type": "10-K", "sector": "Personal Care"},

    # UTILITIES (additions)
    "AES":                     {"ticker": "AES",   "filer_type": "10-K", "sector": "Utilities"},
    "Dominion Energy":         {"ticker": "D",     "filer_type": "10-K", "sector": "Utilities"},
    "Edison International":    {"ticker": "EIX",   "filer_type": "10-K", "sector": "Utilities"},
    "Constellation Energy":    {"ticker": "CEG",   "filer_type": "10-K", "sector": "Utilities"},
    "Southern Company":        {"ticker": "SO",    "filer_type": "10-K", "sector": "Utilities"},
    "PPL Corporation":         {"ticker": "PPL",   "filer_type": "10-K", "sector": "Utilities"},
    "NRG Energy":              {"ticker": "NRG",   "filer_type": "10-K", "sector": "Utilities"},
    "NextEra Energy Partners": {"ticker": "NEP",   "filer_type": "10-K", "sector": "Utilities"},
    "RWE":                     {"ticker": "RWEOY", "filer_type": None,   "sector": "Utilities"},
    "Uniper":                  {"ticker": "UNPRF", "filer_type": None,   "sector": "Utilities"},
    "Engie":                   {"ticker": "ENGIY", "filer_type": None,   "sector": "Utilities"},
    "Enel":                    {"ticker": "ENLAY", "filer_type": None,   "sector": "Utilities"},

    # RENEWABLES
    "Clearway Energy Group":   {"ticker": "CWEN",  "filer_type": "10-K", "sector": "Renewables"},
    "Brookfield Renewable Partners": {"ticker": "BEP", "filer_type": "20-F", "sector": "Renewables"},
    "Fluence Energy":          {"ticker": "FLNC",  "filer_type": "10-K", "sector": "Renewables"},

    # MIDSTREAM
    "Cheniere Energy":         {"ticker": "LNG",   "filer_type": "10-K", "sector": "Midstream"},
    "Enbridge":                {"ticker": "ENB",   "filer_type": "40-F", "sector": "Midstream"},

    # OILFIELD SERVICES & ENERGY (additions)
    "Halliburton":             {"ticker": "HAL",   "filer_type": "10-K", "sector": "Oilfield Services"},
    "SLB":                     {"ticker": "SLB",   "filer_type": "10-K", "sector": "Oilfield Services"},
    "Baker Hughes":            {"ticker": "BKR",   "filer_type": "10-K", "sector": "Oilfield Services"},
    "TechnipFMC":              {"ticker": "FTI",   "filer_type": "10-K", "sector": "Oilfield Services"},
    "Phillips 66":             {"ticker": "PSX",   "filer_type": "10-K", "sector": "Refining"},
    "Woodside Energy":         {"ticker": "WDS",   "filer_type": None,   "sector": "Energy"},
    "Equinor":                 {"ticker": "EQNR",  "filer_type": "20-F", "sector": "Energy"},
    "Shell":                   {"ticker": "SHEL",  "filer_type": "20-F", "sector": "Energy"},
    "TotalEnergies":           {"ticker": "TTE",   "filer_type": "20-F", "sector": "Energy"},

    # CHEMICALS
    "Dow":                     {"ticker": "DOW",   "filer_type": "10-K", "sector": "Chemicals"},
    "LyondellBasell":          {"ticker": "LYB",   "filer_type": "10-K", "sector": "Chemicals"},
    "Olin Corporation":        {"ticker": "OLN",   "filer_type": "10-K", "sector": "Chemicals"},
    "Albemarle":               {"ticker": "ALB",   "filer_type": "10-K", "sector": "Chemicals"},
    "Linde":                   {"ticker": "LIN",   "filer_type": "10-K", "sector": "Chemicals"},
    "FMC Corporation":         {"ticker": "FMC",   "filer_type": "10-K", "sector": "Chemicals"},
    "Ecolab":                  {"ticker": "ECL",   "filer_type": "10-K", "sector": "Chemicals"},
    "Nutrien":                 {"ticker": "NTR",   "filer_type": None,   "sector": "Chemicals"},
    "PPG Industries":          {"ticker": "PPG",   "filer_type": "10-K", "sector": "Chemicals"},
    "Braskem":                 {"ticker": "BAK",   "filer_type": "20-F", "sector": "Chemicals"},
    "Brenntag":                {"ticker": "BNTGY", "filer_type": None,   "sector": "Chemicals"},

    # PHARMA
    "AbbVie":                  {"ticker": "ABBV",  "filer_type": "10-K", "sector": "Pharma"},
    "Eli Lilly":               {"ticker": "LLY",   "filer_type": "10-K", "sector": "Pharma"},
    "Johnson & Johnson":       {"ticker": "JNJ",   "filer_type": "10-K", "sector": "Pharma"},
    "Merck & Co":              {"ticker": "MRK",   "filer_type": "10-K", "sector": "Pharma"},
    "Pfizer":                  {"ticker": "PFE",   "filer_type": "10-K", "sector": "Pharma"},
    "AstraZeneca":             {"ticker": "AZN",   "filer_type": "20-F", "sector": "Pharma"},
    "GSK":                     {"ticker": "GSK",   "filer_type": "20-F", "sector": "Pharma"},
    "Roche Holding":           {"ticker": "RHHBY", "filer_type": None,   "sector": "Pharma"},
    "Bayer":                   {"ticker": "BAYRY", "filer_type": None,   "sector": "Pharma"},

    # HEALTHCARE DISTRIBUTION
    "Cardinal Health":         {"ticker": "CAH",   "filer_type": "10-K", "sector": "Healthcare Distribution"},
    "Cencora":                 {"ticker": "COR",   "filer_type": "10-K", "sector": "Healthcare Distribution"},
    "McKesson":                {"ticker": "MCK",   "filer_type": "10-K", "sector": "Healthcare Distribution"},

    # ASSET MANAGERS
    "Blackstone":              {"ticker": "BX",    "filer_type": "10-K", "sector": "Asset Managers"},
    "KKR":                     {"ticker": "KKR",   "filer_type": "10-K", "sector": "Asset Managers"},
    "Apollo Global Management":{"ticker": "APO",   "filer_type": "10-K", "sector": "Asset Managers"},
    "Brookfield Infrastructure Partners": {"ticker": "BIP", "filer_type": "20-F", "sector": "Asset Managers"},

    # REITs
    "Realty Income":           {"ticker": "O",     "filer_type": "10-K", "sector": "REITs"},
    "Simon Property Group":    {"ticker": "SPG",   "filer_type": "10-K", "sector": "REITs"},

    # MINING
    "Barrick Gold":            {"ticker": "GOLD",  "filer_type": "40-F", "sector": "Mining"},
    "Newmont":                 {"ticker": "NEM",   "filer_type": "10-K", "sector": "Mining"},
    "Teck Resources":          {"ticker": "TECK",  "filer_type": "40-F", "sector": "Mining"},

    # TRUCKS / HEAVY EQUIPMENT
    "Daimler Truck":           {"ticker": "DTRUY", "filer_type": None,   "sector": "Trucks"},
    "PACCAR":                  {"ticker": "PCAR",  "filer_type": "10-K", "sector": "Trucks"},
    "Cummins":                 {"ticker": "CMI",   "filer_type": "10-K", "sector": "Trucks"},
    "Wabtec":                  {"ticker": "WAB",   "filer_type": "10-K", "sector": "Rail"},
    "CNH Industrial":          {"ticker": "CNH",   "filer_type": "10-K", "sector": "Heavy Equipment"},

    # AUTOS (international additions)
    "BMW":                     {"ticker": "BMWYY", "filer_type": None,   "sector": "Auto"},
    "Volkswagen":              {"ticker": "VWAGY", "filer_type": None,   "sector": "Auto"},
    "Mercedes-Benz":           {"ticker": "MBGYY", "filer_type": None,   "sector": "Auto"},
    "Hyundai":                 {"ticker": "HYMTF", "filer_type": None,   "sector": "Auto"},

    # FOOD PROCESSING
    "JBS":                     {"ticker": "JBS",   "filer_type": None,   "sector": "Food Processing"},
    "Pilgrim's Pride":         {"ticker": "PPC",   "filer_type": "10-K", "sector": "Food Processing"},
    "Kraft Heinz":             {"ticker": "KHC",   "filer_type": "10-K", "sector": "Food Processing"},
    "Grupo Bimbo":             {"ticker": "BMBOY", "filer_type": None,   "sector": "Food Processing"},
    "Alicorp":                 {"ticker": "ALCRY", "filer_type": None,   "sector": "Food Processing"},

    # BEVERAGE
    "Coca-Cola Consolidated":  {"ticker": "COKE",  "filer_type": "10-K", "sector": "Beverage"},

    # AIRLINES
    "Turkish Airlines":        {"ticker": "TKHVY", "filer_type": None,   "sector": "Airlines"},

    # MEDIA
    "Lagardère":               {"ticker": "LGDDF", "filer_type": None,   "sector": "Media"},

    # LUXURY
    "LVMH":                    {"ticker": "LVMUY", "filer_type": None,   "sector": "Luxury"},
    "EssilorLuxottica":        {"ticker": "ESLOY", "filer_type": None,   "sector": "Luxury"},

    # POWER EQUIPMENT
    "Generac Holdings":        {"ticker": "GNRC",  "filer_type": "10-K", "sector": "Power Equipment"},
    "Siemens Energy":          {"ticker": "SMNEY", "filer_type": None,   "sector": "Power Equipment"},
    "Siemens":                 {"ticker": "SIEGY", "filer_type": None,   "sector": "Industrials"},

    # BUILDING MATERIALS
    "Holcim":                  {"ticker": "HCMLY", "filer_type": None,   "sector": "Building Materials"},
    "Saint-Gobain":            {"ticker": "CODYY", "filer_type": None,   "sector": "Building Materials"},
    "NVR":                     {"ticker": "NVR",   "filer_type": "10-K", "sector": "Homebuilders"},

    # INDUSTRIALS (additions)
    "3M":                      {"ticker": "MMM",   "filer_type": "10-K", "sector": "Industrials"},
    "Parker Hannifin":         {"ticker": "PH",    "filer_type": "10-K", "sector": "Industrials"},
    "Pentair":                 {"ticker": "PNR",   "filer_type": "10-K", "sector": "Industrials"},
    "Air Lease Corporation":   {"ticker": "AL",    "filer_type": "10-K", "sector": "Aircraft Leasing"},
    "Gerdau":                  {"ticker": "GGB",   "filer_type": "20-F", "sector": "Steel"},
    "Michelin":                {"ticker": "MGDDY", "filer_type": None,   "sector": "Auto Parts"},

    # TECH (additions)
    "Broadcom":                {"ticker": "AVGO",  "filer_type": "10-K", "sector": "Semiconductors"},

    # RETAIL (additions)
    "Costco Wholesale":        {"ticker": "COST",  "filer_type": "10-K", "sector": "Retail"},
    "Home Depot":              {"ticker": "HD",    "filer_type": "10-K", "sector": "Retail"},
    "O'Reilly Automotive":     {"ticker": "ORLY",  "filer_type": "10-K", "sector": "Retail"},
    "WH Smith":                {"ticker": "WHTPF", "filer_type": None,   "sector": "Retail"},
    "Seven & i Holdings":      {"ticker": "SVNDY", "filer_type": None,   "sector": "Retail"},

    # SERVICES
    "Sodexo":                  {"ticker": "SDXAY", "filer_type": None,   "sector": "Services"},
    "Rentokil Initial":        {"ticker": "RTO",   "filer_type": "20-F", "sector": "Services"},
    "Brink's":                 {"ticker": "BCO",   "filer_type": "10-K", "sector": "Services"},

    # RESTAURANTS
    "Krispy Kreme":            {"ticker": "DNUT",  "filer_type": "10-K", "sector": "Restaurants"},
}

TMT_SUBSECTIONS = [
    {"id": "hyperscalers", "title": "Hyperscalers", "subtitle": "Cloud infrastructure operators and CapEx anchors",
     "names": ["Microsoft", "Alphabet", "Amazon", "Oracle"]},
    {"id": "datacenter_towers", "title": "Data Center & Tower REITs", "subtitle": "Physical infrastructure for hyperscalers and carriers",
     "names": ["Equinix", "Digital Realty", "American Tower"]},
    {"id": "telecom", "title": "Telecom", "subtitle": "US wireline and wireless carriers",
     "names": ["AT&T", "Verizon", "Comcast"]},
    {"id": "hardware_ems", "title": "Hardware & EMS", "subtitle": "Servers, networking, contract manufacturing, distribution",
     "names": ["HPE", "Dell", "HP Inc", "IBM", "Jabil", "Flex Ltd", "Sanmina", "Nextracker", "Arrow Electronics", "Avnet", "TD Synnex", "Ingram Micro", "CDW"]},
    {"id": "software_payments_services", "title": "Software, Payments & Services", "subtitle": "SaaS, payments, IT services, online travel",
     "names": ["Salesforce", "Nutanix", "Cognizant", "Kyndryl", "PayPal", "Mastercard", "Visa", "Corpay", "Booking Holdings"]},
]

TICKER_MAP = {co: info["ticker"] for co, info in WATCHLIST.items()}


def fetch_market_data():
    if not YFINANCE_AVAILABLE:
        return {}
    print(f"Fetching market data from yfinance for {len(TICKER_MAP)} tickers...")
    result = {}
    success = 0
    failed = []
    tickers_str = " ".join(TICKER_MAP.values())
    try:
        hist = yf.download(tickers_str, period="1y", interval="1d",
                           group_by="ticker", auto_adjust=True,
                           progress=False, threads=True)
    except Exception as e:
        print(f"WARNING: yfinance batch download failed: {e}")
        return {}
    today_local = now.date()
    year_start = datetime(today_local.year, 1, 1).date()
    for company, ticker in TICKER_MAP.items():
        try:
            if ticker in hist.columns.get_level_values(0):
                df = hist[ticker].dropna()
            else:
                df = hist.dropna()
            if df.empty or 'Close' not in df.columns:
                failed.append(ticker)
                continue
            closes = df['Close']
            current = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) > 1 else current
            one_m_idx = max(0, len(closes) - 22)
            month_ago = float(closes.iloc[one_m_idx])
            # 1Y return: first close in the 1y download window
            year_ago = float(closes.iloc[0]) if len(closes) > 0 else current
            ytd_closes = closes[closes.index.date >= year_start]
            ytd_start = float(ytd_closes.iloc[0]) if len(ytd_closes) > 0 else current
            wk52_high = float(closes.max())
            wk52_low = float(closes.min())
            def pct(n, t):
                if t == 0:
                    return "n/a"
                p = (n - t) / t * 100
                sign = "+" if p >= 0 else "-"
                return f"{sign}{abs(p):.1f}"
            result[company] = {
                "price": f"{current:.2f}",
                "stock_1d": pct(current, prev),
                "stock_1m": pct(current, month_ago),
                "stock_ytd": pct(current, ytd_start),
                "stock_1y": pct(current, year_ago),
                "week52_high": f"{wk52_high:.2f}",
                "week52_low": f"{wk52_low:.2f}",
            }
            try:
                fi = yf.Ticker(ticker).fast_info
                mcap_raw = getattr(fi, 'market_cap', None)
                if mcap_raw and mcap_raw > 0:
                    result[company]["mkt_cap"] = f"{mcap_raw/1e9:.1f}"
            except Exception:
                pass
            success += 1
        except Exception as e:
            failed.append(f"{ticker} ({str(e)[:60]})")
    print(f"yfinance: {success}/{len(TICKER_MAP)} tickers succeeded.")
    if failed:
        print(f"yfinance failures: {failed[:10]}{'...' if len(failed) > 10 else ''}")
    return result


def apply_market_overrides(rows, market_data):
    if not market_data:
        return rows
    applied = 0
    mcap_applied = 0
    for r in rows:
        co = r.get('company', '')
        if co in market_data:
            md = market_data[co]
            r['price'] = md['price']
            r['stock_1d'] = md['stock_1d']
            r['stock_1m'] = md['stock_1m']
            r['stock_ytd'] = md['stock_ytd']
            r['stock_1y'] = md.get('stock_1y', 'n/a')
            r['week52_high'] = md['week52_high']
            r['week52_low'] = md['week52_low']
            if 'mkt_cap' in md:
                r['mkt_cap'] = md['mkt_cap']
                mcap_applied += 1
            applied += 1
    print(f"Applied yfinance market data to {applied} companies (mkt_cap: {mcap_applied}).")
    return rows


def compute_status_from_flags(rows):
    """
    Four-tier status driven by 15-flag framework count.

    Tiers (mapped to status field + severity field for color coding):
      - CRITICAL (status=red, severity=critical):
          >= 4 flagged, OR (>= 3 flagged AND >= 2 watch)
      - HIGH (status=red, severity=high):
          3 flagged, OR (2 flagged AND >= 3 watch)
      - AMBER (status=amber, severity=watch):
          1-2 flagged, OR (0 flagged AND >= 4 watch)
      - GREEN (status=green, severity=monitor):
          0 flagged AND <= 3 watch

    Action mapping:
      - CRITICAL -> ESCALATE
      - HIGH -> REVIEW
      - AMBER -> WATCH
      - GREEN -> MONITOR

    Internally we keep status as 3 values (red/amber/green) to preserve
    backwards compatibility with existing CSS, filter pills, and counters.
    The new severity field drives the visual distinction between CRITICAL
    and HIGH (both red status but different visual treatment).
    """
    upgrade_count = 0
    downgrade_count = 0
    transitions = []
    for r in rows:
        original_status = (r.get('status') or 'green').lower()
        flag_count = int(r.get('_flag_count', 0) or 0)
        watch_count = int(r.get('_watch_count', 0) or 0)

        # Determine tier
        if flag_count >= 4 or (flag_count >= 3 and watch_count >= 2):
            new_status, severity, action = 'red', 'critical', 'Escalate'
        elif flag_count >= 3 or (flag_count >= 2 and watch_count >= 3):
            new_status, severity, action = 'red', 'high', 'Review'
        elif flag_count >= 1 or watch_count >= 4:
            new_status, severity, action = 'amber', 'watch', 'Watch'
        else:
            new_status, severity, action = 'green', 'monitor', 'Monitor'

        if new_status != original_status:
            if (original_status == 'green' and new_status in ('amber', 'red')) or \
               (original_status == 'amber' and new_status == 'red'):
                upgrade_count += 1
                transitions.append(f"  {r.get('company','')}: {original_status} -> {new_status}/{severity} ({flag_count} flagged, {watch_count} watch)")
            else:
                downgrade_count += 1

        r['status'] = new_status
        r['severity'] = severity
        r['action'] = action
        r['_status_source'] = 'flag-driven'
    print(f"Flag-driven status: {upgrade_count} escalations, {downgrade_count} de-escalations from initial Claude classification.")
    if transitions:
        for t in transitions[:10]:
            print(t)
        if len(transitions) > 10:
            print(f"  ... and {len(transitions)-10} more")
    return rows


def compute_status_from_data(rows):
    """
    DEPRECATED legacy function. Retained for backwards compatibility but no longer
    called from main(). Status is now driven by 15-flag count via compute_status_from_flags.
    """
    def to_float(v):
        try:
            return float(str(v).replace(',','').replace('+','').replace('%','').strip())
        except:
            return None
    def is_neg_outlook(o):
        return str(o or '').strip().lower() in ('negative', 'rur')
    overrides = 0
    overrides_detail = []
    for r in rows:
        original = (r.get('status') or 'green').lower()
        concern = to_float(r.get('concern_score')) or 0
        action = (r.get('action') or '').strip().lower()
        neg_count = sum(1 for f in ('moodys_outlook','sp_outlook','fitch_outlook')
                        if is_neg_outlook(r.get(f)))
        ytd = to_float(r.get('stock_ytd'))
        m1 = to_float(r.get('stock_1m'))
        leverage = to_float(r.get('nd_ebitda'))
        fcf = to_float(r.get('fcf_ltm'))
        red_triggers = []
        amber_triggers = []
        if concern >= 70: red_triggers.append(f"concern_score={concern:.0f}")
        if action in ('review', 'escalate', 'reduce', 'sell'): red_triggers.append(f"action={action}")
        if neg_count >= 2: red_triggers.append(f"{neg_count} negative outlooks")
        if ytd is not None and ytd < -30: red_triggers.append(f"YTD {ytd:.0f}%")
        if leverage is not None and leverage > 5 and fcf is not None and fcf < 0:
            red_triggers.append(f"leverage {leverage:.1f}x & FCF neg")
        if red_triggers:
            computed = 'red'
        else:
            if concern >= 30: amber_triggers.append(f"concern={concern:.0f}")
            if action == 'watch': amber_triggers.append("action=watch")
            if neg_count == 1: amber_triggers.append("1 negative outlook")
            if leverage is not None and leverage > 5: amber_triggers.append(f"leverage {leverage:.1f}x")
            if fcf is not None and fcf < 0: amber_triggers.append("FCF negative")
            if ytd is not None and ytd < -20: amber_triggers.append(f"YTD {ytd:.0f}%")
            if m1 is not None and m1 < -15: amber_triggers.append(f"1M {m1:.0f}%")
            computed = 'amber' if amber_triggers else 'green'
        if computed != original:
            overrides += 1
            triggers_str = ", ".join(red_triggers or amber_triggers) or "no triggers fired"
            overrides_detail.append(f"  {r.get('company','')}: {original} -> {computed} ({triggers_str})")
        r['status'] = computed
        r['_status_source'] = 'computed'
    print(f"Status recomputed from data: {overrides} of {len(rows)} rows changed.")
    if overrides_detail:
        for d in overrides_detail[:15]:
            print(d)
        if len(overrides_detail) > 15:
            print(f"  ... and {len(overrides_detail)-15} more")
    return rows


def fetch_yfinance_balance_sheet_fallback(rows, sec_data, watchlist):
    """
    For names where SEC EDGAR returned no total_debt, fetch fallback values
    from yfinance's .info dictionary (totalDebt, totalCash). yfinance covers
    foreign filers and non-SEC filers that SEC EDGAR cannot.

    Limitations:
    - yfinance values are point-in-time from latest available filing (annual for
      foreign filers, quarterly for US filers). Mixing with SEC LTM data is fine
      for EV computation but not appropriate for trend metrics.
    - Values reported in company's local currency. For US tickers this is USD;
      for foreign ADRs and OTC tickers yfinance usually converts to USD but
      check the financialCurrency field.
    - Less authoritative than SEC EDGAR. We tag these rows with a separate source
      label so the UI can show the user the data is from yfinance, not SEC.

    Returns the updated rows. Modifies rows in place with new total_debt, cash,
    net_debt, and a _financials_source = "yfinance" marker.
    """
    if not YFINANCE_AVAILABLE:
        return rows
    candidates = []
    for r in rows:
        co = r.get('company', '')
        td = str(r.get('total_debt', '')).strip().lower()
        # Only fallback when SEC didn't populate total_debt
        if td in ('', 'n/a', 'none'):
            ticker = watchlist.get(co, {}).get('ticker', '').upper()
            if ticker:
                candidates.append((co, ticker, r))
    if not candidates:
        print("yfinance balance sheet fallback: no candidates needed.")
        return rows
    print(f"yfinance balance sheet fallback: pulling Total Debt and Cash for {len(candidates)} names...")
    succeeded = 0
    for co, ticker, row in candidates:
        try:
            info = yf.Ticker(ticker).info or {}
            total_debt = info.get('totalDebt')
            total_cash = info.get('totalCash')
            currency = info.get('financialCurrency', 'USD')
            # Only accept USD-denominated values to avoid FX mismatches against
            # USD market cap. Non-USD tickers (most foreign filers) get skipped.
            if currency and currency.upper() != 'USD':
                print(f"  {co} ({ticker}): yfinance reports in {currency}, skipping to avoid FX mismatch")
                continue
            if total_debt is not None:
                row['total_debt'] = f"{total_debt / 1e9:.1f}"
                # Also fill cash if SEC didn't have it
                if str(row.get('cash', '')).strip().lower() in ('', 'n/a', 'none') and total_cash is not None:
                    row['cash'] = f"{total_cash / 1e9:.1f}"
                # Compute net debt
                if total_cash is not None:
                    row['net_debt'] = f"{(total_debt - total_cash) / 1e9:.1f}"
                row['_financials_source'] = 'yfinance'
                # Clear the "Total debt not found" warning since we now have it
                warnings_list = row.get('_fin_warnings', [])
                row['_fin_warnings'] = [w for w in warnings_list if 'Total debt' not in w]
                succeeded += 1
                print(f"  {co} ({ticker}): Total Debt ${total_debt/1e9:.1f}B, Cash ${(total_cash or 0)/1e9:.1f}B")
            else:
                print(f"  {co} ({ticker}): no totalDebt in yfinance info")
        except Exception as e:
            print(f"  {co} ({ticker}): yfinance fallback error: {str(e)[:100]}")
    print(f"yfinance fallback: filled Total Debt for {succeeded}/{len(candidates)} names.")
    return rows


def fetch_commodities_fx():
    if not YFINANCE_AVAILABLE:
        return {}
    tickers = {"wti": "CL=F", "brent": "BZ=F", "gold": "GC=F",
               "eurusd": "EURUSD=X", "nasdaq": "^IXIC", "dow": "^DJI"}
    print(f"Fetching commodities, FX, and indices from yfinance...")
    try:
        hist = yf.download(" ".join(tickers.values()), period="5d", interval="1d",
                           group_by="ticker", auto_adjust=True,
                           progress=False, threads=True)
    except Exception as e:
        print(f"WARNING: commodities/FX/indices fetch failed: {e}")
        return {}
    result = {}
    for key, ticker in tickers.items():
        try:
            if ticker in hist.columns.get_level_values(0):
                df = hist[ticker].dropna()
            else:
                df = hist.dropna()
            if df.empty or 'Close' not in df.columns:
                continue
            closes = df['Close']
            current = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) > 1 else current
            if prev == 0:
                pct = "n/a"
            else:
                p = (current - prev) / prev * 100
                sign = "+" if p >= 0 else "-"
                pct = f"{sign}{abs(p):.1f}"
            if key == "eurusd":
                result[key] = {"value": f"{current:.4f}", "change": pct}
            elif key in ("nasdaq", "dow"):
                result[key] = {"value": f"{int(current):,}", "change": pct}
            else:
                result[key] = {"value": f"{current:.2f}", "change": pct}
        except Exception as e:
            print(f"  {ticker} ({key}): {str(e)[:80]}")
    print(f"Commodities/FX/indices: {len(result)}/{len(tickers)} succeeded.")
    return result


BATCH_A_NAMES = ["AT&T", "Verizon", "Comcast", "Disney", "Warner Bros. Discovery", "Netflix",
    "Amazon", "Alphabet", "Microsoft", "Oracle", "Salesforce", "IBM",
    "Apple", "Nutanix", "Broadcom",
    "HP Inc", "HPE", "Dell", "Nextracker",
    "Sanmina", "Flex Ltd", "Jabil",
    "Arrow Electronics", "Avnet", "TD Synnex", "Ingram Micro", "CDW",
    "Kyndryl", "Cognizant",
    "Equinix", "Digital Realty", "American Tower",
    "PayPal", "Corpay", "Mastercard", "Visa", "Lagardère"]

BATCH_B_NAMES = ["Booking Holdings", "Uber", "Delta", "Carnival", "Royal Caribbean",
    "Norwegian Cruise Line", "Turkish Airlines",
    "General Motors", "Tesla", "Ford", "Toyota", "Nissan",
    "BMW", "Volkswagen", "Mercedes-Benz", "Hyundai",
    "Boeing", "GE Aerospace",
    "Daimler Truck", "PACCAR", "Cummins", "Wabtec", "CNH Industrial",
    "Walmart", "AutoZone", "Genuine Parts", "Costco Wholesale", "Home Depot",
    "O'Reilly Automotive", "WH Smith", "Seven & i Holdings",
    "Coca-Cola", "Coca-Cola Consolidated", "Anheuser-Busch InBev",
    "Philip Morris", "Altria", "Imperial Brands", "Universal Corporation"]

BATCH_C_NAMES = ["Nike", "Kimberly-Clark", "Whirlpool", "Mondelez",
    "Ball Corp", "Crown Holdings", "International Paper",
    "Colgate-Palmolive", "Kenvue", "Coty",
    "Archer-Daniels-Midland", "Bunge", "Ingredion",
    "JBS", "Pilgrim's Pride", "Kraft Heinz", "Grupo Bimbo", "Alicorp",
    "Krispy Kreme",
    "LVMH", "EssilorLuxottica",
    "AbbVie", "Eli Lilly", "Johnson & Johnson", "Merck & Co", "Pfizer",
    "AstraZeneca", "GSK", "Roche Holding", "Bayer",
    "Cardinal Health", "Cencora", "McKesson",
    "Sodexo", "Rentokil Initial", "Brink's",
    "Realty Income"]

BATCH_D_NAMES = ["Chevron", "BP", "Exxon", "Phillips 66",
    "Woodside Energy", "Equinor", "Shell", "TotalEnergies",
    "Halliburton", "SLB", "Baker Hughes", "TechnipFMC",
    "Cheniere Energy", "Enbridge",
    "NextEra Energy", "NextEra Energy Partners",
    "Duke Energy", "Sempra Energy",
    "AES", "Dominion Energy", "Edison International",
    "Constellation Energy", "Southern Company", "PPL Corporation",
    "NRG Energy",
    "RWE", "Uniper", "Engie", "Enel",
    "Clearway Energy Group", "Brookfield Renewable Partners", "Fluence Energy",
    "Amrize", "CEMEX", "Holcim", "Saint-Gobain", "NVR"]

BATCH_E_NAMES = ["Caterpillar", "Deere", "Danaher", "GE Vernova", "Honeywell",
    "Otis", "Air Products", "Corteva", "DuPont",
    "3M", "Parker Hannifin", "Pentair", "Air Lease Corporation",
    "Gerdau", "Michelin",
    "Generac Holdings", "Siemens Energy", "Siemens",
    "Dow", "LyondellBasell", "Olin Corporation", "Albemarle",
    "Linde", "FMC Corporation", "Ecolab", "Nutrien", "PPG Industries",
    "Braskem", "Brenntag",
    "Barrick Gold", "Newmont", "Teck Resources",
    "Blackstone", "KKR", "Apollo Global Management",
    "Brookfield Infrastructure Partners",
    "Simon Property Group"]


def _build_batch_prompt(batch_id, batch_label, batch_names, include_macro=False, include_top3=False):
    """Build a Claude prompt for one batch of the watchlist.
    Macro and top3 sections only appear in the final batch (E)."""
    names_str = "\n".join(f"- {co}" for co in batch_names)
    macro_section = ""
    macro_output = ""
    top3_section = ""
    top3_output = ""
    if include_macro:
        macro_section = """

MACRO INDICATORS (FALLBACK ONLY - HY OAS and IG OAS pulled from FRED, NOT from this prompt):
DO NOT search for HY OAS or IG OAS. Always return "n/a" for those fields. Source only the items below:
- VIX index level (cboe.com or yahoo.com/finance)
- S&P 500 level and 1-day percentage change"""
        macro_output = '"macro": {"hy_oas": "n/a", "ig_oas": "n/a", "treasury_10y": "n/a", "treasury_2y": "n/a", "vix": "18.2", "sp500": "5234", "sp500_1d": "+0.8"}, '
    if include_top3:
        top3_section = """
- top3: 3 names from across ALL 5 batches most requiring attention today."""
        top3_output = ', "top3": [{"name": "Company A", "note": "Short reason"}]'

    return f"""Today is {datetime_str}. You are generating structured data for a morning credit intelligence dashboard for publicly listed US and global corporates.

Watchlist - BATCH {batch_id} ({len(batch_names)} names): {batch_label}
{names_str}

For each company gather the data below using these source priorities:

FINANCIAL METRICS (Market Cap, Net Debt/EBITDA, EBITDA Margin, FCF LTM, Cash, Total Debt):
DO NOT search for financial data. Return "n/a" for these fields. They are pulled from SEC EDGAR programmatically after your response and your estimates are not used. Skip these completely to save search budget.

STOCK DATA (1-day, 1-month, YTD percentage changes, 52-week high, 52-week low):
DO NOT search for stock prices. Return "n/a" for these fields. They are pulled from yfinance programmatically after your response and your estimates are not used. Skip these completely to save search budget.

NEXT EARNINGS DATE:
Source from earningswhispers.com, yahoo.com/finance, or the company's IR page.

NEWS (last 24 to 48 hours):
Source from reuters.com, bloomberg.com, wsj.com, ft.com, agency press releases, or sec.gov 8-K filings.

CREDIT RATINGS - CRITICAL ACCURACY RULES:
For each agency (Moody's, S&P, Fitch) for EACH company, you MUST perform multiple targeted searches. Required search sequence per agency per company:
1. First search: "[Company] [Agency] rating action 2026"
2. Second search if needed: "[Company] [Agency] credit rating 2025"
3. Third search if needed: "[Company] credit rating [Agency] downgrade upgrade outlook"

Source priority (use in this order):
1. Agency press releases (moodys.com, spglobal.com, fitchratings.com) - most authoritative
2. Reuters, Bloomberg, Investing.com, Yahoo Finance rating action articles
3. Company 10-K, prospectus, or IR page disclosures

CRITICAL ACCURACY REQUIREMENTS:
- Always return the date of the MOST RECENT rating action found (YYYY-MM-DD format)
- Compare dates across sources - use the source with the most recent date
- If two sources disagree on rating, use the one with the most recent date
- Distinguish issuer/corporate family rating from issue-specific (bond-level) ratings - use the ISSUER rating
- For Moody's: use issuer rating or Corporate Family Rating (CFR), NOT senior unsecured if different
- Do NOT confuse outlook with rating - outlook is Stable/Positive/Negative/RUR, separate from the letter grade
- For foreign filers (non-US listed companies), use the parent entity rating, not subsidiary ratings
- A rating action includes: upgrade, downgrade, affirmation, outlook change, or watch placement
- For each rating, the date should reflect the most recent rating action

KEY DEVELOPMENT (key_dev field) - CRITICAL FOR CREDIT SURVEILLANCE:
For each name, search for any of these MATERIAL CREDIT EVENTS in the last 60 days:
1. Rating actions: upgrades, downgrades, outlook changes, ratings affirmed with comments
2. Capital structure: spin-off announcements, M&A, debt issuance, refinancing, dividend changes, buyback authorizations
3. Financial events: covenant amendments, covenant breaches, defaults, missed payments
4. Strategic events: management changes, restructuring, contract wins/losses, strategic reviews
5. Earnings: significant beats, misses, guidance changes, withdrawn guidance
6. Legal/Regulatory: SEC investigations, material litigation, regulatory penalties
7. Operational: major customer wins/losses, supply chain disruptions, plant closures

Apply this rule regardless of green/amber/red status. A name can be GREEN-rated and still have material credit-relevant news.{macro_section}

Use web search to source values. For well-known public companies, use your best available knowledge if a specific value is not directly returned by search. Only return "n/a" if the value is genuinely unknowable.

CONCERN SCORE - compute for every row as an integer 0-100:
Start at 0 and add points as follows:
- +25 if status is red
- +10 if status is amber
- +15 if nd_ebitda > 5.0
- +10 if stock_ytd starts with "-" and absolute value > 20
- +10 if stock_1m starts with "-" and absolute value > 10
- +10 if next earnings date is within 14 calendar days of today
- +10 if key_dev mentions downgrade, default, covenant breach, or restructuring
- +10 if fcf_ltm is negative
- +10 if ebitda_margin < 10
- +10 if any rating outlook is Negative or RUR (across Moody's, S&P, Fitch)
- Cap the total at 100.

OUTPUT FORMAT: Your ENTIRE response must be ONLY a single JSON object. Start with {{ as the very first character. End with }} as the very last character. ABSOLUTELY NO preamble, explanation, acknowledgment, markdown formatting, or code fences. NO text like "Here is" or "I will provide". The response must be directly parseable by json.loads().

{{{macro_output}"rows": [{{"company": "Company Name", "sector": "Sector", "status": "red|amber|green", "mkt_cap": "12.5", "nd_ebitda": "2.4", "ebitda_margin": "18.5", "fcf_ltm": "1.8", "cash": "5.2", "total_debt": "15.0", "earnings": "Jul 23", "stock_1d": "+1.2", "stock_1m": "+1.2", "stock_ytd": "+1.2", "week52_high": "185.50", "week52_low": "112.30", "moodys_rating": "Baa2", "moodys_outlook": "Stable", "moodys_date": "2025-10-15", "sp_rating": "BBB", "sp_outlook": "Stable", "sp_date": "2025-09-22", "fitch_rating": "BBB", "fitch_outlook": "Stable", "fitch_date": "2025-08-10", "concern_score": 35, "key_dev": "No material news.", "action": "Monitor"}}]{top3_output}}}

Rules:
- All {len(batch_names)} names must appear in rows.
- All dollar figures in $Bn. Round to one decimal.
- Net Debt/EBITDA: number only, no "x".
- EBITDA Margin: number only, no % sign.
- Stock percentages: string with + or - prefix, no % symbol.
- week52_high and week52_low: USD price, no $ sign, two decimals.
- concern_score: integer 0-100.
- Ratings: agency-native format (Moody's: Aaa/Aa1/.../C; S&P and Fitch: AAA/AA+/.../D). "n/a" if not rated.
- Outlook: Stable, Positive, Negative, RUR, or n/a.
- Rating date: YYYY-MM-DD format, date of most recent action.
- action: use one of "Monitor" (green), "Watch" (amber), "Review" (red, manageable), "Escalate" (red, urgent).
- key_dev: 1-2 sentences, under 200 characters. Cite the EVENT. If a name truly has NO material news in the last 60 days, return exactly "No material news.".{top3_section}
- Public information only."""


PROMPT_A = _build_batch_prompt("A", "Tech, Media, Telecom, Datacenter, Software, Payments", BATCH_A_NAMES)
PROMPT_B = _build_batch_prompt("B", "Travel, Auto, Aerospace, Trucks, Retail, Beverage, Tobacco", BATCH_B_NAMES)
PROMPT_C = _build_batch_prompt("C", "Consumer, Packaging, Food, Personal Care, Pharma, Healthcare", BATCH_C_NAMES)
PROMPT_D = _build_batch_prompt("D", "Energy, Utilities, Midstream, Renewables, Materials", BATCH_D_NAMES)
PROMPT_E = _build_batch_prompt("E", "Industrials, Chemicals, Mining, Asset Managers, REITs", BATCH_E_NAMES, include_macro=True, include_top3=True)


def call_claude(prompt, batch_name):
    print(f"Calling Claude for {batch_name}...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 25}],
        messages=[{"role": "user", "content": prompt}]
    )
    for block in reversed(response.content):
        if hasattr(block, 'text'):
            return block.text.strip()
    return ""


def parse_json(raw, label):
    """
    Defensive JSON extraction. Claude sometimes prefixes responses with preamble
    text or wraps in markdown code blocks despite explicit prompting. This
    function tries multiple strategies in order:
      1. Parse as-is (works when Claude obeyed the prompt)
      2. Strip markdown code fences
      3. Find the largest balanced {...} block using a proper bracket counter
         (handles preamble before AND trailing text after the JSON)
      4. Scan for multiple candidate JSON objects and pick the largest valid one
    """
    if not raw:
        return None, f"JSON parse error in {label}: empty response"
    cleaned = raw.strip()

    # Strategy 1: parse as-is
    try:
        return json.loads(cleaned), None
    except Exception:
        pass

    # Strategy 2: strip markdown code fences if present
    if '```' in cleaned:
        # Find content between triple backticks (with or without language tag)
        m = re.search(r'```(?:json)?\s*(.+?)```', cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip()), None
            except Exception:
                pass

    # Strategy 3: find largest balanced {...} block using bracket counter
    # This properly handles preamble before and trailing text after the JSON,
    # even if the preamble contains stray { or } characters in code/examples.
    best_candidate = None
    best_length = 0
    depth = 0
    start_idx = -1
    in_string = False
    escape_next = False
    for i, ch in enumerate(cleaned):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            if depth == 0:
                start_idx = i
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start_idx != -1:
                    candidate_str = cleaned[start_idx:i+1]
                    candidate_len = len(candidate_str)
                    # Try parsing this candidate; keep the largest valid one
                    try:
                        parsed = json.loads(candidate_str)
                        if candidate_len > best_length:
                            best_candidate = parsed
                            best_length = candidate_len
                    except Exception:
                        pass
                    start_idx = -1
    if best_candidate is not None:
        return best_candidate, None

    # Strategy 4: salvage attempt - find first { and last } and try with truncation
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start:end+1]
        # Strip everything before "rows" key if it looks like data is there
        try:
            return json.loads(candidate), None
        except Exception as e:
            preview = cleaned[:400].replace('\n', ' ')
            return None, f"JSON parse error in {label}: {str(e)[:150]} | First 400 chars: {preview}"
    preview = cleaned[:400].replace('\n', ' ')
    return None, f"JSON parse error in {label}: no JSON object found | First 400 chars: {preview}"


def apply_overrides(rows):
    overridden = 0
    news_overridden = 0
    rating_fields = ['moodys_rating','moodys_outlook','moodys_date','sp_rating','sp_outlook','sp_date','fitch_rating','fitch_outlook','fitch_date']
    today_date = datetime.now().date()
    for r in rows:
        co = r.get('company','')
        if co in RATINGS_OVERRIDE:
            ov = RATINGS_OVERRIDE[co]
            for f in rating_fields:
                if f in ov:
                    r[f] = ov[f]
            overridden += 1
        # Apply news override if present and not expired
        if co in NEWS_OVERRIDE:
            nv = NEWS_OVERRIDE[co]
            # Check expiry
            expires_str = nv.get('expires')
            expired = False
            if expires_str:
                try:
                    expires_date = datetime.strptime(expires_str, '%Y-%m-%d').date()
                    if today_date > expires_date:
                        expired = True
                except (ValueError, TypeError):
                    pass
            if not expired:
                key_dev = nv.get('key_dev')
                if key_dev:
                    r['key_dev'] = key_dev
                    news_overridden += 1
    if overridden:
        print(f"Applied manual ratings overrides to {overridden} companies.")
    if news_overridden:
        print(f"Applied manual news overrides to {news_overridden} companies.")
    return rows


def _normalize_company_names(rows, watchlist):
    """Map Claude-returned company names back to WATCHLIST canonical keys.

    Claude often expands canonical names in its JSON output ("Delta" ->
    "Delta Air Lines", "Carnival" -> "Carnival Corporation", "Ford" ->
    "Ford Motor"). The downstream pipeline matches rows to data sources
    (SEC EDGAR overrides, yfinance market data, yfinance balance-sheet
    fallback, ratings overrides) by EXACT company name. A name mismatch
    silently drops the row from those data sources and leaves it as n/a.

    Strategy (conservative to avoid false positives):
    1. Exact match - already canonical, no change.
    2. Case-insensitive exact match.
    3. Whole-word prefix match: WATCHLIST key is a prefix of the Claude
       name, followed by space/comma/hyphen. Disambiguate via longest
       matching key (so "Coca-Cola Consolidated, Inc." correctly matches
       "Coca-Cola Consolidated", not "Coca-Cola").

    Leaves the Claude name unchanged when no match is found. Logs any
    unmatched rows so the user can update WATCHLIST if needed.
    """
    wl_keys = list(watchlist.keys())
    wl_lower_to_key = {k.lower(): k for k in wl_keys}

    renamed = 0
    unmatched = []
    rename_log = []
    for r in rows:
        claude_name = (r.get('company') or '').strip()
        if not claude_name:
            continue

        # 1. Exact match
        if claude_name in watchlist:
            continue

        # 2. Case-insensitive exact match
        cn_lower = claude_name.lower()
        if cn_lower in wl_lower_to_key:
            wl_key = wl_lower_to_key[cn_lower]
            r['company'] = wl_key
            rename_log.append(f"{claude_name} -> {wl_key}")
            renamed += 1
            continue

        # 3. Whole-word prefix match (longest WATCHLIST key wins)
        best = None
        best_len = 0
        for wl_key in wl_keys:
            wl_lower = wl_key.lower()
            if (cn_lower.startswith(wl_lower + ' ')
                or cn_lower.startswith(wl_lower + ',')
                or cn_lower.startswith(wl_lower + '-')):
                if len(wl_lower) > best_len:
                    best = wl_key
                    best_len = len(wl_lower)
        if best:
            r['company'] = best
            rename_log.append(f"{claude_name} -> {best}")
            renamed += 1
        else:
            unmatched.append(claude_name)

    if renamed:
        print(f"Normalized {renamed} Claude-returned names to WATCHLIST canonical keys.")
        for entry in rename_log[:15]:
            print(f"  {entry}")
        if len(rename_log) > 15:
            print(f"  ... and {len(rename_log) - 15} more")
    if unmatched:
        print(f"WARNING: {len(unmatched)} rows had names not matching WATCHLIST. First 10: {unmatched[:10]}")

    return rows


# =============================================================================
# Smart Caching Architecture
# =============================================================================
# Two run modes:
#   "full":  Full Claude refresh (Batches A+B + second-pass). ~$5-7/run.
#            Runs on Fridays, and also on Mon-Thu if cache is >10 days stale.
#   "cheap": Skip Batches A+B. Use cached ratings + news. Selectively re-query
#            Claude for news of amber/red names only (1 small call, ~$1.50).
#            Market data, SEC EDGAR, FRED, OWID all refresh as normal.
#
# Cache file: claude_cache.json. Structure:
# {
#   "_last_full_refresh": "2026-05-15T12:00:00Z",
#   "_run_id": "2026-05-15-0800",
#   "rows": [
#     { "company": "AT&T", "moodys_rating": "Baa2", ..., "key_dev": "...",
#       "_cached_at": "2026-05-15T12:00:00Z" },
#     ...
#   ],
#   "macro": { ... },
#   "top3": [ ... ]
# }
# =============================================================================

CLAUDE_CACHE_PATH = "claude_cache.json"
CACHE_STALE_DAYS = 10  # Auto-escalate to full mode after this many days


def determine_run_mode():
    """
    Decide whether this run is 'full' (Claude Batches A+B) or 'cheap' (cache reuse).

    Logic:
    - If env var RUN_MODE is explicitly set, use it (full|cheap|auto). Default: auto.
    - In auto mode:
      - Friday (weekday 4) -> full
      - Other weekdays -> cheap, unless cache is missing/stale
      - If claude_cache.json missing or _last_full_refresh > 10 days ago -> escalate to full
    """
    env_mode = os.environ.get("RUN_MODE", "auto").lower().strip()
    if env_mode in ("full", "cheap"):
        print(f"Run mode: {env_mode} (forced via RUN_MODE env var)")
        return env_mode

    today_local = now.date()
    weekday = today_local.weekday()  # Monday=0, Friday=4
    is_friday = (weekday == 4)

    cache = None
    if os.path.exists(CLAUDE_CACHE_PATH):
        try:
            with open(CLAUDE_CACHE_PATH, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = None

    cache_age_days = None
    if cache and cache.get("_last_full_refresh"):
        try:
            last_full = datetime.fromisoformat(cache["_last_full_refresh"].replace("Z", "+00:00"))
            cache_age_days = (datetime.now(pytz.utc) - last_full).days
        except Exception:
            cache_age_days = None

    if not cache:
        print(f"Run mode: full (no cache file found, building fresh)")
        return "full"

    if cache_age_days is not None and cache_age_days > CACHE_STALE_DAYS:
        print(f"Run mode: full (cache is {cache_age_days} days old, exceeds {CACHE_STALE_DAYS}-day stale threshold)")
        return "full"

    if is_friday:
        print(f"Run mode: full (Friday weekly refresh)")
        return "full"

    print(f"Run mode: cheap (cache is {cache_age_days} days old; non-Friday weekday)")
    return "cheap"


def load_claude_cache():
    """Load cached Claude output from disk. Returns (rows_list, macro_dict, top3_list, last_refresh_str)."""
    if not os.path.exists(CLAUDE_CACHE_PATH):
        return [], {}, [], None
    try:
        with open(CLAUDE_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("rows", [])
        macro = data.get("macro", {})
        top3 = data.get("top3", [])
        last_refresh = data.get("_last_full_refresh")
        print(f"Loaded claude_cache.json: {len(rows)} rows, last full refresh {last_refresh}")
        return rows, macro, top3, last_refresh
    except Exception as e:
        print(f"WARNING: claude_cache.json failed to load: {e}")
        return [], {}, [], None


def save_claude_cache(rows, macro, top3):
    """Persist Claude output to disk for reuse on cheap-mode days."""
    payload = {
        "_last_full_refresh": datetime.now(pytz.utc).isoformat(),
        "_run_id": now.strftime("%Y-%m-%d-%H%M"),
        "rows": rows,
        "macro": macro,
        "top3": top3,
    }
    try:
        with open(CLAUDE_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"Saved claude_cache.json with {len(rows)} rows.")
    except Exception as e:
        print(f"WARNING: failed to save claude_cache.json: {e}")


def cheap_mode_news_refresh(all_rows):
    """
    On cheap-mode days, refresh news ONLY for names currently flagged amber/red.
    Green names keep their cached key_dev from the last full run.

    Returns updated rows. Costs ~$1-2 per call (1 Claude call, max 15 names).
    """
    candidates = []
    for r in all_rows:
        status = str(r.get("status", "")).lower()
        if status in ("amber", "red"):
            candidates.append(r.get("company", ""))

    if not candidates:
        print("Cheap-mode news refresh: no amber/red names; skipping Claude call.")
        return all_rows

    # Cap at 15 to keep search budget per name high (~1.7 per name)
    candidates = candidates[:15]
    print(f"Cheap-mode news refresh: querying Claude for {len(candidates)} amber/red names: {', '.join(candidates)}")

    names_str = "\n".join(f"- {co}" for co in candidates)
    prompt = f"""Today is {datetime_str}. You are a credit analyst refreshing daily news for amber/red status names. Find the MOST RECENT material credit-relevant event for each.

Companies:
{names_str}

For EACH company, search the web for material credit events in the last 14 days. Focus on:
1. Rating actions (Moody's, S&P, Fitch press releases)
2. M&A, spin-offs, divestitures, debt issuance, refinancing
3. Earnings results, guidance changes
4. Covenant breaches, defaults, going concern
5. Material 8-K filings
6. Strategic announcements (management changes, restructuring)

Be specific: cite dates, dollar amounts. If truly no news in last 14 days, return "No material news."

OUTPUT FORMAT: ONLY a single JSON object. Start with {{ end with }}. No preamble, no markdown.

{{"updates": [{{"company": "Exact Name", "key_dev": "1-2 sentences under 200 chars with date"}}]}}

Rules:
- Include EVERY company in the list
- Use the EXACT company name as input
- Public information only"""

    try:
        raw = call_claude(prompt, "Cheap-mode news refresh")
        data, err = parse_json(raw, "Cheap-mode news refresh")
        if err or not data:
            print(f"Cheap-mode news refresh: parse error; keeping cached news. Detail: {err}")
            return all_rows
        updates = data.get("updates", [])
        name_to_update = {u.get("company", "").strip(): u.get("key_dev", "") for u in updates}
        updated_count = 0
        for r in all_rows:
            co = r.get("company", "")
            if co in name_to_update:
                new_dev = name_to_update[co]
                if new_dev and new_dev.lower() not in ("no material news.", "no material news", "n/a", ""):
                    r["key_dev"] = new_dev
                    updated_count += 1
        print(f"Cheap-mode news refresh: updated {updated_count} of {len(candidates)} candidates.")
    except Exception as e:
        print(f"Cheap-mode news refresh: exception, keeping cached news. Detail: {str(e)[:200]}")
    return all_rows


# =============================================================================
# End smart caching block
# =============================================================================



def is_stale(date_str):
    if not date_str or date_str == 'n/a':
        return False
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        return (today - d).days > 365
    except:
        return False


def outlook_color(outlook):
    o = (outlook or '').strip().lower()
    if o == 'negative' or o == 'rur': return '#ff6b6b'
    if o == 'positive': return '#4ec38a'
    if o == 'stable': return '#7a8a9a'
    return '#3a4a5a'


def stock_cell(v):
    v = str(v or 'n/a').strip()
    if v.startswith('+'):
        return f'<td class="num-cell stock-up">{v}%</td>'
    elif v.startswith('-'):
        return f'<td class="num-cell stock-down">{v}%</td>'
    return f'<td class="num-cell stock-flat">{v if v else "n/a"}</td>'


def num_cell(v, suffix=''):
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    return f'<td class="num-cell">{v}{suffix}</td>'


def week52_cell(level_v, current_v, kind='high'):
    """
    Render 52W high or low with context: shows the price AND % distance from current.
    For 52W high: shows "% below high" (negative number = how much current price is below 52W high)
    For 52W low: shows "% above low" (positive number = how much current price is above 52W low)
    """
    level_str = str(level_v or 'n/a').strip()
    if not level_str or level_str == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    try:
        level = float(level_str)
        current = float(str(current_v or '').replace('$','').replace(',','').strip())
        if level == 0:
            return f'<td class="num-cell">{level_str}</td>'
        pct = (current - level) / level * 100
        if kind == 'high':
            # pct will be 0 or negative; show as "-X.X%" in red if material
            if pct >= -2:
                color_class = 'stock-flat'
                pct_str = f"{pct:+.1f}%"
            elif pct >= -10:
                color_class = 'stock-down'
                pct_str = f"{pct:.1f}%"
            else:
                color_class = 'stock-down'
                pct_str = f"{pct:.1f}%"
        else:
            # 52W low: pct will be 0 or positive; show as "+X.X%" in green if material
            if pct <= 2:
                color_class = 'stock-flat'
                pct_str = f"{pct:+.1f}%"
            elif pct <= 20:
                color_class = 'stock-up'
                pct_str = f"+{pct:.1f}%"
            else:
                color_class = 'stock-up'
                pct_str = f"+{pct:.1f}%"
        return f'<td class="num-cell"><div style="line-height:1.3">{level_str}<div class="{color_class}" style="font-size:9px;font-weight:600">{pct_str}</div></div></td>'
    except (ValueError, TypeError):
        return f'<td class="num-cell">{level_str}</td>'


def yoy_cell(v):
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    try:
        f = float(v)
        if f > 0: return f'<td class="num-cell stock-up">+{f:.1f}%</td>'
        if f < 0: return f'<td class="num-cell stock-down">{f:.1f}%</td>'
        return f'<td class="num-cell stock-flat">{f:.1f}%</td>'
    except:
        return f'<td class="num-cell">{v}%</td>'


def leverage_cell(v):
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    try:
        f = float(v)
        if f < 0: return f'<td class="num-cell stock-up">{f:.1f}x</td>'
        if f > 5: cls = 'stock-down'
        elif f > 3: cls = 'lev-amber'
        else: cls = 'stock-up'
        return f'<td class="num-cell {cls}">{f:.1f}x</td>'
    except:
        return f'<td class="num-cell">{v}</td>'


def margin_cell(v):
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    try:
        f = float(v)
        if f < 10: cls = 'stock-down'
        elif f < 20: cls = 'lev-amber'
        else: cls = 'stock-up'
        sign = '+' if f >= 0 else ''
        return f'<td class="num-cell {cls}">{sign}{f:.1f}%</td>'
    except:
        return f'<td class="num-cell">{v}%</td>'


def fcf_cell(v):
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    try:
        f = float(v)
        if f < 0: return f'<td class="num-cell stock-down">-${abs(f):,.1f}</td>'
        return f'<td class="num-cell stock-up">${f:,.1f}</td>'
    except:
        return f'<td class="num-cell">{v}</td>'


def ratings_cell_compact(r):
    agencies = [('moodys_rating','moodys_outlook','M'),
                ('sp_rating','sp_outlook','S'),
                ('fitch_rating','fitch_outlook','F')]
    lines = []
    for rf, of, label in agencies:
        rating = r.get(rf,'n/a') or 'n/a'
        outlook = r.get(of,'n/a') or 'n/a'
        outlook_short = outlook[:3].upper() if outlook != 'n/a' else '-'
        color = outlook_color(outlook)
        lines.append(
            f'<div class="rating-row-compact">'
            f'<span class="agency-tag">{label}</span>'
            f'<span class="rating-val">{rating}</span>'
            f'<span class="outlook-tag" style="color:{color}">{outlook_short}</span>'
            f'</div>'
        )
    return f'<td class="ratings-cell">{"".join(lines)}</td>'


def last_action_cell(r):
    candidates = [('moodys_date', "Moody's"), ('sp_date', 'S&P'), ('fitch_date', 'Fitch')]
    valid = []
    for field, name in candidates:
        d = r.get(field, 'n/a') or 'n/a'
        if d != 'n/a':
            try:
                parsed = datetime.strptime(d, '%Y-%m-%d').date()
                valid.append((parsed, name, d))
            except:
                pass
    if not valid:
        return '<td class="action-date-cell"><div class="action-date-na">No date</div></td>'
    valid.sort(reverse=True)
    most_recent, agency, raw_date = valid[0]
    try:
        display = most_recent.strftime('%b %d, %Y')
    except:
        display = raw_date
    stale = is_stale(raw_date)
    stale_mark = ' <span class="stale-flag" title="Over 12 months old">&#9888;</span>' if stale else ''
    return (
        f'<td class="action-date-cell">'
        f'<div class="action-date-main">{display}{stale_mark}</div>'
        f'<div class="action-date-sub">{agency}</div>'
        f'</td>'
    )


def concern_cell_redesigned(r, status):
    flag_count = r.get('_flag_count')
    watch_count = r.get('_watch_count', 0)
    total_flags = 9
    if flag_count is not None:
        try:
            from red_flags import flag_count_tier
            tier = flag_count_tier(flag_count, watch_count)
        except ImportError:
            tier = 'Comfortable'
        if flag_count >= 5: color = '#ff6b6b'
        elif flag_count >= 3: color = '#ff6b6b'
        elif flag_count >= 1 or watch_count >= 3: color = '#f0b429'
        else: color = '#4ec38a'
        signal_strength = min(100, (flag_count * 2 + watch_count) / (total_flags * 2) * 100)
        watch_suffix = f' <span class="watch-suffix">+{watch_count}~</span>' if watch_count > 0 else ''
        return (
            f'<td class="concern-cell">'
            f'<div class="concern-num" style="color:{color}">{flag_count}<span class="concern-denom">/{total_flags}</span>{watch_suffix}</div>'
            f'<div class="concern-bar"><div style="background:{color};width:{signal_strength:.0f}%"></div></div>'
            f'<div class="concern-tier">{tier}</div>'
            f'</td>'
        )
    try:
        score = int(r.get('concern_score', 0))
    except:
        score = 0
    color = '#ff6b6b' if score >= 70 else ('#f0b429' if score >= 40 else '#4ec38a')
    tier = 'Escalate' if score >= 80 else ('Review' if score >= 60 else ('Watch' if score >= 40 else 'Comfortable'))
    return (
        f'<td class="concern-cell">'
        f'<div class="concern-num" style="color:{color}">{score}<span class="concern-denom">/100</span></div>'
        f'<div class="concern-bar"><div style="background:{color};width:{min(score,100)}%"></div></div>'
        f'<div class="concern-tier">{tier}</div>'
        f'</td>'
    )


def _build_status_tooltip(row):
    """Build hover-text explaining why a row has its status (which flags fired)."""
    flags = row.get('_flags', {}) or {}
    if not flags:
        return ""
    fired = []
    watched = []
    # Stable order: by flag id (1..15)
    for fid in sorted(flags.keys(), key=lambda x: (len(str(x)), str(x))):
        state = (flags[fid].get('state') or '').upper()
        reason = flags[fid].get('reason') or ''
        if state == 'FLAGGED':
            fired.append(f"  • {fid}: {reason}")
        elif state == 'WATCH':
            watched.append(f"  ~ {fid}: {reason}")
    co = row.get('company', '')
    severity = (row.get('severity') or '').upper()
    fc = int(row.get('_flag_count', 0) or 0)
    wc = int(row.get('_watch_count', 0) or 0)
    parts = [f"{co} - {severity}", f"{fc} flagged + {wc} watch", ""]
    if fired:
        parts.append("FLAGGED:")
        parts.extend(fired)
    if watched:
        if fired:
            parts.append("")
        parts.append("WATCH:")
        parts.extend(watched)
    if not fired and not watched:
        parts.append("No flag triggers fired.")
    # title attribute can't contain certain characters easily; use plain text
    tooltip = "\n".join(parts).replace('"', "'")
    return tooltip


def status_cell_redesigned(status, severity=None, row=None):
    """
    Render status badge with four-tier severity coloring and a hover tooltip
    showing WHY (which flags fired).

    severity options:
      - 'critical' -> red text on faint tint, "CRITICAL" label
      - 'high'     -> orange text on faint tint, "HIGH" label
      - 'watch'    -> amber text on amber tint, "AMBER" label
      - 'monitor'  -> green text on green tint, "GREEN" label
      - None       -> falls back to legacy status (red/amber/green)
    """
    tooltip = _build_status_tooltip(row) if row else ""
    title_attr = f' title="{tooltip}"' if tooltip else ""
    if severity in ('critical', 'high', 'watch', 'monitor'):
        label_map = {'critical': 'CRITICAL', 'high': 'HIGH', 'watch': 'AMBER', 'monitor': 'GREEN'}
        label = label_map[severity]
        return f'<td><span class="status-badge severity-{severity}"{title_attr}>{label}</span></td>'
    return f'<td><span class="status-badge {status}"{title_attr}>{status.upper()}</span></td>'


def status_label_cell(status, severity=None):
    """
    Plain status cell for Market Data, Financials, TMT, Red Flags tabs.
    Returns a colored text cell (not a badge) consistent with severity tier.
    Falls back to legacy status if no severity provided.
    """
    if severity == 'critical':
        return '<td class="status" style="color:#ff5a5a;background:rgba(255,90,90,.10);font-weight:700;text-align:center">CRITICAL</td>'
    elif severity == 'high':
        return '<td class="status" style="color:#ff8a3d;background:rgba(255,138,61,.10);font-weight:700;text-align:center">HIGH</td>'
    elif severity == 'watch':
        return f'<td class="status amber">AMBER</td>'
    elif severity == 'monitor':
        return f'<td class="status green">GREEN</td>'
    # Legacy fallback
    return f'<td class="status {status}">{status.upper()}</td>'


def company_cell_redesigned(r):
    return (
        f'<td class="co-cell-stack">'
        f'<div class="co-name">{r.get("company","")}</div>'
        f'<div class="co-sector">{r.get("sector","").upper()}</div>'
        f'</td>'
    )


def action_cell_redesigned(r):
    """Action button styled per severity tier (escalate/review/watch/monitor)."""
    severity = (r.get('severity') or '').lower()
    if severity == 'critical':
        cls, text = 'escalate', 'Escalate'
    elif severity == 'high':
        cls, text = 'review', 'Review'
    elif severity == 'watch':
        cls, text = 'watch', 'Watch'
    elif severity == 'monitor':
        cls, text = 'monitor', 'Monitor'
    else:
        # Fallback to action field if severity not set (defensive)
        action_l = (r.get('action') or 'Monitor').lower()
        if action_l in ('escalate', 'sell'): cls, text = 'escalate', 'Escalate'
        elif action_l in ('review', 'reduce'): cls, text = 'review', 'Review'
        elif action_l == 'watch': cls, text = 'watch', 'Watch'
        else: cls, text = 'monitor', 'Monitor'
    return f'<td><span class="action-redesigned {cls}">{text}</span></td>'


def price_cell(v):
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    return f'<td class="num-cell price-cell">${v}</td>'


def money_cell(v, decimals=1):
    v = str(v or 'n/a').strip()
    if not v or v == 'n/a':
        return '<td class="num-cell stock-flat">n/a</td>'
    try:
        num = float(v)
        if num < 0: formatted = f"-${abs(num):,.{decimals}f}"
        else: formatted = f"${num:,.{decimals}f}"
        return f'<td class="num-cell">{formatted}</td>'
    except (ValueError, TypeError):
        return f'<td class="num-cell">{v}</td>'


# Red flag rendering
# Source mapping per flag (which data source provides the inputs)
FLAG_SOURCES = {
    "leverage_high": "SEC EDGAR (XBRL)",
    "leverage_climbing": "SEC EDGAR (XBRL)",
    "coverage_thin": "SEC EDGAR (XBRL)",
    "burning_cash": "SEC EDGAR (Cash Flow Statement)",
    "wall_of_maturities": "SEC EDGAR (Capital Structure)",
    "refi_higher_rates": "SEC EDGAR + macro rates",
    "revenue_shrinking": "SEC EDGAR (XBRL)",
    "margin_compression": "SEC EDGAR (XBRL)",
    "stock_collapse": "yfinance (daily price history)",
    "rating_pressure": "Claude web search (agency press releases)",
    "bad_news": "Claude key_dev (keyword scan)",
    "liquidity_squeeze": "SEC EDGAR (Balance Sheet)",
    "going_concern": "SEC EDGAR + Claude",
    "insider_selling": "SEC Form 4 filings",
    "geographic_risk": "Claude geographic analysis",
}


def _build_flag_tooltip(fid, state, reason, flag_def):
    """Build hover tooltip for a single flag cell with name, source, value, thresholds."""
    name = flag_def.get("name", fid)
    threshold = flag_def.get("threshold", "")
    watch_threshold = flag_def.get("watch_threshold", "")
    source = FLAG_SOURCES.get(fid, "Multi-source")
    parts = [name, f"Source: {source}"]
    if reason:
        parts.append(f"Value: {reason}")
    if threshold and watch_threshold:
        parts.append(f"Threshold: FLAGGED {threshold}, WATCH {watch_threshold}")
    elif threshold:
        parts.append(f"Threshold: FLAGGED {threshold}")
    tooltip = "\n".join(parts).replace('"', "'")
    return tooltip


def redflag_cell(state, tooltip=""):
    """Render a flag cell with optional rich tooltip (name + source + value + threshold)."""
    title_attr = f' title="{tooltip}"' if tooltip else f' title="{state}"'
    style_attr = ' style="cursor:help"' if tooltip else ''
    if state == "FLAGGED":
        return f'<td class="rf-cell"><span class="rf-pill rf-flagged"{title_attr}{style_attr}>&#9888;</span></td>'
    if state == "WATCH":
        return f'<td class="rf-cell"><span class="rf-pill rf-watch"{title_attr}{style_attr}>~</span></td>'
    if state == "CLEAR":
        return f'<td class="rf-cell"><span class="rf-pill rf-clear"{title_attr}{style_attr}>&#10003;</span></td>'
    return f'<td class="rf-cell"><span class="rf-pill rf-na"{title_attr}{style_attr}>&mdash;</span></td>'


def build_redflag_rows(rows):
    if not rows:
        return []
    try:
        from red_flags import FLAG_DEFINITIONS
        flag_ids = [f["id"] for f in FLAG_DEFINITIONS]
        flag_defs_by_id = {f["id"]: f for f in FLAG_DEFINITIONS}
    except ImportError:
        flag_ids = []
        flag_defs_by_id = {}
    sorted_rows = sorted(
        [r for r in rows if r.get("_flags")],
        key=lambda r: (-(r.get("_flag_count") or 0), -(r.get("_watch_count") or 0), r.get("company", "").lower())
    )
    rf_rows = []
    for r in sorted_rows:
        flags = r.get("_flags", {})
        flag_count = r.get("_flag_count", 0)
        watch_count = r.get("_watch_count", 0)
        status = (r.get("status") or "green").lower()
        flag_cells = ""
        for fid in flag_ids:
            result = flags.get(fid, {})
            state = result.get("state", "N/A")
            reason = result.get("reason", "")
            flag_def = flag_defs_by_id.get(fid, {"id": fid, "name": fid})
            tooltip = _build_flag_tooltip(fid, state, reason, flag_def)
            flag_cells += redflag_cell(state, tooltip)
        if flag_count >= 3: count_color = "#ff6b6b"
        elif flag_count >= 1: count_color = "#f0b429"
        elif watch_count >= 3: count_color = "#f0b429"
        else: count_color = "#4ec38a"
        rf_rows.append(
            f'<tr data-status="{status}" data-severity="{r.get("severity","")}" data-company="{r.get("company","").lower()}" data-sector="{r.get("sector","")}">'
            f'<td class="rf-co">{r.get("company","")}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            + status_label_cell(status, r.get("severity"))
            + flag_cells
            + f'<td class="rf-summary" style="color:{count_color}"><strong>{flag_count}</strong>'
            + (f'<span class="rf-watch-suffix">+{watch_count}~</span>' if watch_count > 0 else '')
            + '</td></tr>'
        )
    return rf_rows


# ----------------------------------------------------------------------
# Historical snapshots - FIXED to walk full tag chain for each metric.
# Old version only looked at one resolved tag per metric in _history.
# New version: if first key has no data for the target year, try all
# alternative keys that might have been used historically.
# ----------------------------------------------------------------------
def _to_float_safe(v):
    if v is None: return None
    try:
        s = str(v).strip().replace(',', '').replace('$', '').replace('%', '').replace('+', '')
        if not s or s.lower() in ('n/a', 'na', 'none'): return None
        return float(s)
    except (ValueError, TypeError):
        return None


def _detect_fiscal_year_ends(sec_for_co, max_count=3):
    """
    Find the last N fiscal year-end dates. Defensive strategy:

    Approach 1 (primary): Walk balance history and flow history, accept any
    entries explicitly tagged as 10-K/10-K-A/20-F filings.

    Approach 2 (fallback): If no 10-K-tagged entries found, derive year-ends
    from the latest period_end of any flow series. Walks back 12 months at a
    time from the latest observation. This works for filers where SEC XBRL
    doesn't consistently tag the form field, including hyperscalers like
    Microsoft and Google.
    """
    bh = sec_for_co.get("_balance_history", {}) or {}
    h = sec_for_co.get("_history", {}) or {}
    ha = sec_for_co.get("_history_annual", {}) or {}
    candidates = []

    # Approach 1: explicitly tagged 10-K entries from any source
    for source in ("lt_debt", "cash", "st_debt"):
        for entry in bh.get(source, []) or []:
            form = (entry.get("form") or "").upper()
            if form in ("10-K", "10-K/A", "20-F"):
                pd = entry.get("period_end")
                if pd:
                    candidates.append(pd)
    for source in ("revenue", "op_income", "capex"):
        for entry in h.get(source, []) or []:
            form = (entry.get("form") or "").upper()
            if form in ("10-K", "10-K/A", "20-F"):
                pd = entry.get("period_end")
                if pd:
                    candidates.append(pd)
    # Annual history is by definition from 10-K filings: take all period_ends
    for source in ("revenue", "op_income", "capex", "ocf"):
        for entry in ha.get(source, []) or []:
            pd = entry.get("period_end")
            if pd:
                candidates.append(pd)

    if candidates:
        return sorted(set(candidates), reverse=True)[:max_count]

    # Approach 2: derive year-ends from the latest period_end of any flow series.
    # Walk back 12 months at a time. This catches hyperscalers and other filers
    # where the form field isn't reliably 10-K-tagged in XBRL company facts.
    latest_dates = []
    for source in ("revenue", "op_income", "capex", "ocf"):
        flow_hist = h.get(source, []) or []
        if flow_hist:
            try:
                latest = flow_hist[0].get("period_end")
                if latest:
                    latest_dates.append(datetime.strptime(latest, "%Y-%m-%d").date())
            except (ValueError, TypeError):
                continue
    for source in ("lt_debt", "cash", "st_debt"):
        bal_hist = bh.get(source, []) or []
        if bal_hist:
            try:
                latest = bal_hist[0].get("period_end")
                if latest:
                    latest_dates.append(datetime.strptime(latest, "%Y-%m-%d").date())
            except (ValueError, TypeError):
                continue

    if not latest_dates:
        return []

    # The latest available period_end is approximately at-or-just-after a fiscal year-end.
    # For calendar-year filers it's e.g. Q1 2026 (March end) or Q4 2025 (Dec end).
    # The fiscal year-end is roughly the prior occurrence of the same fiscal-period-end
    # month from a year prior. For most US filers: latest_date.replace(year=latest_date.year-1)
    # works as a candidate, then step back 12 months from there.
    latest = max(latest_dates)

    # Heuristic: align to a likely fiscal year-end. If latest is between Sep 30 and Mar 31,
    # the fiscal year-end likely matches the calendar year-end (Dec 31 for calendar filers).
    # Otherwise use latest_date's month as the year-end month (handles MSFT June, Oracle May).
    derived = []
    # The latest quarterly period_end IS one of the fiscal quarter ends. Step back to find
    # the most recent fiscal year-end at-or-before latest_date.
    # We assume year-end is the month preceding the latest_date when latest_date is the
    # first quarter (e.g., latest is March -> year-end is March of prior year for FY ending March;
    # or December prior for calendar fiscal year). Simpler: try both same-month-prior-year
    # and December-prior-year as candidates.

    # Candidate 1: same month, prior year (handles non-calendar fiscal years)
    try:
        c1 = latest.replace(year=latest.year - 1)
        derived.append(c1)
    except ValueError:
        pass

    # Generate prior year-ends by stepping back 12 months from c1
    if derived:
        for i in range(1, max_count + 1):
            try:
                prev = derived[-1].replace(year=derived[-1].year - 1)
                derived.append(prev)
            except ValueError:
                break

    return [d.strftime("%Y-%m-%d") for d in derived[:max_count]]


def _annual_sum_around(history, year_end_date, window_days=400):
    """
    Sum 4 quarters ending at or before year_end_date within window_days.
    Returns dollar sum or None.
    """
    if not history: return None
    try:
        target = datetime.strptime(year_end_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    window_start = target - timedelta(days=window_days)
    matching = []
    for q in history:
        pd_str = q.get("period_end")
        if not pd_str: continue
        try:
            pd = datetime.strptime(pd_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if window_start <= pd <= target and q.get("value") is not None:
            matching.append((pd, q.get("value")))
    if len(matching) < 4: return None
    matching.sort(key=lambda x: x[0], reverse=True)
    # Pick 4 non-overlapping
    return sum(v for _, v in matching[:4])


def _balance_at(history, year_end_date, tolerance_days=60):
    """Get balance sheet value at or closest before year_end_date within tolerance."""
    if not history: return None
    try:
        target = datetime.strptime(year_end_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    best = None
    best_gap = None
    for q in history:
        pd_str = q.get("period_end")
        if not pd_str: continue
        try:
            pd = datetime.strptime(pd_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if pd > target: continue
        gap = (target - pd).days
        if gap > tolerance_days: continue
        if best is None or gap < best_gap:
            best = q.get("value")
            best_gap = gap
        if gap == 0: break
    return best


def _annual_value_or_sum(history_annual, history_quarterly, year_end_date):
    """
    Get year-end value: prefer direct annual record (from 10-K), fall back to 4-quarter sum.

    Companies like telecoms and utilities often report D&A, CapEx, and CFO only annually.
    Without checking annual history first, we'd return None for those names' historical years.
    """
    # First try: exact annual record matching the year-end
    if history_annual:
        try:
            target = datetime.strptime(year_end_date, "%Y-%m-%d").date()
            for rec in history_annual:
                pd_str = rec.get("period_end")
                if not pd_str: continue
                try:
                    pd = datetime.strptime(pd_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                # Match within 5 days of year-end (handles fiscal year reporting variations)
                if abs((pd - target).days) <= 5 and rec.get("value") is not None:
                    return rec.get("value")
        except (ValueError, TypeError):
            pass
    # Fallback: sum 4 quarterly records around year-end
    return _annual_sum_around(history_quarterly, year_end_date)


def historical_snapshots(sec_for_co):
    """
    Build year-by-year snapshots: Year-3, Year-2, Year-1, LTM.
    Uses _history (quarterly flow), _history_annual (annual flow), and _balance_history (instant).
    """
    if not sec_for_co: return []
    year_ends = _detect_fiscal_year_ends(sec_for_co, max_count=3)
    history = sec_for_co.get("_history", {}) or {}
    history_annual = sec_for_co.get("_history_annual", {}) or {}
    balance = sec_for_co.get("_balance_history", {}) or {}
    snapshots = []
    for ye in reversed(year_ends):
        rev = _annual_value_or_sum(history_annual.get("revenue"), history.get("revenue"), ye)
        opi = _annual_value_or_sum(history_annual.get("op_income"), history.get("op_income"), ye)
        da = _annual_value_or_sum(history_annual.get("da"), history.get("da"), ye)
        ocf = _annual_value_or_sum(history_annual.get("ocf"), history.get("ocf"), ye)
        capex = _annual_value_or_sum(history_annual.get("capex"), history.get("capex"), ye)
        cash = _balance_at(balance.get("cash"), ye)
        lt = _balance_at(balance.get("lt_debt"), ye)
        st = _balance_at(balance.get("st_debt"), ye)
        ebitda = (opi + da) if (opi is not None and da is not None) else None
        ebitda_margin = (ebitda / rev * 100) if (ebitda is not None and rev and rev > 0) else None
        op_margin = (opi / rev * 100) if (opi is not None and rev and rev > 0) else None
        fcf = (ocf - abs(capex)) if (ocf is not None and capex is not None) else None
        total_debt = None
        if lt is not None or st is not None:
            total_debt = (lt or 0) + (st or 0)
        net_debt = (total_debt - cash) if (total_debt is not None and cash is not None) else None
        net_leverage = (net_debt / ebitda) if (net_debt is not None and ebitda and ebitda > 0) else None
        try:
            dt = datetime.strptime(ye, "%Y-%m-%d").date()
            label = f"FY {dt.year}"
        except (ValueError, TypeError):
            label = ye
        snapshots.append({
            "period_end": ye, "period_label": label,
            "revenue": rev / 1e9 if rev is not None else None,
            "op_income": opi / 1e9 if opi is not None else None,
            "da": da / 1e9 if da is not None else None,
            "ocf": ocf / 1e9 if ocf is not None else None,
            "capex": -abs(capex) / 1e9 if capex is not None else None,
            "ebitda": ebitda / 1e9 if ebitda is not None else None,
            "ebitda_margin": ebitda_margin, "op_margin": op_margin,
            "fcf": fcf / 1e9 if fcf is not None else None,
            "cash": cash / 1e9 if cash is not None else None,
            "lt_debt": lt / 1e9 if lt is not None else None,
            "st_debt": st / 1e9 if st is not None else None,
            "total_debt": total_debt / 1e9 if total_debt is not None else None,
            "net_debt": net_debt / 1e9 if net_debt is not None else None,
            "net_leverage": net_leverage,
        })
    ltm_period = sec_for_co.get("_period_end", "")
    ltm_label = "LTM"
    if ltm_period:
        try:
            dt = datetime.strptime(ltm_period, "%Y-%m-%d").date()
            ltm_label = f"LTM {dt.strftime('%b %Y')}"
        except (ValueError, TypeError):
            pass
    snapshots.append({
        "period_end": ltm_period, "period_label": ltm_label,
        "revenue": _to_float_safe(sec_for_co.get("revenue_ltm")),
        "op_income": _to_float_safe(sec_for_co.get("op_income_ltm")),
        "da": _to_float_safe(sec_for_co.get("da_ltm")),
        "ocf": _to_float_safe(sec_for_co.get("ocf_ltm")),
        "capex": (-abs(_to_float_safe(sec_for_co.get("capex_ltm"))) if _to_float_safe(sec_for_co.get("capex_ltm")) is not None else None),
        "ebitda": _to_float_safe(sec_for_co.get("ebitda_ltm")),
        "ebitda_margin": _to_float_safe(sec_for_co.get("ebitda_margin")),
        "op_margin": _to_float_safe(sec_for_co.get("op_margin")),
        "fcf": _to_float_safe(sec_for_co.get("fcf_ltm")),
        "cash": _to_float_safe(sec_for_co.get("cash")),
        "lt_debt": _to_float_safe(sec_for_co.get("lt_debt")),
        "st_debt": _to_float_safe(sec_for_co.get("st_debt")),
        "total_debt": _to_float_safe(sec_for_co.get("total_debt")),
        "net_debt": _to_float_safe(sec_for_co.get("net_debt")),
        "net_leverage": _to_float_safe(sec_for_co.get("nd_ebitda")),
    })
    return snapshots


def _fmt_cur(v):
    if v is None: return "n/a"
    if v < 0: return f"-${abs(v):,.1f}"
    return f"${v:,.1f}"


def _fmt_cur_bold(v):
    """Currency formatter for emphasized rows like EBITDA and FCF (the bottom-line totals)."""
    if v is None: return "n/a"
    if v < 0: return f'<strong>-${abs(v):,.1f}</strong>'
    return f'<strong>${v:,.1f}</strong>'


def _fmt_pct(v):
    if v is None: return "n/a"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _fmt_lev(v):
    if v is None: return "n/a"
    return f"{v:.1f}x"


def _trend_arrow(values, lower_is_better=False):
    clean = [v for v in values if v is not None]
    if len(clean) < 2: return "", ""
    first = clean[0]
    last = clean[-1]
    if first == 0: return "", ""
    delta = last - first
    if abs(delta) < abs(first) * 0.02:
        return "&#8594;", "stock-flat"
    if delta > 0:
        return ("&#8593;", "stock-down" if lower_is_better else "stock-up")
    return ("&#8595;", "stock-up" if lower_is_better else "stock-down")


def fin_detail_html(co_name, sec_for_co):
    if not sec_for_co:
        return '<div class="fin-detail-empty">No SEC EDGAR data available. Foreign filers (20-F) and non-SEC filers cannot show historical detail.</div>'
    snapshots = historical_snapshots(sec_for_co)
    if not snapshots or len(snapshots) < 2:
        return '<div class="fin-detail-empty">Insufficient historical data to build trend (need at least 1 full prior fiscal year plus LTM).</div>'
    period_headers = "".join(f'<th>{s["period_label"]}</th>' for s in snapshots)
    income_metrics = [
        ("Revenue", "revenue", _fmt_cur, False),
        ("Operating Income", "op_income", _fmt_cur, False),
        ("D&A (from CFS)", "da", _fmt_cur, False),
        ("EBITDA", "ebitda", _fmt_cur_bold, False),
        ("EBITDA Margin", "ebitda_margin", _fmt_pct, False),
        ("Cash from Operations", "ocf", _fmt_cur, False),
        ("CapEx", "capex", _fmt_cur, False),
        ("Free Cash Flow", "fcf", _fmt_cur_bold, False),
    ]
    balance_metrics = [
        ("Cash", "cash", _fmt_cur, False),
        ("Long-Term Debt", "lt_debt", _fmt_cur, True),
        ("Short-Term Debt", "st_debt", _fmt_cur, True),
        ("Total Debt", "total_debt", _fmt_cur, True),
        ("Net Debt", "net_debt", _fmt_cur, True),
        ("Net Leverage (ND/EBITDA)", "net_leverage", _fmt_lev, True),
    ]
    def build_metric_rows(metrics):
        rows = []
        for label, key, fmt, lower_better in metrics:
            values = [s.get(key) for s in snapshots]
            cells = "".join(f'<td class="fd-val">{fmt(v)}</td>' for v in values)
            non_null = [v for v in values if v is not None]
            if len(non_null) >= 2 and key in ("ebitda_margin", "op_margin"):
                bps = (non_null[-1] - non_null[-2]) * 100
                bps_sign = "+" if bps >= 0 else ""
                bps_cls = "stock-up" if bps > 0 else ("stock-down" if bps < 0 else "stock-flat")
                yoy_str = f'<span class="{bps_cls}">{bps_sign}{bps:.0f}bps</span>'
            elif len(non_null) >= 2 and key == "net_leverage":
                delta = non_null[-1] - non_null[-2]
                delta_sign = "+" if delta >= 0 else ""
                delta_cls = "stock-down" if delta > 0 else ("stock-up" if delta < 0 else "stock-flat")
                yoy_str = f'<span class="{delta_cls}">{delta_sign}{delta:.1f}x</span>'
            elif len(non_null) >= 2 and non_null[-2] != 0:
                yoy_pct = (non_null[-1] - non_null[-2]) / abs(non_null[-2]) * 100
                yoy_sign = "+" if yoy_pct >= 0 else ""
                if lower_better:
                    yoy_cls = "stock-down" if yoy_pct > 5 else ("stock-up" if yoy_pct < -5 else "stock-flat")
                else:
                    yoy_cls = "stock-up" if yoy_pct >= 0 else "stock-down"
                yoy_str = f'<span class="{yoy_cls}">{yoy_sign}{yoy_pct:.1f}%</span>'
            else:
                yoy_str = '<span class="stock-flat">n/a</span>'
            arrow, arrow_cls = _trend_arrow(values, lower_is_better=lower_better)
            trend_html = f'<span class="fd-arrow {arrow_cls}">{arrow}</span>' if arrow else ''
            rows.append(
                f'<tr><td class="fd-metric-label">{label}</td>{cells}'
                f'<td class="fd-yoy">{yoy_str}</td><td class="fd-trend">{trend_html}</td></tr>'
            )
        return "".join(rows)
    income_rows = build_metric_rows(income_metrics)
    balance_rows = build_metric_rows(balance_metrics)
    period_end = sec_for_co.get("_period_end", "")
    filing_form = sec_for_co.get("_filing_form", "")
    source_label = f"SEC EDGAR {filing_form}" if filing_form else "SEC EDGAR"
    if period_end:
        source_label += f" as of {period_end}"
    return (
        f'<div class="fin-detail-content">'
        f'<div class="fin-detail-header">'
        f'<span class="fin-detail-title">Historical Snapshot &mdash; {co_name}</span>'
        f'<span class="fin-detail-source">Source: {source_label}</span></div>'
        f'<div class="fin-detail-section">'
        f'<div class="fin-detail-subtitle">Income Statement &amp; Cash Flow</div>'
        f'<table class="fin-detail-table">'
        f'<thead><tr><th class="fd-metric-col">Metric</th>{period_headers}<th>YoY</th><th>Trend</th></tr></thead>'
        f'<tbody>{income_rows}</tbody></table></div>'
        f'<div class="fin-detail-section">'
        f'<div class="fin-detail-subtitle">Capital Structure</div>'
        f'<table class="fin-detail-table">'
        f'<thead><tr><th class="fd-metric-col">Metric</th>{period_headers}<th>YoY</th><th>Trend</th></tr></thead>'
        f'<tbody>{balance_rows}</tbody></table></div>'
        f'<div class="fin-detail-footer">All figures in $Bn unless noted. Historical periods reconstructed from quarterly SEC EDGAR XBRL data. YoY compares LTM to prior fiscal year. Margin YoY in basis points; leverage YoY in turns.</div>'
        f'</div>'
    )


# ----------------------------------------------------------------------
# Hyperscaler CapEx historical bar chart - 4 names stacked, 4 years + LTM
# ----------------------------------------------------------------------
def _round_to_calendar_quarter(period_end_str):
    """
    Round a period_end date to the nearest calendar quarter end (Mar 31, Jun 30,
    Sep 30, Dec 31). Used to align hyperscalers with different fiscal calendars
    (e.g. Oracle's May FY, MSFT's June FY) onto a single chart axis.
    """
    try:
        dt = datetime.strptime(period_end_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return period_end_str
    # Calendar quarter ends
    from datetime import date as _date
    quarter_ends = [
        _date(dt.year, 3, 31),
        _date(dt.year, 6, 30),
        _date(dt.year, 9, 30),
        _date(dt.year, 12, 31),
    ]
    # Also include adjacent year ends for boundary cases
    quarter_ends.insert(0, _date(dt.year - 1, 12, 31))
    quarter_ends.append(_date(dt.year + 1, 3, 31))
    closest = min(quarter_ends, key=lambda qe: abs((dt - qe).days))
    return closest.strftime("%Y-%m-%d")


def _hyperscaler_capex_history(sec_data):
    """
    Build quarterly CapEx history for MSFT, GOOGL, AMZN, ORCL.

    Quarterly view: each bar is one calendar quarter, with the 4 hyperscalers
    stacked. Each company's capex for that quarter is added to the stack based
    on its reported period_end. Different fiscal calendars are fine - we synchronize
    on the calendar period_end date, not on fiscal year.

    Returns (rows, contributors) where rows is a list of period dicts oldest
    first. Each row has period_label (e.g. "Q1 25"), period_end (raw date),
    one entry per company (Microsoft, Alphabet, Amazon, Oracle) and a total.
    """
    hyperscalers = ["Microsoft", "Alphabet", "Amazon", "Oracle"]
    if not sec_data:
        return [], []

    # Collect quarterly capex by calendar-quarter-end across all 4 names.
    # Companies with non-calendar fiscal years (Oracle: Feb/May/Aug/Nov; MSFT
    # historical periods: also non-calendar) get rounded to the nearest
    # calendar quarter end so they stack cleanly on the chart.
    capex_by_period_co = {}  # (rounded_period_end, co) -> value in dollars
    all_periods = set()
    contributors_present = []
    for co in hyperscalers:
        sec = (sec_data or {}).get(co, {})
        if not sec:
            continue
        capex_hist = (sec.get("_history", {}) or {}).get("capex", []) or []
        if not capex_hist:
            continue
        company_has_data = False
        for entry in capex_hist:
            pd = entry.get("period_end")
            val = entry.get("value")
            if pd and val is not None:
                # Round to calendar quarter for cross-company alignment
                pd_aligned = _round_to_calendar_quarter(pd)
                capex_by_period_co[(pd_aligned, co)] = abs(val)
                all_periods.add(pd_aligned)
                company_has_data = True
        if company_has_data and co not in contributors_present:
            contributors_present.append(co)

    if not all_periods:
        return [], []

    # Keep the most recent 16 quarters across all names
    sorted_periods = sorted(all_periods, reverse=True)[:16]
    sorted_periods.reverse()  # oldest first for chart

    rows = []
    for period in sorted_periods:
        try:
            dt = datetime.strptime(period, "%Y-%m-%d").date()
            q = (dt.month - 1) // 3 + 1
            label = f"Q{q} '{str(dt.year)[2:]}"
        except (ValueError, TypeError):
            label = period
        row = {"period_label": label, "period_end": period}
        period_total = 0.0
        period_has_data = False
        for co in hyperscalers:
            val = capex_by_period_co.get((period, co))
            if val is not None:
                val_bn = val / 1e9
                row[co] = round(val_bn, 1)
                period_total += val_bn
                period_has_data = True
            else:
                row[co] = None
        row["total"] = round(period_total, 1) if period_has_data else None
        rows.append(row)

    return rows, contributors_present


def _build_hyperscaler_chart_html(sec_data, chart_id="hyperCapexChart"):
    """Build the Hyperscaler CapEx historical bar chart section (uses Chart.js)."""
    history, contributors = _hyperscaler_capex_history(sec_data)
    if not history or not contributors:
        return ""

    # Color map: professional credit-research palette with distinct hues per name.
    # MSFT navy, GOOGL green, AMZN orange, ORCL purple.
    color_map = {
        "Microsoft": "#2C5282",   # deep navy - MSFT
        "Alphabet": "#38A169",    # forest green - GOOGL
        "Amazon": "#DD6B20",      # burnt orange - AMZN
        "Oracle": "#805AD5",      # purple - ORCL
    }
    short_label = {"Microsoft": "MSFT", "Alphabet": "GOOGL", "Amazon": "AMZN", "Oracle": "ORCL"}

    labels_json = json.dumps([r["period_label"] for r in history])
    datasets = []
    for co in contributors:
        data_list = [r.get(co) if r.get(co) is not None else None for r in history]
        datasets.append({
            "label": short_label.get(co, co),
            "data": data_list,
            "backgroundColor": color_map.get(co, "#7090a8"),
            "borderColor": color_map.get(co, "#7090a8"),
            "borderWidth": 0,
            "stack": "capex",
        })
    datasets_json = json.dumps(datasets)
    totals_json = json.dumps([r.get("total") for r in history])

    # Most recent quarter total + YoY (4 quarters back = same quarter prior year)
    latest = history[-1] if history else None
    prior_year = history[-5] if len(history) >= 5 else None
    callout_total = latest.get("total") if latest else 0
    callout_yoy_html = ""
    if latest and prior_year and prior_year.get("total") and prior_year["total"] > 0:
        yoy = (latest["total"] - prior_year["total"]) / prior_year["total"] * 100
        sign = "+" if yoy >= 0 else ""
        cls = "stock-up" if yoy >= 0 else "stock-down"
        callout_yoy_html = f'<span class="{cls}">{sign}{yoy:.1f}% YoY</span>'

    return f"""
    <div class="hyper-chart-section">
      <div class="hyper-chart-header">
        <div>
          <h3 class="tmt-section-title">Hyperscaler CapEx (Stacked, Quarterly)</h3>
          <div class="tmt-section-subtitle">Quarterly CapEx for MSFT + GOOGL + AMZN + ORCL, last 16 quarters. Bars synchronize on calendar quarter end; companies with non-calendar fiscal years contribute at their actual reported period.</div>
        </div>
        <div class="hyper-chart-callout">
          <div class="hyper-chart-callout-label">Latest quarter total</div>
          <div class="hyper-chart-callout-value">${callout_total:,.1f}Bn</div>
          {callout_yoy_html}
        </div>
      </div>
      <div class="hyper-chart-wrap">
        <canvas id="{chart_id}"></canvas>
      </div>
    </div>
    <script>
      (function(){{
        if (typeof Chart === 'undefined') {{ return; }}
        var labels = {labels_json};
        var datasets = {datasets_json};
        var totals = {totals_json};
        var ctx = document.getElementById('{chart_id}');
        if (!ctx) return;

        // Custom plugin: draw column totals above each stacked bar
        var totalLabelsPlugin = {{
          id: 'totalLabels_{chart_id}',
          afterDatasetsDraw: function(chart) {{
            var ctxCanvas = chart.ctx;
            ctxCanvas.save();
            ctxCanvas.font = '600 11px monospace';
            ctxCanvas.fillStyle = '#cdd5df';
            ctxCanvas.textAlign = 'center';
            ctxCanvas.textBaseline = 'bottom';
            var meta = chart.getDatasetMeta(chart.data.datasets.length - 1);
            for (var i = 0; i < meta.data.length; i++) {{
              var bar = meta.data[i];
              var total = totals[i];
              if (total == null || bar == null) continue;
              var label = '$' + Math.round(total) + 'B';
              ctxCanvas.fillText(label, bar.x, bar.y - 4);
            }}
            ctxCanvas.restore();
          }}
        }};

        new Chart(ctx, {{
          type: 'bar',
          data: {{ labels: labels, datasets: datasets }},
          options: {{
            responsive: true, maintainAspectRatio: false,
            layout: {{ padding: {{ top: 24 }} }},
            plugins: {{
              legend: {{ position: 'top', labels: {{ color: '#a0b4c8', font: {{ size: 11 }} }} }},
              tooltip: {{ callbacks: {{ label: function(ctx) {{ return ctx.dataset.label + ': $' + (ctx.parsed.y||0).toFixed(1) + 'Bn'; }} }} }}
            }},
            scales: {{
              x: {{ stacked: true, ticks: {{ color: '#7090a8' }}, grid: {{ color: '#1e2a3a' }} }},
              y: {{ stacked: true, ticks: {{ color: '#7090a8', callback: function(v) {{ return '$' + v + 'B'; }} }}, grid: {{ color: '#1e2a3a' }} }}
            }}
          }},
          plugins: [totalLabelsPlugin]
        }});
      }})();
    </script>
    """


# ----------------------------------------------------------------------
# Hyperscaler Revenue Backlog (RPO) chart - forward demand signal
# Source: SEC EDGAR XBRL RevenueRemainingPerformanceObligation tag
# Names included: only those in watchlist with material RPO disclosure.
# ----------------------------------------------------------------------
def _hyperscaler_rpo_history(sec_data):
    """
    Build quarterly RPO history for hyperscalers in the watchlist.
    Returns list of dicts: [{period_label, Microsoft, Alphabet, Amazon, Oracle, total}, ...]
    Oldest first, last is the latest reported quarter.
    Names without RPO data are simply absent from contributors_present.
    """
    hyperscalers = ["Microsoft", "Alphabet", "Amazon", "Oracle"]
    if not sec_data:
        return [], []

    # Find the set of distinct period_end dates across the 4 names, rounded to
    # calendar quarter end to align companies with non-calendar fiscal years.
    all_periods = set()
    rpo_by_company = {}
    for co in hyperscalers:
        sec = (sec_data or {}).get(co, {})
        if not sec:
            continue
        rpo_hist = (sec.get("_balance_history", {}) or {}).get("revenue_backlog", []) or []
        if not rpo_hist:
            continue
        # rpo_hist is newest first; build period->value map with rounded keys
        company_map = {}
        for entry in rpo_hist:
            pd = entry.get("period_end")
            val = entry.get("value")
            if pd and val is not None:
                pd_aligned = _round_to_calendar_quarter(pd)
                company_map[pd_aligned] = val
                all_periods.add(pd_aligned)
        if company_map:
            rpo_by_company[co] = company_map

    if not rpo_by_company:
        return [], []

    # Keep the most recent 8 quarters across all names
    sorted_periods = sorted(all_periods, reverse=True)[:8]
    sorted_periods.reverse()  # oldest first for chart

    rows = []
    contributors_present = []
    for period in sorted_periods:
        # Convert YYYY-MM-DD to e.g. "Q1 26" for readability
        try:
            dt = datetime.strptime(period, "%Y-%m-%d").date()
            q = (dt.month - 1) // 3 + 1
            label = f"Q{q} '{str(dt.year)[2:]}"
        except (ValueError, TypeError):
            label = period
        row = {"period_label": label, "period_end": period}
        period_total = 0.0
        period_has_data = False
        for co in hyperscalers:
            company_map = rpo_by_company.get(co, {})
            val = company_map.get(period)
            if val is not None:
                val_bn = val / 1e9
                row[co] = round(val_bn, 1)
                period_total += val_bn
                period_has_data = True
                if co not in contributors_present:
                    contributors_present.append(co)
            else:
                row[co] = None
        row["total"] = round(period_total, 1) if period_has_data else None
        if period_has_data:
            rows.append(row)

    return rows, contributors_present


def _build_rpo_chart_html(sec_data, chart_id="rpoChart"):
    """Hyperscaler RPO chart - TEMPORARILY STUBBED.

    Reason: SEC XBRL stores RPO with multiple time-horizon dimensions (within 12mo,
    beyond 12mo, total). Current extraction doesn't filter by XBRL dimension axis,
    leading to inflated totals when multiple records per period_end are summed.
    Microsoft's true RPO is ~$300-380B vs displayed $1,653B (Q1 2026).

    Honest disclosure to colleagues: data quality is being investigated rather
    than show incorrect values that would undermine dashboard credibility.

    Re-enable once XBRL dimension parsing is implemented (next session).
    """
    return f"""
    <div style="background:#0d1117;border:1px solid #1e2a3a;border-radius:6px;padding:24px;margin:14px 28px;">
      <div style="color:#e89c00;font-size:12px;letter-spacing:1.5px;font-weight:600;margin-bottom:8px;">HYPERSCALER REVENUE BACKLOG (RPO) — DATA QUALITY INVESTIGATION IN PROGRESS</div>
      <div style="color:#7090a8;font-size:11px;line-height:1.6;">
        The RPO chart is temporarily stubbed pending resolution of an XBRL aggregation issue.
        Multiple time-horizon records per company per period are being summed instead of taking the reported total.
        Estimated true RPO across MSFT + GOOGL + ORCL is approximately $600-700Bn; previous chart displayed materially higher values due to this issue.
        Chart will return once SEC XBRL dimension filtering is implemented.
      </div>
    </div>
    """


def _build_rpo_chart_html_DISABLED(sec_data, chart_id="rpoChart"):
    """Disabled until XBRL dimension parsing is added."""
    history, contributors = _hyperscaler_rpo_history(sec_data)
    if not history or not contributors:
        return ""

    color_map = {
        "Microsoft": "#2C5282",   # deep navy - MSFT
        "Alphabet": "#38A169",    # forest green - GOOGL
        "Amazon": "#DD6B20",      # burnt orange - AMZN
        "Oracle": "#805AD5",      # purple - ORCL
    }
    short_label = {"Microsoft": "MSFT", "Alphabet": "GOOGL", "Amazon": "AMZN", "Oracle": "ORCL"}

    labels_json = json.dumps([r["period_label"] for r in history])
    datasets = []
    for co in contributors:
        data_list = [r.get(co) if r.get(co) is not None else None for r in history]
        datasets.append({
            "label": short_label.get(co, co),
            "data": data_list,
            "backgroundColor": color_map.get(co, "#7090a8"),
            "borderColor": color_map.get(co, "#7090a8"),
            "borderWidth": 0,
            "stack": "rpo",
        })
    datasets_json = json.dumps(datasets)
    totals_json = json.dumps([r.get("total") for r in history])

    # Latest period total + YoY (5 quarters back) callout
    latest = history[-1] if history else None
    prior_year = history[-5] if len(history) >= 5 else None
    callout_total = latest.get("total") if latest else 0
    callout_yoy_html = ""
    if latest and prior_year and prior_year.get("total") and prior_year["total"] > 0:
        yoy = (latest["total"] - prior_year["total"]) / prior_year["total"] * 100
        sign = "+" if yoy >= 0 else ""
        cls = "stock-up" if yoy >= 0 else "stock-down"
        callout_yoy_html = f'<span class="{cls}">{sign}{yoy:.0f}% YoY</span>'

    # Build contributors list for subtitle (so users see which names are included)
    contributors_str = ", ".join(short_label.get(c, c) for c in contributors)
    excluded = [c for c in ("Microsoft", "Alphabet", "Amazon", "Oracle") if c not in contributors]
    excluded_note = ""
    if excluded:
        excluded_labels = ", ".join(short_label.get(c, c) for c in excluded)
        excluded_note = f' (not disclosed: {excluded_labels})'

    return f"""
    <div class="hyper-chart-section">
      <div class="hyper-chart-header">
        <div>
          <h3 class="tmt-section-title">Hyperscaler Revenue Backlog (RPO, Stacked)</h3>
          <div class="tmt-section-subtitle">Remaining Performance Obligation (RPO), last 8 quarters. Forward demand signal: contracted-but-not-yet-recognized cloud revenue. Includes {contributors_str}{excluded_note}. Amazon excluded when applicable because AWS RPO is not separately tagged in SEC XBRL; total Amazon ContractWithCustomerLiability would include Prime memberships and gift card balances, materially overstating AWS commercial backlog.</div>
        </div>
        <div class="hyper-chart-callout">
          <div class="hyper-chart-callout-label">Latest quarter total</div>
          <div class="hyper-chart-callout-value">${callout_total:,.0f}Bn</div>
          {callout_yoy_html}
        </div>
      </div>
      <div class="hyper-chart-wrap">
        <canvas id="{chart_id}"></canvas>
      </div>
    </div>
    <script>
      (function(){{
        if (typeof Chart === 'undefined') {{ return; }}
        var labels = {labels_json};
        var datasets = {datasets_json};
        var totals = {totals_json};
        var ctx = document.getElementById('{chart_id}');
        if (!ctx) return;

        // Custom plugin: draw column totals above each stacked bar
        var totalLabelsPlugin = {{
          id: 'totalLabels_{chart_id}',
          afterDatasetsDraw: function(chart) {{
            var ctxCanvas = chart.ctx;
            ctxCanvas.save();
            ctxCanvas.font = '600 11px monospace';
            ctxCanvas.fillStyle = '#cdd5df';
            ctxCanvas.textAlign = 'center';
            ctxCanvas.textBaseline = 'bottom';
            var meta = chart.getDatasetMeta(chart.data.datasets.length - 1);
            for (var i = 0; i < meta.data.length; i++) {{
              var bar = meta.data[i];
              var total = totals[i];
              if (total == null || bar == null) continue;
              var label = '$' + Math.round(total) + 'B';
              ctxCanvas.fillText(label, bar.x, bar.y - 4);
            }}
            ctxCanvas.restore();
          }}
        }};

        new Chart(ctx, {{
          type: 'bar',
          data: {{ labels: labels, datasets: datasets }},
          options: {{
            responsive: true, maintainAspectRatio: false,
            layout: {{ padding: {{ top: 24 }} }},
            plugins: {{
              legend: {{ position: 'top', labels: {{ color: '#a0b4c8', font: {{ size: 11 }} }} }},
              tooltip: {{ callbacks: {{ label: function(ctx) {{ return ctx.dataset.label + ': $' + (ctx.parsed.y||0).toFixed(1) + 'Bn'; }} }} }}
            }},
            scales: {{
              x: {{ stacked: true, ticks: {{ color: '#7090a8' }}, grid: {{ color: '#1e2a3a' }} }},
              y: {{ stacked: true, ticks: {{ color: '#7090a8', callback: function(v) {{ return '$' + v + 'B'; }} }}, grid: {{ color: '#1e2a3a' }} }}
            }}
          }},
          plugins: [totalLabelsPlugin]
        }});
      }})();
    </script>
    """


# ----------------------------------------------------------------------
# US Data Center Construction chart (Census Bureau via census_construction module)
# ----------------------------------------------------------------------
def _build_data_center_construction_html(census_data, chart_id_lvl="dcConstructionLevel", chart_id_mom="dcConstructionMom"):
    """Build the dual-chart section showing monthly level + MoM change."""
    if not census_data or not census_data.get("series"):
        return f"""
        <div class="dc-construction-section">
          <h3 class="tmt-section-title">US Data Center Construction</h3>
          <div class="dc-construction-empty">Census Bureau data not yet available. The module attempts to discover the correct category_code on first run; check the workflow log for the value Census returned and we can hard-code it next iteration.</div>
        </div>
        """

    series = census_data["series"]
    # Render last 5 years (60 months) to match the reference screenshots
    series_view = series[-60:] if len(series) > 60 else series
    labels = [s["period"] for s in series_view]
    values = [s["value"] for s in series_view]

    # MoM deltas across the same window
    mom_labels = labels[1:]
    mom_values = [values[i] - values[i - 1] for i in range(1, len(values))]
    mom_colors = ["#4ec38a" if v >= 0 else "#ff6b6b" for v in mom_values]

    latest = census_data.get("latest", {})
    yoy_pct = census_data.get("yoy_pct")
    three_m = census_data.get("three_month_avg_mom")
    five_y = census_data.get("five_year_growth_pct")

    def kpi(label, value, color="#a0c4e8"):
        return (
            f'<div class="dc-kpi">'
            f'<div class="dc-kpi-label">{label}</div>'
            f'<div class="dc-kpi-value" style="color:{color}">{value}</div>'
            f'</div>'
        )

    latest_str = f"${latest.get('value', 0):,.0f}M" if latest else "n/a"
    latest_period = latest.get("period", "") if latest else ""
    yoy_str = f"+{yoy_pct:.1f}%" if (yoy_pct is not None and yoy_pct >= 0) else (f"{yoy_pct:.1f}%" if yoy_pct is not None else "n/a")
    yoy_color = "#4ec38a" if (yoy_pct is not None and yoy_pct >= 0) else ("#ff6b6b" if yoy_pct is not None else "#a0c4e8")
    three_m_str = f"{'+' if three_m and three_m >= 0 else ''}${three_m:,.0f}M" if three_m is not None else "n/a"
    three_m_color = "#4ec38a" if (three_m is not None and three_m >= 0) else ("#ff6b6b" if three_m is not None else "#a0c4e8")
    five_y_str = f"+{five_y:.0f}%" if (five_y is not None and five_y >= 0) else (f"{five_y:.0f}%" if five_y is not None else "n/a")

    labels_json = json.dumps(labels)
    values_json = json.dumps(values)
    mom_labels_json = json.dumps(mom_labels)
    mom_values_json = json.dumps(mom_values)
    mom_colors_json = json.dumps(mom_colors)

    return f"""
    <div class="dc-construction-section">
      <div class="dc-construction-header">
        <div>
          <h3 class="tmt-section-title">US Data Center Construction</h3>
          <div class="tmt-section-subtitle">Monthly private construction put-in-place spending, US Census Bureau. Lagged ~6 weeks. Last 5 years shown.</div>
        </div>
        <div class="dc-source">Source: Census Bureau VIP</div>
      </div>
      <div class="dc-kpi-row">
        {kpi(f"Latest ({latest_period})", latest_str)}
        {kpi("YoY change", yoy_str, yoy_color)}
        {kpi("3M avg MoM", three_m_str, three_m_color)}
        {kpi("5Y growth", five_y_str, "#4ec38a")}
      </div>
      <div class="dc-chart-label">Monthly spending level ($M)</div>
      <div class="dc-chart-wrap"><canvas id="{chart_id_lvl}"></canvas></div>
      <div class="dc-chart-label">Month-over-month change ($M)</div>
      <div class="dc-chart-wrap-short"><canvas id="{chart_id_mom}"></canvas></div>
    </div>
    <script>
      (function(){{
        if (typeof Chart === 'undefined') {{ return; }}
        var ctx1 = document.getElementById('{chart_id_lvl}');
        if (ctx1) {{
          new Chart(ctx1, {{
            type: 'line',
            data: {{
              labels: {labels_json},
              datasets: [{{
                label: 'Spend',
                data: {values_json},
                borderColor: '#a0c4e8',
                backgroundColor: 'rgba(160, 196, 232, 0.08)',
                fill: true, tension: 0.25, borderWidth: 2,
                pointRadius: 2, pointHoverRadius: 5
              }}]
            }},
            options: {{
              responsive: true, maintainAspectRatio: false,
              plugins: {{
                legend: {{ display: false }},
                tooltip: {{ callbacks: {{ label: function(c){{ return '$' + c.parsed.y.toLocaleString() + 'M'; }} }} }}
              }},
              scales: {{
                x: {{ ticks: {{ color: '#7090a8', autoSkip: true, maxRotation: 45, font: {{ size: 9 }} }}, grid: {{ color: '#1e2a3a' }} }},
                y: {{ ticks: {{ color: '#7090a8', callback: function(v) {{ return '$' + v.toLocaleString(); }} }}, grid: {{ color: '#1e2a3a' }}, beginAtZero: true }}
              }}
            }}
          }});
        }}
        var ctx2 = document.getElementById('{chart_id_mom}');
        if (ctx2) {{
          new Chart(ctx2, {{
            type: 'bar',
            data: {{
              labels: {mom_labels_json},
              datasets: [{{
                label: 'MoM',
                data: {mom_values_json},
                backgroundColor: {mom_colors_json},
                borderWidth: 0
              }}]
            }},
            options: {{
              responsive: true, maintainAspectRatio: false,
              plugins: {{
                legend: {{ display: false }},
                tooltip: {{ callbacks: {{ label: function(c){{ var v = c.parsed.y; return (v < 0 ? '-$' : '+$') + Math.abs(v).toFixed(0) + 'M'; }} }} }}
              }},
              scales: {{
                x: {{ ticks: {{ color: '#7090a8', autoSkip: true, maxRotation: 45, font: {{ size: 9 }} }}, grid: {{ color: '#1e2a3a' }} }},
                y: {{ ticks: {{ color: '#7090a8', callback: function(v) {{ return (v < 0 ? '-$' : '$') + Math.abs(v); }} }}, grid: {{ color: '#1e2a3a' }} }}
              }}
            }}
          }});
        }}
      }})();
    </script>
    """


# ----------------------------------------------------------------------
# TMT tab company row + subsection builder (unchanged from prior version)
# ----------------------------------------------------------------------
def _tmt_company_row(co_name, all_rows, sec_data):
    row = next((r for r in all_rows if r.get("company") == co_name), None)
    if not row:
        return f'<tr><td class="co-cell">{co_name}</td><td colspan="9" class="tmt-missing">Not in watchlist</td></tr>'
    status = (row.get("status") or "green").lower()
    sector = row.get("sector", "")
    fin_source = row.get('_financials_source', '')
    filing_form = row.get('_filing_form', '')
    period_end = row.get('_period_end', '')
    if fin_source.startswith('SEC'):
        form_label = filing_form if filing_form else ""
        period_label = period_end if period_end else "unknown"
        source_marker = f'<span class="src-tag sec" title="Source: SEC EDGAR {form_label} as of {period_label}">SEC</span>'
    elif fin_source == 'yfinance':
        source_marker = '<span class="src-tag yf" title="Source: yfinance balance sheet (Total Debt fallback for non-SEC filer or unusual tag structure)">YF</span>'
    else:
        source_marker = '<span class="src-tag claude" title="Source: Claude web search">EST</span>'
    return (
        f'<tr data-status="{status}" data-severity="{row.get("severity","")}" data-company="{co_name.lower()}" data-sector="{sector}">'
        f'<td class="co-cell">{co_name} {source_marker}</td>'
        + status_label_cell(status, row.get("severity"))
        + money_cell(row.get('revenue_ltm'))
        + yoy_cell(row.get('revenue_yoy_pct'))
        + leverage_cell(row.get('nd_ebitda'))
        + margin_cell(row.get('ebitda_margin'))
        + margin_cell(row.get('op_margin'))
        + fcf_cell(row.get('fcf_ltm'))
        + money_cell(row.get('cash'))
        + money_cell(row.get('total_debt'))
        + '</tr>'
    )


def build_tmt_tab(all_rows, sec_data, census_data):
    """Build the full TMT tab content with all sections."""
    dc_chart_html = _build_data_center_construction_html(census_data)
    hyper_chart_html = _build_hyperscaler_chart_html(sec_data)
    rpo_chart_html = _build_rpo_chart_html(sec_data)

    sections_html = []
    for sub in TMT_SUBSECTIONS:
        rows_html = "".join(_tmt_company_row(co, all_rows, sec_data) for co in sub["names"])
        sections_html.append(
            f'<div class="tmt-section" data-subsection="{sub["id"]}">'
            f'<div class="tmt-section-header">'
            f'<h3 class="tmt-section-title">{sub["title"]}</h3>'
            f'<span class="tmt-section-subtitle">{sub["subtitle"]}</span></div>'
            f'<table class="tmt-table"><thead><tr>'
            f'<th data-type="text">Company</th>'
            f'<th data-type="text">Status</th>'
            f'<th data-type="num">Revenue (LTM)</th>'
            f'<th data-type="num">Growth YoY</th>'
            f'<th data-type="num">Net Leverage</th>'
            f'<th data-type="num">EBITDA Margin</th>'
            f'<th data-type="num">Op Margin</th>'
            f'<th data-type="num">FCF (LTM)</th>'
            f'<th data-type="num">Cash</th>'
            f'<th data-type="num">Total Debt</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
        )
    return (
        f'<div class="tmt-tab-content">'
        f'<div class="tmt-intro">TMT sector deep-dive. Data center construction is the macro demand signal; hyperscaler CapEx is the public-company supply commitment; revenue backlog is the contracted demand. Company tables follow.</div>'
        f'{dc_chart_html}{hyper_chart_html}{rpo_chart_html}{"".join(sections_html)}</div>'
    )


def build_macro_tab(macro_data):
    if not macro_data:
        return '<div class="placeholder-pane"><div class="ph-title">MACRO TAB</div><div>FRED data not available. Ensure FRED_API_KEY is set as a GitHub secret and fred.py is in the repo.</div></div>'
    categories = {
        "rates":     {"label": "Rates &amp; Treasury Curve", "items": []},
        "spreads":   {"label": "Credit Spreads",             "items": []},
        "inflation": {"label": "Inflation",                  "items": []},
        "labor":     {"label": "Labor Market",               "items": []},
        "activity":  {"label": "Economic Activity",          "items": []},
    }
    for key, m in macro_data.items():
        if not isinstance(m, dict): continue
        cat = m.get("_category", "other")
        if cat in categories: categories[cat]["items"].append((key, m))
    for cat in categories.values():
        cat["items"].sort(key=lambda x: x[0])
    def fmt_value(m):
        val = m.get("value"); units = m.get("_units", "")
        if val is None: return "n/a"
        try:
            v = float(val)
            if "%" in units or "YoY" in units: return f"{v:.2f}%"
            if v < 10: return f"{v:.2f}"
            if v < 1000: return f"{v:.1f}"
            return f"{v:,.0f}"
        except (TypeError, ValueError):
            return str(val)
    def fmt_change(m):
        change = m.get("change")
        if change is None: return ""
        try:
            c = float(change)
            sign = "+" if c >= 0 else ""
            cls = "macro-up" if c >= 0 else "macro-down"
            arrow = "&#9650;" if c >= 0 else "&#9660;"
            if abs(c) < 1: return f'<span class="{cls}">{arrow} {sign}{c:.2f}</span>'
            return f'<span class="{cls}">{arrow} {sign}{c:.1f}</span>'
        except (TypeError, ValueError):
            return ""
    def build_section(cat_key, cat_data):
        if not cat_data["items"]: return ""
        rows = []
        for key, m in cat_data["items"]:
            label = m.get("_label", key)
            value = fmt_value(m)
            change = fmt_change(m)
            as_of = m.get("as_of", "")
            freq = m.get("_frequency", "")
            series_id = m.get("_series_id", "")
            rows.append(
                f'<tr><td class="macro-row-label">{label}</td>'
                f'<td class="macro-row-value">{value}</td>'
                f'<td class="macro-row-change">{change}</td>'
                f'<td class="macro-row-asof">{as_of}</td>'
                f'<td class="macro-row-freq">{freq}</td>'
                f'<td class="macro-row-series">{series_id}</td></tr>'
            )
        return (
            f'<div class="macro-section"><h3 class="macro-section-title">{cat_data["label"]}</h3>'
            f'<table class="macro-table"><thead><tr>'
            f'<th>Indicator</th><th>Value</th><th>Change</th><th>As of</th><th>Freq</th><th>FRED ID</th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        )
    sections_html = "".join(build_section(k, v) for k, v in categories.items())
    return (
        '<div class="macro-tab-content">'
        '<div class="macro-tab-intro"><p>Source: <strong>FRED (Federal Reserve Economic Data)</strong>, St. Louis Fed. '
        'Header strip HY OAS, IG OAS, 10Y UST, and 2Y UST pull from these same FRED series '
        '(spreads converted from percent to bps in the header). Cache TTL 20 hours.</p></div>'
        f'{sections_html}</div>'
    )


def _fred_value(fred_data, key, mode="percent"):
    if not fred_data: return "n/a"
    m = fred_data.get(key, {})
    if not isinstance(m, dict): return "n/a"
    val = m.get("value")
    if val is None: return "n/a"
    try:
        v = float(val)
        if mode == "bps":
            return f"{int(round(v * 100))}"
        return f"{v:.2f}"
    except (TypeError, ValueError):
        return "n/a"


def build_html(all_rows, macro, top3, datetime_str, commodities=None, fred_data=None, sec_data=None, census_data=None, run_mode="full"):
    commodities = commodities or {}
    fred_data = fred_data or {}
    sec_data = sec_data or {}
    census_data = census_data or {}

    # Build sector snapshot panel (inserted at top of Overview pane).
    if SECTOR_SNAPSHOT_AVAILABLE and all_rows:
        try:
            snapshot_html = sector_snapshot.build_sector_snapshot(all_rows)
        except Exception as e:
            print(f"WARNING: sector_snapshot.build_sector_snapshot failed: {e}")
            snapshot_html = ""
    else:
        snapshot_html = ""
    overview_rows, market_rows, fin_summary_rows, fin_detail_rows = [], [], [], []
    # Four-tier counters (severity-based)
    crit_count = high_count = watch_count = mon_count = 0
    # Legacy 3-tier counters (status-based) for backwards compatibility
    g_count = a_count = r_count = 0
    name_count = len(all_rows)

    for r in all_rows:
        status = r.get('status','green').lower()
        severity = r.get('severity','').lower()
        if status == 'green': g_count += 1
        elif status == 'amber': a_count += 1
        elif status == 'red': r_count += 1
        if severity == 'critical': crit_count += 1
        elif severity == 'high': high_count += 1
        elif severity == 'watch': watch_count += 1
        elif severity == 'monitor': mon_count += 1
        co = r.get('company', '')
        co_slug = re.sub(r'[^a-z0-9]+', '-', co.lower()).strip('-')

        overview_rows.append(
            f'<tr data-status="{status}" data-severity="{r.get("severity","")}" data-company="{co.lower()}" data-sector="{r.get("sector","")}">'
            + company_cell_redesigned(r)
            + status_cell_redesigned(status, r.get('severity'), r)
            + concern_cell_redesigned(r, status)
            + ratings_cell_compact(r)
            + last_action_cell(r)
            + f'<td class="key-dev-redesigned" title="{r.get("key_dev","").replace(chr(34),"&quot;")}">{r.get("key_dev","")}</td>'
            + action_cell_redesigned(r)
            + '</tr>'
        )

        def _to_f(v):
            try:
                return float(str(v).replace(',','').replace('+','').replace('$','').strip())
            except:
                return None
        mc = _to_f(r.get('mkt_cap'))
        td = _to_f(r.get('total_debt'))
        cs = _to_f(r.get('cash'))
        ev_str = f"{mc + td - cs:.1f}" if (mc is not None and td is not None and cs is not None) else "n/a"

        market_rows.append(
            f'<tr data-status="{status}" data-severity="{r.get("severity","")}" data-company="{co.lower()}" data-sector="{r.get("sector","")}">'
            f'<td class="co-cell">{co}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            + money_cell(r.get('mkt_cap'))
            + money_cell(ev_str)
            + status_label_cell(status, r.get("severity"))
            + price_cell(r.get('price'))
            + stock_cell(r.get('stock_1d'))
            + stock_cell(r.get('stock_1m'))
            + stock_cell(r.get('stock_ytd'))
            + stock_cell(r.get('stock_1y'))
            + week52_cell(r.get('week52_high'), r.get('price'), 'high')
            + week52_cell(r.get('week52_low'), r.get('price'), 'low')
            + f'<td>{r.get("earnings","TBD")}</td>'
            + '</tr>'
        )

        fin_source = r.get('_financials_source', '')
        fin_warnings = r.get('_fin_warnings') or []
        filing_form = r.get('_filing_form', '')
        period_end = r.get('_period_end', '')
        if fin_source.startswith('SEC'):
            form_label = filing_form if filing_form else ""
            period_label = period_end if period_end else "unknown"
            source_marker = f'<span class="src-tag sec" title="Source: SEC EDGAR {form_label} as of {period_label}">SEC</span>'
            has_history = bool(sec_data.get(co))
        elif fin_source == 'yfinance':
            source_marker = '<span class="src-tag yf" title="Source: yfinance balance sheet (Total Debt fallback for non-SEC filer or unusual tag structure). Less authoritative than SEC EDGAR. Historical detail unavailable.">YF</span>'
            has_history = False
        else:
            source_marker = '<span class="src-tag claude" title="Source: Claude web search (less reliable than SEC EDGAR)">EST</span>'
            has_history = False
        warning_marker = ''
        if fin_warnings:
            warning_marker = f' <span class="data-warn" title="{"; ".join(fin_warnings)[:200]}">&#9888;</span>'
        expand_arrow = '<span class="fin-expand-arrow">&#9656;</span>' if has_history else '<span class="fin-expand-arrow disabled">&middot;</span>'

        fin_summary_rows.append(
            f'<tr class="fin-summary-row {"clickable" if has_history else ""}" data-status="{status}" data-severity="{r.get("severity","")}" data-company="{co.lower()}" data-co-slug="{co_slug}" data-sector="{r.get("sector","")}">'
            f'<td class="co-cell fin-co-cell">{expand_arrow} {co} {source_marker}{warning_marker}</td>'
            f'<td><span class="sector-tag">{r.get("sector","")}</span></td>'
            + status_label_cell(status, r.get("severity"))
            + money_cell(r.get('revenue_ltm'))
            + yoy_cell(r.get('revenue_yoy_pct'))
            + leverage_cell(r.get('nd_ebitda'))
            + margin_cell(r.get('ebitda_margin'))
            + margin_cell(r.get('op_margin'))
            + fcf_cell(r.get('fcf_ltm'))
            + money_cell(r.get('cash'))
            + money_cell(r.get('total_debt'))
            + '</tr>'
        )

        if has_history:
            sec_for_co = sec_data.get(co, {})
            detail_inner = fin_detail_html(co, sec_for_co)
            fin_detail_rows.append(
                f'<tr class="fin-detail-row" data-co-slug="{co_slug}" data-status="{status}" data-severity="{r.get("severity","")}" data-company="{co.lower()}" data-sector="{r.get("sector","")}" style="display:none;">'
                f'<td colspan="11">{detail_inner}</td></tr>'
            )

    fin_combined_rows = []
    detail_by_slug = {}
    for dr in fin_detail_rows:
        m = re.search(r'data-co-slug="([^"]+)"', dr)
        if m: detail_by_slug[m.group(1)] = dr
    for sr in fin_summary_rows:
        fin_combined_rows.append(sr)
        m = re.search(r'data-co-slug="([^"]+)"', sr)
        if m and m.group(1) in detail_by_slug:
            fin_combined_rows.append(detail_by_slug[m.group(1)])

    top3_html = ''.join(
        f'<li><strong>{i.get("name","")}</strong>: {i.get("note","")}</li>'
        for i in top3
    )

    redflag_rows_list = build_redflag_rows(all_rows)
    try:
        from red_flags import FLAG_DEFINITIONS
        rf_headers = "".join(
            f'<th data-type="text" title="{f["name"]}: {f["threshold"]}"><div class="rf-hdr-num">{f["number"]}</div><div class="rf-hdr-label">{f["name"]}</div></th>'
            for f in FLAG_DEFINITIONS
        )
    except ImportError:
        rf_headers = ""

    tmt_tab_html = build_tmt_tab(all_rows, sec_data, census_data)
    macro_tab_html = build_macro_tab(fred_data)

    hy_oas = _fred_value(fred_data, 'hy_oas', mode='bps')
    if hy_oas == "n/a": hy_oas = macro.get('hy_oas', 'n/a')
    ig_oas = _fred_value(fred_data, 'ig_oas', mode='bps')
    if ig_oas == "n/a": ig_oas = macro.get('ig_oas', 'n/a')
    t10y = _fred_value(fred_data, 'ust_10y', mode='percent')
    if t10y == "n/a": t10y = macro.get('treasury_10y', 'n/a')
    t2y = _fred_value(fred_data, 'ust_2y', mode='percent')
    if t2y == "n/a": t2y = macro.get('treasury_2y', 'n/a')

    vix = macro.get('vix','n/a')
    sp500 = macro.get('sp500','n/a')
    sp500_1d = macro.get('sp500_1d','')
    sp500_up = str(sp500_1d).startswith('+')
    sp500_display = sp500
    try:
        sp500_int = int(str(sp500).replace(',','').replace('$','').strip())
        sp500_display = f"${sp500_int:,}"
    except:
        sp500_display = str(sp500)

    def macro_item(label, value, change=None, up=None):
        change_html = ''
        if change:
            cls = 'macro-up' if up else 'macro-down'
            arrow = '&#9650;' if up else '&#9660;'
            change_html = f'<span class="{cls}">{arrow} {change}</span>'
        return f'<div class="macro-item"><span class="macro-label">{label}</span><span class="macro-value">{value}</span>{change_html}</div>'

    def commodity_item(label, key, prefix='$', suffix=''):
        c = commodities.get(key)
        if not c: return macro_item(label, 'n/a')
        chg = c.get('change', '')
        up = chg.startswith('+') if chg else None
        return macro_item(label, f'{prefix}{c["value"]}{suffix}', chg, up)

    macro_html = (
        '<div class="macro-strip">'
        + macro_item('HY OAS', f'{hy_oas} bps')
        + macro_item('IG OAS', f'{ig_oas} bps')
        + macro_item('10Y UST', f'{t10y}%')
        + macro_item('2Y UST', f'{t2y}%')
        + macro_item('VIX', vix)
        + macro_item('S&amp;P 500', sp500_display, sp500_1d, sp500_up)
        + commodity_item('Nasdaq', 'nasdaq', prefix='')
        + commodity_item('Dow', 'dow', prefix='')
        + commodity_item('WTI', 'wti')
        + commodity_item('Brent', 'brent')
        + commodity_item('Gold', 'gold')
        + commodity_item('EUR/USD', 'eurusd', prefix='')
        + f'<div class="macro-item macro-note">Live macro as of {datetime_str}</div>'
        + '</div>'
    )

    css = """
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap");
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"IBM Plex Sans",-apple-system,sans-serif;background:#0a0e14;color:#e6edf3;font-size:13px}
header{background:linear-gradient(135deg,#6b0000 0%,#8B0000 60%,#a00000 100%);color:#fff;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;border-bottom:2px solid #ff000033}
.title{font-size:22px;font-weight:700;letter-spacing:2px;font-family:"IBM Plex Mono",monospace}
.subtitle{font-size:11px;margin-top:3px;opacity:.75;letter-spacing:1px;text-transform:uppercase}
.right-block{text-align:right}
.pills{display:flex;gap:8px;justify-content:flex-end}
.pill{padding:5px 14px;border-radius:3px;font-weight:700;font-size:11px;color:#fff;letter-spacing:.5px;font-family:"IBM Plex Mono",monospace}
.pill.red{background:#cc0000}.pill.amber{background:#e6a700}.pill.green{background:#2e7d32}
.pill.severity-critical-pill{background:#8B0000;color:#fff}
.pill.severity-high-pill{background:#DC2626;color:#fff}
.pill.severity-watch-pill{background:#e6a700;color:#fff}
.pill.severity-monitor-pill{background:#2e7d32;color:#fff}
.status-legend{background:#0f1620;border:1px solid #1e2a3a;border-radius:4px;margin:10px 28px;padding:14px 18px;font-size:11px;font-family:"IBM Plex Mono",monospace}
.status-legend.hidden{display:none}
.status-legend h4{margin:0 0 10px 0;font-size:11px;color:#cfd8e3;letter-spacing:1.5px;text-transform:uppercase}
.status-legend .legend-row{display:flex;align-items:center;gap:14px;padding:7px 0;border-bottom:1px solid #16202b}
.status-legend .legend-row:last-of-type{border-bottom:none}
.status-legend .legend-desc{color:#a0afbf;flex:1;line-height:1.5;font-size:11px}
.status-legend .status-badge{min-width:80px;text-align:center;font-size:11px;padding:4px 8px}
.status-legend .legend-footnote{margin-top:10px;font-size:10px;color:#5a7287;font-style:italic;padding-top:8px;border-top:1px solid #16202b}
.last-refresh{font-size:10px;margin-top:6px;opacity:.7;font-family:"IBM Plex Mono",monospace}
.macro-strip{background:#0d1520;border-bottom:1px solid #1e3a5f;padding:10px 28px;display:flex;gap:0;flex-wrap:wrap;align-items:center}
.macro-item{padding:4px 20px;border-right:1px solid #1e3a5f;display:flex;flex-direction:column;align-items:center;gap:2px}
.macro-item:last-child{border-right:none;margin-left:auto}
.macro-label{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:#4a6080;font-family:"IBM Plex Mono",monospace}
.macro-value{font-size:13px;font-weight:600;color:#a0c4e8;font-family:"IBM Plex Mono",monospace}
.macro-up{font-size:10px;color:#4ec38a;font-weight:600}
.macro-down{font-size:10px;color:#ff6b6b;font-weight:600}
.macro-note{font-size:10px;color:#3a4a5a;align-items:flex-end;border-right:none}
.tabs{background:#0d1117;padding:0 28px;display:flex;gap:0;border-bottom:1px solid #1e2a3a;flex-wrap:wrap}
.tab{padding:11px 18px;font-family:"IBM Plex Mono",monospace;font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase;color:#4a6080;cursor:pointer;border:none;border-bottom:2px solid transparent;background:none;transition:all .15s}
.tab:hover{color:#a0b4c8}
.tab.active{color:#fff;border-bottom-color:#8B0000;background:#0a0e14}
.controls{padding:12px 28px;background:#0d1117;border-bottom:1px solid #1e2a3a;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.controls button{padding:6px 14px;border:1px solid #1e2a3a;background:#0d1520;color:#a0b4c8;cursor:pointer;font-weight:600;border-radius:3px;font-size:11px;letter-spacing:.5px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;transition:all .15s}
.controls button:hover{background:#1e2a3a;color:#e6edf3}
.controls button.active{background:#8B0000;color:#fff;border-color:#8B0000}
.controls input,.controls select{padding:6px 12px;border:1px solid #1e2a3a;border-radius:3px;font-size:12px;background:#0d1520;color:#e6edf3}
.controls input{width:200px}
.pane{display:none}.pane.active{display:block}
table{width:100%;border-collapse:collapse;background:#0a0e14;table-layout:fixed}
thead th{background:#0d1117;color:#4a6080;padding:10px;text-align:left;font-size:10px;letter-spacing:1px;text-transform:uppercase;border-bottom:1px solid #1e2a3a;cursor:pointer;user-select:none;position:sticky;top:0;font-family:"IBM Plex Mono",monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
thead th:hover{background:#0d1520;color:#a0b4c8}
tbody td{padding:9px 10px;border-bottom:1px solid #0d1520;font-size:12px;vertical-align:middle;overflow:hidden}
tbody tr:hover{background:#0d1520}
.co-cell{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.status{font-weight:700;font-size:11px;letter-spacing:.5px;font-family:"IBM Plex Mono",monospace}
.status.red{color:#ff6b6b}.status.amber{color:#f0b429}.status.green{color:#4ec38a}
.sector-tag{background:#0d1520;border:1px solid #1e2a3a;color:#7090a8;font-size:10px;padding:2px 7px;border-radius:2px;letter-spacing:.5px;white-space:nowrap}
.stock-up{color:#4ec38a;font-weight:700;font-family:"IBM Plex Mono",monospace}
.stock-down{color:#ff6b6b;font-weight:700;font-family:"IBM Plex Mono",monospace}
.stock-flat{color:#3a4a5a;font-family:"IBM Plex Mono",monospace}
.lev-amber{color:#f0b429;font-weight:700;font-family:"IBM Plex Mono",monospace}
.num-cell{text-align:right;font-variant-numeric:tabular-nums;font-family:"IBM Plex Mono",monospace;font-size:12px}
.overview-table tbody td{padding:12px 14px;vertical-align:middle}
.overview-table tbody td:not(:nth-child(1)):not(:nth-child(6)),
.overview-table thead th:not(:nth-child(1)):not(:nth-child(6)){text-align:center}
#pane-market tbody td:not(:nth-child(1)),
#pane-market thead th:not(:nth-child(1)){text-align:center}
#pane-financials tbody td:not(:nth-child(1)),
#pane-financials thead th:not(:nth-child(1)){text-align:center}
#pane-market .num-cell,
#pane-financials .num-cell{text-align:center}
.co-cell-stack{font-family:"IBM Plex Sans",sans-serif}
.co-name{font-weight:600;font-size:13px;color:#e6edf3;line-height:1.2}
.co-sector{font-family:"IBM Plex Mono",monospace;font-size:9px;color:#7090a8;margin-top:3px;letter-spacing:.5px}
.status-badge{font-weight:700;font-size:13px;letter-spacing:1px;font-family:"IBM Plex Mono",monospace;padding:5px 12px;border-radius:3px;display:inline-block;text-align:center}
.status-badge.red{color:#ff6b6b;background:rgba(255,107,107,.12)}
.status-badge.amber{color:#f0b429;background:rgba(240,180,41,.12)}
.status-badge.green{color:#4ec38a;background:rgba(78,195,138,.12)}
/* Four-tier severity colors (severity drives visual distinction within red status) */
.status-badge.severity-critical{color:#ff5a5a;background:rgba(255,90,90,.10);font-weight:700}
.status-badge.severity-high{color:#ff8a3d;background:rgba(255,138,61,.10);font-weight:700}
.status-badge.severity-watch{color:#f0b429;background:rgba(240,180,41,.12);border:1px solid rgba(240,180,41,.4)}
.status-badge.severity-monitor{color:#4ec38a;background:rgba(78,195,138,.12);border:1px solid rgba(78,195,138,.4)}
.severity-label{font-size:9px;letter-spacing:1.2px;opacity:.85;margin-top:2px;display:block}
.concern-cell{padding:10px 12px;font-family:"IBM Plex Mono",monospace}
.concern-num{font-weight:700;font-size:18px;line-height:1}
.concern-denom{font-size:11px;color:#3a4a5a;font-weight:400;margin-left:2px}
.concern-bar{background:#21262d;border-radius:2px;height:4px;margin:6px auto 0;width:80px;overflow:hidden}
.concern-bar div{height:100%;border-radius:2px}
.concern-tier{font-size:9px;color:#7090a8;margin-top:4px;text-transform:uppercase;letter-spacing:.5px}
.watch-suffix{font-size:10px;color:#f0b429;font-weight:600;margin-left:4px;font-family:"IBM Plex Mono",monospace}
.fin-summary-row.clickable{cursor:pointer}
.fin-summary-row.clickable:hover{background:#0d1520}
.fin-summary-row.expanded{background:rgba(139,0,0,.06)}
.fin-co-cell{display:flex;align-items:center;gap:6px}
.fin-expand-arrow{display:inline-block;color:#4a6080;font-size:10px;transition:transform .15s ease;width:10px;text-align:center}
.fin-expand-arrow.disabled{color:#1e2a3a}
.fin-summary-row.expanded .fin-expand-arrow:not(.disabled){transform:rotate(90deg);color:#a0c4e8}
.fin-detail-row td{padding:0;background:#080b10;border-bottom:1px solid #1e2a3a}
.fin-detail-content{padding:18px 28px}
.fin-detail-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid #1e2a3a;flex-wrap:wrap;gap:8px}
.fin-detail-title{font-family:"IBM Plex Mono",monospace;font-size:12px;color:#a0c4e8;font-weight:700;letter-spacing:1px;text-transform:uppercase}
.fin-detail-source{font-family:"IBM Plex Mono",monospace;font-size:10px;color:#7090a8;letter-spacing:.5px}
.fin-detail-section{margin-bottom:18px}
.fin-detail-subtitle{font-family:"IBM Plex Mono",monospace;font-size:10px;color:#8B0000;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px}
.fin-detail-table{width:auto;min-width:80%;border-collapse:collapse;font-family:"IBM Plex Mono",monospace;table-layout:auto}
.fin-detail-table th{background:#0d1117;color:#4a6080;padding:8px 12px;text-align:right;font-size:10px;letter-spacing:.5px;text-transform:uppercase;font-weight:600;border-bottom:1px solid #1e2a3a;cursor:default;white-space:nowrap}
.fin-detail-table th:hover{background:#0d1117;color:#4a6080}
.fin-detail-table th.fd-metric-col{text-align:left}
.fin-detail-table td{padding:7px 12px;border-bottom:1px solid #0d1520;font-size:11px;color:#a0c4e8;vertical-align:middle;text-align:right;white-space:nowrap}
.fd-metric-label{font-family:"IBM Plex Sans",sans-serif !important;color:#e6edf3 !important;font-weight:500;text-align:left !important}
.fd-val{font-variant-numeric:tabular-nums}
.fd-yoy{font-size:11px;font-weight:600}
.fd-trend{font-size:14px}
.fd-arrow{font-weight:700}
.fin-detail-footer{font-size:10px;color:#4a6080;font-style:italic;margin-top:10px;padding-top:8px;border-top:1px solid #1e2a3a;line-height:1.5}
.fin-detail-empty{padding:30px;text-align:center;color:#4a6080;font-family:"IBM Plex Mono",monospace;font-size:12px;font-style:italic}
.rf-legend{padding:14px 28px;background:#0d1117;border-bottom:1px solid #1e2a3a;display:flex;flex-wrap:wrap;gap:24px;align-items:center;font-size:11px;color:#a0b4c8}
.rf-legend-item{display:flex;align-items:center;gap:6px;font-family:"IBM Plex Mono",monospace}
.rf-legend-item .rf-pill{width:22px;height:22px;font-size:12px}
.rf-legend-note{margin-left:auto;font-size:10px;color:#7090a8;font-style:italic;font-family:"IBM Plex Sans",sans-serif}
.rf-table{width:100%;border-collapse:collapse;background:#0a0e14;table-layout:fixed}
.rf-table th{background:#0d1117;color:#4a6080;padding:8px 6px;font-size:9px;letter-spacing:.5px;text-transform:uppercase;border-bottom:1px solid #1e2a3a;font-family:"IBM Plex Mono",monospace;font-weight:600;vertical-align:bottom;text-align:center}
.rf-table thead th:first-child{text-align:left;width:14%;padding-left:14px}
.rf-table thead th:nth-child(2){width:9%}
.rf-table thead th:nth-child(3){width:7%}
.rf-table thead th:last-child{width:7%}
.rf-hdr-num{font-size:13px;color:#a0b4c8;font-weight:700;margin-bottom:4px}
.rf-hdr-label{font-size:8px;color:#4a6080;line-height:1.2;white-space:normal}
.rf-table tbody td{padding:8px 6px;border-bottom:1px solid #0d1520;font-size:12px;vertical-align:middle;text-align:center}
.rf-table tbody td.rf-co{text-align:left;padding-left:14px;font-weight:600;color:#e6edf3;font-size:13px}
.rf-cell{padding:8px 4px;text-align:center;vertical-align:middle}
.rf-pill{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:3px;font-family:"IBM Plex Mono",monospace;font-weight:700;cursor:help;font-size:13px}
.rf-flagged{background:rgba(255,107,107,.15);color:#ff6b6b;border:1px solid rgba(255,107,107,.4)}
.rf-watch{background:rgba(240,180,41,.12);color:#f0b429;border:1px solid rgba(240,180,41,.35)}
.rf-clear{background:rgba(78,195,138,.08);color:#4ec38a;border:1px solid rgba(78,195,138,.25)}
.rf-na{background:#0d1520;color:#3a4a5a;border:1px solid #1e2a3a}
.rf-summary{font-family:"IBM Plex Mono",monospace;font-size:14px;font-weight:700}
.rf-summary strong{font-size:16px}
.rf-watch-suffix{font-size:10px;color:#f0b429;margin-left:3px;font-weight:600}
.ratings-cell{padding:6px 8px;font-family:"IBM Plex Mono",monospace;font-size:10px;line-height:1.35}
.rating-row-compact{display:flex;align-items:center;gap:8px;font-family:"IBM Plex Mono",monospace;font-size:11px;line-height:1.6}
.agency-tag{display:inline-block;width:11px;color:#4a6080;font-weight:600}
.rating-val{color:#e6edf3;font-weight:600;min-width:36px}
.outlook-tag{font-weight:700;font-size:9px;width:32px;display:inline-block}
.stale-flag{color:#f0b429;font-size:11px;margin-left:2px;cursor:help}
.action-date-cell{font-family:"IBM Plex Mono",monospace;padding:10px 12px}
.action-date-main{font-size:11px;color:#a0b4c8;font-weight:500;line-height:1.3}
.action-date-sub{font-size:9px;color:#4a6080;margin-top:3px;text-transform:uppercase;letter-spacing:.5px}
.action-date-na{font-size:10px;color:#3a4a5a;font-style:italic}
.key-dev-redesigned{color:#a0b4c8;font-size:12px;line-height:1.5;padding:10px 14px}
.action-redesigned{padding:6px 14px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;display:inline-block;white-space:nowrap}
.action-redesigned.red{background:#3a0000;color:#ff6b6b;border:1px solid #8B0000}
.action-redesigned.amber{background:#2a1a00;color:#f0b429;border:1px solid #8b6200}
.action-redesigned.green{background:#001a0a;color:#4ec38a;border:1px solid #1a5c32}
/* Four-tier action button colors aligned with severity */
.action-redesigned.escalate{background:rgba(255,90,90,.12);color:#ff5a5a;border:1px solid rgba(255,90,90,.45)}
.action-redesigned.review{background:rgba(255,138,61,.10);color:#ff8a3d;border:1px solid rgba(255,138,61,.45)}
.action-redesigned.watch{background:#2a1a00;color:#f0b429;border:1px solid #8b6200}
.action-redesigned.monitor{background:#001a0a;color:#4ec38a;border:1px solid #1a5c32}
.price-cell{font-weight:700;color:#a0c4e8}
.src-tag{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:8px;letter-spacing:.5px;padding:1px 4px;border-radius:2px;margin-left:6px;vertical-align:middle;cursor:help}
.src-tag.sec{background:#001a0a;color:#4ec38a;border:1px solid #1a5c32}
.src-tag.claude{background:#0d1520;color:#7090a8;border:1px solid #1e2a3a}
.src-tag.yf{background:#1a1500;color:#f0b429;border:1px solid #5c4a1a}
.data-warn{color:#f0b429;font-size:12px;cursor:help;margin-left:2px}
.tmt-tab-content{padding:24px 28px}
.tmt-intro{color:#a0b4c8;font-size:12px;line-height:1.5;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid #1e2a3a;max-width:960px}
.dc-construction-section{margin-bottom:36px;padding:20px;background:linear-gradient(135deg,#0d1520 0%,#0a0e14 100%);border:1px solid #1e3a5f;border-left:3px solid #8B0000;border-radius:4px}
.dc-construction-header{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid #1e2a3a}
.dc-construction-empty{padding:30px;text-align:center;color:#4a6080;font-family:"IBM Plex Mono",monospace;font-size:12px;font-style:italic}
.dc-source{font-family:"IBM Plex Mono",monospace;font-size:10px;color:#7090a8;letter-spacing:.5px}
.dc-kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
.dc-kpi{background:#0a0e14;border:1px solid #1e2a3a;border-radius:4px;padding:14px}
.dc-kpi-label{font-family:"IBM Plex Mono",monospace;font-size:9px;color:#7090a8;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.dc-kpi-value{font-family:"IBM Plex Mono",monospace;font-size:20px;font-weight:700;letter-spacing:.5px}
.dc-chart-label{font-family:"IBM Plex Mono",monospace;font-size:9px;color:#7090a8;text-transform:uppercase;letter-spacing:1px;margin:14px 0 6px}
.dc-chart-wrap{position:relative;width:100%;height:240px;margin-bottom:6px}
.dc-chart-wrap-short{position:relative;width:100%;height:200px;margin-bottom:6px}
.hyper-chart-section{margin-bottom:36px}
.hyper-chart-header{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:14px;padding-bottom:6px;border-bottom:1px solid #1e2a3a}
.hyper-chart-callout{text-align:right;padding:8px 14px;background:#0d1520;border:1px solid #1e2a3a;border-radius:4px;min-width:180px}
.hyper-chart-callout-label{font-family:"IBM Plex Mono",monospace;font-size:9px;color:#7090a8;text-transform:uppercase;letter-spacing:1px}
.hyper-chart-callout-value{font-family:"IBM Plex Mono",monospace;font-size:22px;color:#a0c4e8;font-weight:700;margin:4px 0}
.hyper-chart-wrap{position:relative;width:100%;height:280px}
.tmt-section{margin-bottom:28px}
.tmt-section-header{display:flex;align-items:baseline;gap:14px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #1e2a3a;flex-wrap:wrap}
.tmt-section-title{font-family:"IBM Plex Mono",monospace;font-size:13px;color:#8B0000;text-transform:uppercase;letter-spacing:1.5px;font-weight:700;margin:0}
.tmt-section-subtitle{font-size:11px;color:#7090a8;font-style:italic}
.tmt-table{width:100%;border-collapse:collapse;table-layout:auto}
.tmt-table th{background:#0d1117;color:#4a6080;padding:8px 10px;font-size:10px;letter-spacing:.5px;text-transform:uppercase;border-bottom:1px solid #1e2a3a;font-family:"IBM Plex Mono",monospace;font-weight:600;text-align:center;cursor:pointer;white-space:nowrap}
.tmt-table th:first-child{text-align:left}
.tmt-table th:hover{background:#0d1520;color:#a0b4c8}
.tmt-table tbody td{padding:8px 10px;border-bottom:1px solid #0d1520;font-size:12px;vertical-align:middle;text-align:center}
.tmt-table tbody td.co-cell{text-align:left}
.tmt-table tbody tr:hover{background:#0d1520}
.tmt-table .num-cell{text-align:center}
.tmt-missing{color:#3a4a5a;font-size:11px;font-style:italic;text-align:left;padding-left:10px}
.macro-tab-content{padding:24px 28px}
.macro-tab-intro{color:#a0b4c8;font-size:12px;line-height:1.5;margin-bottom:24px;padding-bottom:14px;border-bottom:1px solid #1e2a3a;max-width:960px}
.macro-section{margin-bottom:28px}
.macro-section-title{font-family:"IBM Plex Mono",monospace;font-size:11px;color:#8B0000;text-transform:uppercase;letter-spacing:1.5px;font-weight:700;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #1e2a3a}
.macro-table{width:auto;min-width:560px;border-collapse:collapse}
.macro-table th{background:#0d1117;color:#4a6080;padding:8px 14px;text-align:left;font-size:10px;letter-spacing:1px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;font-weight:600;border-bottom:1px solid #1e2a3a;cursor:default}
.macro-table td{padding:8px 14px;border-bottom:1px solid #0d1520;font-size:12px;color:#a0b4c8;vertical-align:middle;font-family:"IBM Plex Mono",monospace}
.macro-row-label{color:#e6edf3;font-family:"IBM Plex Sans",sans-serif !important;font-weight:500}
.macro-row-value{color:#a0c4e8;font-weight:700;text-align:right}
.macro-row-change{font-weight:600}
.macro-row-asof{color:#7090a8;font-size:11px}
.macro-row-freq{color:#7090a8;font-size:11px;text-transform:uppercase}
.macro-row-series{color:#4a6080;font-size:10px}
.placeholder-pane{padding:80px 28px;text-align:center;color:#4a6080;font-family:"IBM Plex Mono",monospace;font-size:13px;letter-spacing:1px}
.placeholder-pane .ph-title{font-size:16px;color:#a0b4c8;margin-bottom:10px;letter-spacing:2px}
.methodology-content{padding:28px 32px;color:#a0b4c8;font-size:13px;line-height:1.6;max-width:920px}
.methodology-content h2{font-family:"IBM Plex Mono",monospace;font-size:13px;color:#8B0000;text-transform:uppercase;letter-spacing:1.5px;margin:28px 0 12px;padding-bottom:6px;border-bottom:1px solid #1e2a3a;font-weight:700}
.methodology-content h2:first-child{margin-top:0}
.methodology-content p{margin:8px 0 12px;color:#a0b4c8}
.methodology-content ul{margin:8px 0 16px;padding-left:22px}
.methodology-content li{padding:4px 0;color:#a0b4c8}
.methodology-content code{font-family:"IBM Plex Mono",monospace;background:#0d1520;padding:1px 6px;border-radius:2px;font-size:11px;color:#a0c4e8}
.methodology-table{border-collapse:collapse;margin:8px 0 18px;width:auto;min-width:50%}
.methodology-table th{background:#0d1117;color:#4a6080;padding:8px 14px;text-align:left;font-size:10px;letter-spacing:1px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;font-weight:600;border-bottom:1px solid #1e2a3a}
.methodology-table td{padding:8px 14px;border-bottom:1px solid #0d1520;font-size:12px;color:#a0b4c8;vertical-align:middle}
.methodology-table td:first-child{font-family:"IBM Plex Mono",monospace}
footer{background:linear-gradient(135deg,#6b0000,#8B0000);color:#fff;padding:20px 28px;border-top:2px solid #ff000033}
footer h3{margin-bottom:12px;font-size:12px;letter-spacing:1.5px;text-transform:uppercase;font-family:"IBM Plex Mono",monospace;opacity:.8}
footer ol{padding-left:20px}
footer li{padding:5px 0;font-size:13px;line-height:1.5}
footer li strong{color:#ffaaaa}
"""

    js = """
(function(){
  var panes={
    overview:document.getElementById('pane-overview'),
    sectors:document.getElementById('pane-sectors'),
    market:document.getElementById('pane-market'),
    financials:document.getElementById('pane-financials'),
    tmt:document.getElementById('pane-tmt'),
    redflags:document.getElementById('pane-redflags'),
    macro:document.getElementById('pane-macro'),
    methodology:document.getElementById('pane-methodology')
  };
  var tabs=document.querySelectorAll('.tab');
  tabs.forEach(function(t){t.addEventListener('click',function(){
    tabs.forEach(function(x){x.classList.remove('active');});
    Object.values(panes).forEach(function(p){if(p)p.classList.remove('active');});
    t.classList.add('active');
    var pane=panes[t.dataset.tab];if(pane)pane.classList.add('active');
  });});

  document.querySelectorAll('.fin-summary-row.clickable').forEach(function(row){
    row.addEventListener('click',function(e){
      var slug=row.dataset.coSlug;
      if(!slug)return;
      var detail=document.querySelector('.fin-detail-row[data-co-slug="'+slug+'"]');
      if(!detail)return;
      var isOpen=row.classList.contains('expanded');
      if(isOpen){
        row.classList.remove('expanded');
        detail.style.display='none';
      }else{
        row.classList.add('expanded');
        detail.style.display='table-row';
      }
    });
  });

  var btns=document.querySelectorAll('.controls button[data-filter]');
  var search=document.getElementById('searchBox');
  var sel=document.getElementById('sectorFilter');
  var af='all';

  function applyAll(){
    var q=(search.value||'').toLowerCase();
    var sv=sel.value;
    var crit=0,high=0,wat=0,mon=0;
    document.querySelectorAll('.pane tbody tr[data-status]').forEach(function(row){
      if(row.classList.contains('fin-detail-row'))return;
      var st=(row.dataset.status||'').toLowerCase();
      var sev=(row.dataset.severity||'').toLowerCase();
      var co=(row.dataset.company||'');
      var sc=(row.dataset.sector||'');
      // Four-tier filter: 'critical'/'high' match severity, 'amber'/'green' match status (legacy)
      var pf=af==='all';
      if(!pf){
        if(af==='critical')pf=(sev==='critical');
        else if(af==='high')pf=(sev==='high');
        else if(af==='amber')pf=(st==='amber'||sev==='watch');
        else if(af==='green')pf=(st==='green'||sev==='monitor');
        else pf=(st===af);
      }
      var ps=!q||co.indexOf(q)>-1;
      var psc=sv==='all'||sc===sv;
      var sh=pf&&ps&&psc;
      row.style.display=sh?'':'none';
      if(row.classList.contains('fin-summary-row')){
        var slug=row.dataset.coSlug;
        if(slug){
          var det=document.querySelector('.fin-detail-row[data-co-slug="'+slug+'"]');
          if(det&&!sh){
            det.style.display='none';
            row.classList.remove('expanded');
          }
        }
      }
    });
    // Recount visible Overview rows by severity tier
    document.querySelectorAll('#pane-overview tbody tr').forEach(function(row){
      if(row.style.display!=='none'){
        var sev=(row.dataset.severity||'').toLowerCase();
        if(sev==='critical')crit++;
        else if(sev==='high')high++;
        else if(sev==='watch')wat++;
        else if(sev==='monitor')mon++;
      }
    });
    var critEl=document.getElementById('critCount');if(critEl)critEl.textContent='CRITICAL '+crit;
    var highEl=document.getElementById('highCount');if(highEl)highEl.textContent='HIGH '+high;
    var watEl=document.getElementById('watchCount');if(watEl)watEl.textContent='AMBER '+wat;
    var monEl=document.getElementById('monCount');if(monEl)monEl.textContent='MONITOR '+mon;
  }

  btns.forEach(function(b){b.addEventListener('click',function(){
    btns.forEach(function(x){x.classList.remove('active');});
    b.classList.add('active');af=b.dataset.filter;applyAll();
  });});
  search.addEventListener('input',applyAll);
  sel.addEventListener('change',applyAll);

  var secs=new Set();
  document.querySelectorAll('#pane-overview tbody tr').forEach(function(r){
    var x=(r.dataset.sector||'').trim();if(x)secs.add(x);
  });
  Array.from(secs).sort().forEach(function(x){
    var o=document.createElement('option');o.value=x;o.textContent=x;sel.appendChild(o);
  });

  document.querySelectorAll('.pane table').forEach(function(tbl){
    var isFinTab = tbl.closest('#pane-financials');
    var ths=tbl.querySelectorAll('thead th');
    var sc=-1,sd=1;
    ths.forEach(function(th,idx){
      th.style.cursor = 'pointer';
      th.addEventListener('click',function(){
        var t=th.dataset.type||'text';
        if(sc===idx)sd=-sd;else{sc=idx;sd=1;}
        var tb=tbl.querySelector('tbody');
        if(isFinTab){
          // Financials tab: rows come in pairs (summary + detail).
          // Sort by summary rows, keep their detail row attached.
          var pairs=[];
          var summaryRows=Array.from(tb.querySelectorAll('tr.fin-summary-row'));
          summaryRows.forEach(function(sumRow){
            var slug=sumRow.dataset.coSlug;
            var detRow=slug?tb.querySelector('.fin-detail-row[data-co-slug="'+slug+'"]'):null;
            pairs.push({summary:sumRow,detail:detRow});
          });
          pairs.sort(function(a,b){
            var av=a.summary.cells[idx]?a.summary.cells[idx].textContent.trim():'';
            var bv=b.summary.cells[idx]?b.summary.cells[idx].textContent.trim():'';
            if(t==='num'){av=parseFloat(av.replace(/[^0-9.\\-]/g,''))||0;bv=parseFloat(bv.replace(/[^0-9.\\-]/g,''))||0;return (av-bv)*sd;}
            return av.localeCompare(bv)*sd;
          });
          tb.innerHTML='';
          pairs.forEach(function(p){
            tb.appendChild(p.summary);
            if(p.detail)tb.appendChild(p.detail);
          });
        } else {
          var rows=Array.from(tb.querySelectorAll('tr'));
          rows.sort(function(a,b){
            var av=a.cells[idx]?a.cells[idx].textContent.trim():'';
            var bv=b.cells[idx]?b.cells[idx].textContent.trim():'';
            if(t==='num'){av=parseFloat(av.replace(/[^0-9.\\-]/g,''))||0;bv=parseFloat(bv.replace(/[^0-9.\\-]/g,''))||0;return (av-bv)*sd;}
            if(t==='date'){av=new Date(av).getTime()||0;bv=new Date(bv).getTime()||0;return (av-bv)*sd;}
            return av.localeCompare(bv)*sd;
          });
          tb.innerHTML='';rows.forEach(function(r){tb.appendChild(r);});
        }
      });
    });
  });

  applyAll();
})();
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning Credit Digest</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>{css}</style>
</head>
<body>
<header>
  <div>
    <div class="title">MORNING CREDIT DIGEST</div>
    <div class="subtitle">2LOD Credit Surveillance &nbsp;&bull;&nbsp; US Corporate Watchlist &nbsp;&bull;&nbsp; {name_count} Names</div>
  </div>
  <div class="right-block">
    <div class="pills">
      <span class="pill severity-monitor-pill" id="monCount" title="Monitor: 0 flagged AND ≤ 3 watch">MONITOR {mon_count}</span>
      <span class="pill severity-watch-pill" id="watchCount" title="Watch: 1-2 flagged OR (0 flagged AND ≥ 4 watch)">AMBER {watch_count}</span>
      <span class="pill severity-high-pill" id="highCount" title="High: 3 flagged OR (2 flagged AND ≥ 3 watch)">HIGH {high_count}</span>
      <span class="pill severity-critical-pill" id="critCount" title="Critical: ≥ 4 flagged OR (≥ 3 flagged AND ≥ 2 watch)">CRITICAL {crit_count}</span>
    </div>
    <div class="last-refresh">Updated: {datetime_str} &nbsp;&bull;&nbsp; Refresh: <span style="font-weight:700;color:{'#4ec38a' if run_mode == 'full' else '#a0afbf'}" title="{'WEEKLY: Friday full refresh with all ratings and news from web search.' if run_mode == 'full' else 'DAILY: Monday-Thursday refresh of market data and macro. Ratings and news cached from last weekly refresh; targeted news refresh for amber/red names.'}">{('WEEKLY' if run_mode == 'full' else 'DAILY')}</span></div>
  </div>
</header>
{macro_html}
<div class="tabs">
  <button class="tab active" data-tab="overview">Overview</button>
  <button class="tab" data-tab="sectors">Sectors</button>
  <button class="tab" data-tab="market">Market Data</button>
  <button class="tab" data-tab="financials">Financials</button>
  <button class="tab" data-tab="tmt">TMT</button>
  <button class="tab" data-tab="redflags">Red Flags</button>
  <button class="tab" data-tab="macro">Macro</button>
  <button class="tab" data-tab="methodology">Methodology</button>
</div>
<div class="controls">
  <button class="active" data-filter="all">All</button>
  <button data-filter="critical" title="Critical: ≥ 4 flagged OR (≥ 3 flagged AND ≥ 2 watch)">Critical</button>
  <button data-filter="high" title="High: 3 flagged OR (2 flagged AND ≥ 3 watch)">High</button>
  <button data-filter="amber" title="Amber: 1-2 flagged OR (0 flagged AND ≥ 4 watch)">Amber</button>
  <button data-filter="green" title="Monitor: 0 flagged AND ≤ 3 watch">Monitor</button>
  <input type="text" id="searchBox" placeholder="Search company...">
  <select id="sectorFilter"><option value="all">All Sectors</option></select>
  <button id="statusLegendToggle" type="button" style="margin-left:auto;font-size:11px;color:#7eb3cf;background:transparent;border:1px dashed #2d4a5d;padding:5px 10px;cursor:pointer;border-radius:3px;" title="Toggle status definitions" onclick="document.getElementById('statusLegend').classList.toggle('hidden')">&#9432; What do statuses mean?</button>
</div>
<div id="statusLegend" class="status-legend hidden">
  <h4>STATUS DEFINITIONS</h4>
  <div class="legend-row">
    <span class="status-badge severity-critical">CRITICAL</span>
    <span class="legend-desc">≥ 4 flagged, OR (≥ 3 flagged AND ≥ 2 watch). Immediate escalation required.</span>
  </div>
  <div class="legend-row">
    <span class="status-badge severity-high">HIGH</span>
    <span class="legend-desc">3 flagged, OR (2 flagged AND ≥ 3 watch). Active credit review needed.</span>
  </div>
  <div class="legend-row">
    <span class="status-badge severity-watch">AMBER</span>
    <span class="legend-desc">1-2 flagged, OR (0 flagged AND ≥ 4 watch). Elevated monitoring.</span>
  </div>
  <div class="legend-row">
    <span class="status-badge severity-monitor">GREEN</span>
    <span class="legend-desc">0 flagged AND ≤ 3 watch. Standard monitoring cadence.</span>
  </div>
  <div class="legend-footnote">Status is computed deterministically after every run from the 15-flag framework. Full methodology in the Methodology tab.</div>
</div>

<div class="pane active" id="pane-overview">
<table class="overview-table">
<colgroup>
<col style="width:14%"><col style="width:7%"><col style="width:9%"><col style="width:14%"><col style="width:11%"><col style="width:36%"><col style="width:9%">
</colgroup>
<thead><tr>
  <th data-type="text">Company</th><th data-type="text">Status</th><th data-type="num">Flags</th>
  <th data-type="text">Ratings (M/S/F)</th><th data-type="date">Last Action</th>
  <th data-type="text">Key Development</th><th data-type="text">Action</th>
</tr></thead>
<tbody>{"".join(overview_rows)}</tbody>
</table>
</div>

<div class="pane" id="pane-sectors">{snapshot_html}</div>

<div class="pane" id="pane-market">
<table>
<colgroup>
<col style="width:13%"><col style="width:9%"><col style="width:8%"><col style="width:8%"><col style="width:6%"><col style="width:7%"><col style="width:7%"><col style="width:7%"><col style="width:7%"><col style="width:8%"><col style="width:8%"><col style="width:12%">
</colgroup>
<thead><tr>
  <th data-type="text">Company</th><th data-type="text">Sector</th>
  <th data-type="num">Mkt Cap $Bn</th><th data-type="num">EV $Bn</th>
  <th data-type="text">Status</th><th data-type="num">Price $</th>
  <th data-type="num">1D %</th><th data-type="num">1M %</th><th data-type="num">YTD %</th><th data-type="num">1Y %</th>
  <th data-type="num">52W High</th><th data-type="num">52W Low</th>
  <th data-type="date">Next Earnings</th>
</tr></thead>
<tbody>{"".join(market_rows)}</tbody>
</table>
</div>

<div class="pane" id="pane-financials">
<div class="fin-intro" style="padding:14px 28px;color:#7090a8;font-size:11px;font-style:italic;border-bottom:1px solid #1e2a3a;background:#0d1117">
  Click any row to expand historical financial detail (3 fiscal years plus LTM). SEC EDGAR sourced names show the &#9656; arrow; non-SEC filers show a static dot.
</div>
<table>
<colgroup>
<col style="width:18%"><col style="width:9%"><col style="width:7%"><col style="width:9%"><col style="width:8%"><col style="width:8%"><col style="width:8%"><col style="width:8%"><col style="width:9%"><col style="width:8%"><col style="width:8%">
</colgroup>
<thead><tr>
  <th data-type="text">Company</th><th data-type="text">Sector</th><th data-type="text">Status</th>
  <th data-type="num">Revenue (LTM)</th><th data-type="num">Growth YoY</th>
  <th data-type="num">Net Leverage</th><th data-type="num">EBITDA Margin</th>
  <th data-type="num">Op Margin</th><th data-type="num">FCF (LTM)</th>
  <th data-type="num">Cash</th><th data-type="num">Total Debt</th>
</tr></thead>
<tbody>{"".join(fin_combined_rows)}</tbody>
</table>
</div>

<div class="pane" id="pane-tmt">
{tmt_tab_html}
</div>

<div class="pane" id="pane-redflags">
<div class="rf-legend">
  <div class="rf-legend-item"><span class="rf-pill rf-flagged">&#9888;</span> Flagged (threshold breached)</div>
  <div class="rf-legend-item"><span class="rf-pill rf-watch">~</span> Watch (approaching threshold)</div>
  <div class="rf-legend-item"><span class="rf-pill rf-clear">&#10003;</span> Clear</div>
  <div class="rf-legend-item"><span class="rf-pill rf-na">&mdash;</span> N/A (data unavailable)</div>
  <div class="rf-legend-note"><strong>Hover any flag cell</strong> to see flag name, data source (SEC EDGAR / yfinance / Claude), the specific value that fired, and both flagged and watch thresholds. See Methodology tab for full flag definitions.</div>
</div>
<table class="rf-table">
<thead><tr>
  <th data-type="text">Company</th><th data-type="text">Sector</th><th data-type="text">Status</th>
  {rf_headers}<th data-type="num">Total</th>
</tr></thead>
<tbody>{"".join(redflag_rows_list)}</tbody>
</table>
</div>

<div class="pane" id="pane-macro">{macro_tab_html}</div>

<div class="pane" id="pane-methodology">
<div class="methodology-content">
  <h2>Refresh Schedule</h2>
  <p>The dashboard runs automatically Monday through Friday at 7:55 AM ET (set 5 minutes off the hour to avoid GitHub Actions cron congestion). Two refresh modes balance data freshness with API cost:</p>
  <table class="methodology-table">
    <tr><th>Refresh</th><th>When</th><th>What Refreshes</th><th>What's Cached</th></tr>
    <tr><td><strong>WEEKLY</strong></td><td>Friday morning, or any day if cache is &gt; 10 days stale, or manually triggered</td><td>All Claude data (Batches A+B + second-pass), all market data, all SEC EDGAR, all macro</td><td>Writes claude_cache.json for the week</td></tr>
    <tr><td><strong>DAILY</strong></td><td>Monday through Thursday</td><td>Market data (yfinance), macro (FRED), data center construction, plus targeted Claude news refresh ONLY for amber/red names</td><td>Reuses Claude ratings + news from last Friday for green names</td></tr>
  </table>
  <p><strong>Why this design</strong>: ratings change quarterly at most, news changes daily for stressed names but rarely for stable green names. Refreshing everything daily wastes API budget. The daily refresh keeps the dashboard fresh on metrics that matter daily (stock prices, macro, news for at-risk names) while preserving cache for stable items. Cost: roughly $60-80/month sustained, vs $150+ daily-weekly equivalent.</p>
  <p><strong>Manual trigger</strong>: any time, via the GitHub Actions tab. Defaults to auto mode (weekly on Friday, daily otherwise), with the option to force weekly or daily refresh. Manual weekly refreshes cost ~$5-7; daily refreshes cost ~$1.50.</p>
  <p><strong>Override files</strong> (<code>ratings_override.json</code> and <code>news_override.json</code>) are applied on every run regardless of refresh mode, so manually entered data appears immediately. These files allow manual injection of credit-relevant news or rating actions when automated sources miss something material.</p>

  <h2>Quick Reference</h2>
  <p>Status across every tab is driven by one source of truth: the 15-flag red flag framework. Each flag has explicit numerical thresholds. The combined count of FLAGGED + WATCH per name determines its tier.</p>
  <table class="methodology-table">
    <tr><th>Tier</th><th>Trigger</th><th>Action</th></tr>
    <tr><td><span class="status-badge severity-critical">CRITICAL</span></td><td>&ge; 4 flagged, OR (&ge; 3 flagged AND &ge; 2 watch)</td><td>Escalate</td></tr>
    <tr><td><span class="status-badge severity-high">HIGH</span></td><td>3 flagged, OR (2 flagged AND &ge; 3 watch)</td><td>Review</td></tr>
    <tr><td><span class="status-badge severity-watch">AMBER</span></td><td>1-2 flagged, OR (0 flagged AND &ge; 4 watch)</td><td>Watch</td></tr>
    <tr><td><span class="status-badge severity-monitor">GREEN</span></td><td>0 flagged AND &le; 3 watch</td><td>Monitor</td></tr>
  </table>
  <p><strong>Note on methodology change</strong>: prior versions of this dashboard used a separate concern_score (0-100 composite) from Claude. As of May 2026, status is driven purely by the 15-flag framework for consistency across all tabs and to align with auditable credit officer practice. See Red Flags Framework section below for the 15 flag definitions.</p>

  <h2>Status Definitions (detailed)</h2>
  <p>Each row's status badge and corresponding action button are computed after every run from the 15-flag count. Tiers are mutually exclusive: a name belongs to exactly one tier.</p>
  <table class="methodology-table">
    <tr><th>Tier</th><th>Description</th><th>Threshold</th></tr>
    <tr><td><span class="status-badge severity-critical">CRITICAL</span></td><td>Immediate credit committee attention required. Significant or compounding credit deterioration across multiple categories.</td><td>4+ hard flags, OR 3+ hard + 2+ watch</td></tr>
    <tr><td><span class="status-badge severity-high">HIGH</span></td><td>Active credit review needed within current cycle. Pattern of credit stress emerging.</td><td>3 hard flags, OR 2 hard + 3+ watch</td></tr>
    <tr><td><span class="status-badge severity-watch">AMBER</span></td><td>Elevated monitoring. Single material concern, or multiple early warnings.</td><td>1-2 hard flags, OR 0 hard + 4+ watch</td></tr>
    <tr><td><span class="status-badge severity-monitor">GREEN</span></td><td>Standard monitoring cadence. No or minimal credit stress signals.</td><td>0 hard flags AND 0-3 watch flags</td></tr>
  </table>

  <h2>Financial Metric Definitions</h2>
  <p>All metrics are LTM (Last Twelve Months) unless explicitly labeled FY. All dollar figures in $Bn unless noted.</p>
  <table class="methodology-table">
    <tr><th>Metric</th><th>Definition</th><th>Source</th></tr>
    <tr><td><strong>Revenue (LTM)</strong></td><td>Sum of four most recent non-overlapping quarterly Revenue observations. For 20-F foreign filers, the latest annual filing.</td><td>SEC EDGAR XBRL <code>Revenues</code> or fallback chain</td></tr>
    <tr><td><strong>Growth YoY</strong></td><td>Current LTM Revenue divided by prior-year LTM Revenue, minus one. Compares 4 most recent quarters against the 4 preceding non-overlapping quarters.</td><td>Derived from Revenue history</td></tr>
    <tr><td><strong>EBITDA</strong></td><td>Built bottom-up: Operating Income (from income statement) + Depreciation &amp; Amortization (sourced from the cash flow statement, since the income statement often does not break out D&amp;A separately). LTM basis.</td><td>SEC EDGAR <code>OperatingIncomeLoss</code> + <code>DepreciationDepletionAndAmortization</code> (CFS)</td></tr>
    <tr><td><strong>EBITDA Margin</strong></td><td>EBITDA divided by Revenue, expressed as percent.</td><td>Derived</td></tr>
    <tr><td><strong>FCF (Free Cash Flow)</strong></td><td>GAAP unlevered FCF: Cash from Operations (CFO) minus absolute value of Capital Expenditures. LTM basis. This is the standard credit-analyst definition; not adjusted for working capital or capitalized leases.</td><td>SEC EDGAR <code>NetCashProvidedByUsedInOperatingActivities</code> &minus; <code>PaymentsToAcquirePropertyPlantAndEquipment</code></td></tr>
    <tr><td><strong>Cash</strong></td><td>Cash &amp; cash equivalents at most recent reporting date.</td><td>SEC EDGAR <code>CashAndCashEquivalentsAtCarryingValue</code></td></tr>
    <tr><td><strong>Long-Term Debt</strong></td><td>Non-current portion of total debt at most recent reporting date. Tag chain walks 15 candidates including capital lease obligations, senior notes, secured/unsecured debt, mortgages payable.</td><td>SEC EDGAR fallback chain (15 candidate tags)</td></tr>
    <tr><td><strong>Short-Term Debt</strong></td><td>Current portion of long-term debt + commercial paper + short-term borrowings. Tag chain walks 8 candidates.</td><td>SEC EDGAR fallback chain</td></tr>
    <tr><td><strong>Total Debt</strong></td><td>Long-Term Debt + Short-Term Debt. For names where SEC EDGAR returns no debt data (20-F filers, unusual tag structures), falls back to yfinance balance sheet.</td><td>SEC EDGAR primary, yfinance fallback</td></tr>
    <tr><td><strong>Net Debt</strong></td><td>Total Debt minus Cash.</td><td>Derived</td></tr>
    <tr><td><strong>Net Leverage (ND/EBITDA)</strong></td><td>Net Debt divided by LTM EBITDA. The standard rating-agency leverage measure. Investment-grade typically below 3.0x. &gt;5.0x is the Red Flag threshold. Shown as n/a when Net Debt is negative (cash exceeds debt) or EBITDA is zero/negative.</td><td>Derived</td></tr>
    <tr><td><strong>Interest Coverage</strong></td><td>EBITDA divided by LTM Interest Expense.</td><td>SEC EDGAR <code>InterestExpense</code> + derived</td></tr>
  </table>

  <h2>Market Data Definitions</h2>
  <table class="methodology-table">
    <tr><th>Metric</th><th>Definition</th><th>Source</th></tr>
    <tr><td><strong>Market Cap</strong></td><td>Current share price times shares outstanding. From yfinance fast_info.</td><td>yfinance</td></tr>
    <tr><td><strong>EV (Enterprise Value)</strong></td><td>Market Cap + Total Debt - Cash. The theoretical takeover price: what an acquirer would pay equity holders plus assume in debt, less captured cash. Shown as n/a when any of the three inputs is missing.</td><td>Derived</td></tr>
    <tr><td><strong>1D / 1M / YTD / 1Y %</strong></td><td>Total return percentage change from previous close, 22 trading days back, start of calendar year, and 252 trading days back respectively. Negative values shown in red, positive in green.</td><td>yfinance</td></tr>
    <tr><td><strong>52W High / Low</strong></td><td>Highest and lowest adjusted close over trailing 252 trading days. Each cell shows the price plus a context % indicating how far current price is from that level: 52W High shows "% below high" (red if &gt; 10% below), 52W Low shows "% above low" (green if &gt; 20% above).</td><td>yfinance</td></tr>
  </table>

  <h2>Data Source Tags</h2>
  <p>Each financials row is tagged with its source. Tags appear next to the company name on the Financials and TMT tabs.</p>
  <ul>
    <li><span class="src-tag sec">SEC</span> Pulled from SEC EDGAR XBRL company facts API. Authoritative, audited filings.</li>
    <li><span class="src-tag claude">EST</span> Sourced from Claude web search. Used only when SEC EDGAR data is unavailable. Less reliable.</li>
    <li><span class="src-tag claude">YF</span> Fallback for Total Debt from yfinance balance sheet when SEC EDGAR returns no debt fields. Used for non-SEC filers (Nissan, Imperial Brands) and some 20-F foreign filers.</li>
  </ul>
  <p>Warning icon (<span class="data-warn">&#9888;</span>) next to a company name indicates SEC EDGAR returned a validation warning (stale period, unusual ratio, or missing field). Hover for details.</p>

  <h2>Financials Tab</h2>
  <p>Summary row shows LTM metrics. Click any row with a &#9656; to expand historical detail showing the last 3 fiscal years plus LTM. Income Statement &amp; Cash Flow plus Capital Structure tables with YoY and trend columns. Historical years are reconstructed from quarterly XBRL data by summing 4 non-overlapping quarters ending at each fiscal year-end.</p>

  <h2>TMT Tab</h2>
  <p>Sector deep-dive with four chart layers and five subsection tables, top to bottom:</p>
  <ul>
    <li><strong>US Data Center Construction</strong>: monthly dollar value of private data center construction put in place in the US. Sourced from the US Census Bureau Value of Construction Put in Place (VIP) report via Our World in Data. The number represents the dollar value of construction work performed during the month (materials installed, labor performed) on private-sector data center projects nationwide. Includes new construction, additions, alterations, and major replacements; excludes maintenance and government-owned projects. Values are inflation-adjusted to constant 2021 US dollars using BLS Producer Price Index for new office building construction. Reported in millions of dollars per month. Lagged approximately 6 weeks (the May release covers March data). Chart shows monthly level and month-over-month change. KPI tiles show latest value, YoY %, 3-month average MoM change, and 5-year cumulative growth. <em>Why it matters for credit:</em> this is the macro demand signal for the entire data center buildout cycle. Rising values mean more physical construction; flattening values would signal cycle deceleration before it shows in hyperscaler earnings.</li>
    <li><strong>Hyperscaler CapEx (Stacked, Quarterly)</strong>: quarterly CapEx for Microsoft, Alphabet, Amazon, and Oracle going back up to 16 quarters. Bars synchronize on calendar quarter end. <em>Public-company supply commitment, quarterly cadence to surface inflection points.</em></li>
    <li><strong>Hyperscaler Revenue Backlog (RPO)</strong>: quarterly Remaining Performance Obligation for hyperscalers, last 8 quarters. Pulled from SEC EDGAR XBRL <code>RevenueRemainingPerformanceObligation</code> and <code>RemainingPerformanceObligation</code> tags. <em>Contracted demand: revenue under signed contracts but not yet recognized. Forward demand signal.</em> Amazon may be excluded from the chart because AWS RPO is not separately tagged in SEC XBRL filings; including their broader ContractWithCustomerLiability would mix Prime memberships and gift card balances with AWS commercial backlog. Names with no RPO disclosure are noted in the chart subtitle.</li>
    <li><strong>Five subsection tables</strong>: Hyperscalers, Data Center &amp; Tower REITs, Telecom, Hardware &amp; EMS, Software/Payments/Services. Filter pills (Red/Amber/Green) apply across all subsections.</li>
  </ul>
  <p><strong>How the three charts work together</strong>: data center construction shows what's being physically built. Hyperscaler CapEx shows the public-company portion of that spend. RPO shows the contracted demand that buildout is serving. Rising construction and CapEx with rising RPO is a healthy expansion. Rising construction and CapEx with flat or falling RPO is the classic overbuild signal.</p>

  <h2>Red Flags Framework (15 Flags)</h2>
  <p>Universal 15-flag framework, 11 deterministically computed each run, 4 pending future data sources. The heat map renders all 15 columns with pending flags shown as N/A so the framework is honest about coverage.</p>
  <table class="methodology-table">
    <tr><th>#</th><th>Flag</th><th>Threshold</th><th>Watch</th><th>Source</th><th>Status</th></tr>
    <tr><td>1</td><td>Leverage Too High</td><td>ND/EBITDA &gt; 5.0x</td><td>&gt; 4.0x</td><td>SEC EDGAR</td><td>Computed</td></tr>
    <tr><td>2</td><td>Leverage Climbing</td><td>ND/EBITDA +1.0x YoY</td><td>+0.5x</td><td>SEC EDGAR history</td><td>Computed</td></tr>
    <tr><td>3</td><td>Coverage Thin</td><td>EBITDA/Interest &lt; 3.0x</td><td>&lt; 4.5x</td><td>SEC EDGAR</td><td>Computed</td></tr>
    <tr><td>4</td><td>Burning Cash</td><td>FCF negative 2 quarters</td><td>1 quarter</td><td>SEC EDGAR history</td><td>Computed</td></tr>
    <tr><td>5</td><td>Wall of Maturities</td><td>&gt;20% of debt as current portion</td><td>&gt;10%</td><td>SEC EDGAR (ST debt / Total debt)</td><td>Computed</td></tr>
    <tr><td>6</td><td>Refi at Higher Rates</td><td>Avg coupon to refi &gt;150bps above current</td><td>&gt;75bps</td><td>Bond coupon data</td><td>Pending</td></tr>
    <tr><td>7</td><td>Revenue Shrinking</td><td>Rev YoY &lt; -5%</td><td>&lt; -2%</td><td>SEC EDGAR</td><td>Computed</td></tr>
    <tr><td>8</td><td>Margin Compression</td><td>EBITDA margin -300bps YoY</td><td>-150bps</td><td>SEC EDGAR history</td><td>Computed</td></tr>
    <tr><td>9</td><td>Stock Collapse</td><td>YTD &lt; -25%</td><td>&lt; -15%</td><td>yfinance</td><td>Computed</td></tr>
    <tr><td>10</td><td>Rating Pressure</td><td>2+ Negative outlooks</td><td>1 negative</td><td>Ratings + override</td><td>Computed</td></tr>
    <tr><td>11</td><td>Bad News in Filings</td><td>Trigger phrases in key dev</td><td>Watch phrases</td><td>Claude synthesis</td><td>Computed</td></tr>
    <tr><td>12</td><td>Liquidity Squeeze</td><td>Cash / ST Debt &lt; 1.0x</td><td>&lt; 1.5x</td><td>SEC EDGAR</td><td>Computed</td></tr>
    <tr><td>13</td><td>Going Concern</td><td>Auditor going concern qualification</td><td>Substantial doubt language</td><td>10-K auditor opinion text</td><td>Pending</td></tr>
    <tr><td>14</td><td>Insider Selling</td><td>Large insider sales 90d (&gt;$10MM or &gt;5% shares)</td><td>&gt;$5MM</td><td>Form 4 filings</td><td>Pending</td></tr>
    <tr><td>15</td><td>Geographic Risk</td><td>Material unhedged sanctioned/conflict exposure</td><td>Single-country &gt;25% revenue</td><td>10-K risk factors text</td><td>Pending</td></tr>
  </table>
  <p><strong>Why 4 flags are pending:</strong> Flag 6 requires bond-level coupon data outside the SEC XBRL companyfacts schema. Flags 13, 15 require text-extraction from 10-K filings (auditor opinion section, risk factors section), which is a separate pipeline. Flag 14 requires parsing Form 4 insider transactions, which is a different SEC API endpoint. The architecture leaves these as N/A placeholders rather than guessing; we can wire them in future iterations using either a manual override file (for known cases) or dedicated text-extraction passes.</p>
  <p><strong>Sign-off tier mapping:</strong> 0 flags = Comfortable. 1-2 flags = Watch. 3-4 flags = Review. 5+ flags = Escalate. Watch states accumulate separately; 3+ watch states alone elevate to Watch tier.</p>

  <h2>Macro Indicators</h2>
  <p>HY OAS, IG OAS, 10Y UST, and 2Y UST in the header strip pull directly from FRED. Spreads converted from percent to basis points for the header tile. The Macro tab displays the same FRED observations in their native percent format with category groupings (Rates, Spreads, Inflation, Labor, Activity).</p>

  <h2>Data Sources</h2>
  <table class="methodology-table">
    <tr><th>Source</th><th>Purpose</th><th>Cache TTL</th></tr>
    <tr><td>SEC EDGAR</td><td>Financial metrics for SEC filers</td><td>6 days</td></tr>
    <tr><td>yfinance</td><td>Market data, stock returns, Total Debt fallback</td><td>None (live every run)</td></tr>
    <tr><td>FRED</td><td>Macro indicators (19 series across rates, spreads, inflation, labor, activity)</td><td>20 hours</td></tr>
    <tr><td>Our World in Data</td><td>US data center construction spending (mirrors Census Bureau VIP + BLS PPI)</td><td>24 hours</td></tr>
    <tr><td>Anthropic Claude</td><td>Ratings, news, earnings dates, key developments, Top 3</td><td>None (live every run)</td></tr>
  </table>

  <h2>Refresh Cadence</h2>
  <ul>
    <li>Workflow runs daily at 8:00 AM ET on weekdays (cron schedule). Can be triggered manually via the Actions tab.</li>
    <li>Daily refresh: market data + commodities + indices (yfinance), ratings + news + Top 3 (Claude), FRED macro, data center construction (Our World in Data).</li>
    <li>Weekly refresh: SEC EDGAR financials (TTL 6 days). Delete <code>financials_cache.json</code> to force a refresh.</li>
    <li>Each run logs to <code>runs.json</code> with full diagnostics. Keep last 60 runs.</li>
  </ul>
</div>
</div>

<footer>
  <h3>&#9650; Top 3 Names Requiring Attention</h3>
  <ol>{top3_html}</ol>
</footer>
<script>{js}</script>
</body>
</html>"""


def second_pass_news(all_rows):
    """
    For names with status=amber/red that currently show "No material news.",
    do a targeted second-pass Claude search to surface credit-relevant events.

    The first-pass Batch A/B prompts cover 44 + 38 names. With ~25 web searches
    available per batch, Claude has limited search budget per name. Names where
    the search returned empty often have material news that just wasn't found.

    This pass re-queries Claude with a focused prompt for ONLY the names that
    need it. Maximum 15 names per call to keep search budget per name high.
    """
    candidates = []
    for r in all_rows:
        status = str(r.get('status', '')).lower()
        if status not in ('amber', 'red'):
            continue
        key_dev = str(r.get('key_dev', '') or '').strip().lower()
        if key_dev in ('', 'no material news.', 'no material news', 'n/a'):
            candidates.append(r.get('company', ''))

    if not candidates:
        print("Second-pass news: no amber/red names with empty key_dev; skipping.")
        return all_rows

    # Cap at 15 to keep per-name search budget meaningful (25 searches / 15 names = ~1.7 per)
    candidates = candidates[:15]
    print(f"Second-pass news: re-querying {len(candidates)} amber/red names with empty key_dev: {', '.join(candidates)}")

    names_str = '\n'.join(f"- {co}" for co in candidates)
    prompt = f"""Today is {datetime_str}. You are a credit analyst finding material credit-relevant news for specific companies that another search missed.

Companies to research:
{names_str}

For EACH company, search the web for material credit events in the last 60 days. Look hard for:
1. Rating actions: upgrades, downgrades, outlook changes, ratings affirmed with comments (Moody's, S&P, Fitch press releases)
2. Capital structure: spin-offs, M&A, acquisitions, divestitures, debt issuance, refinancing, dividend changes, buybacks
3. Financial events: covenant amendments, defaults, missed payments, going concern, restatements
4. Strategic: management changes, restructuring, contract wins/losses, strategic reviews
5. Earnings: beats, misses, guidance changes, withdrawn guidance, especially recent quarterly earnings
6. Legal/Regulatory: SEC investigations, material litigation, penalties

If a company TRULY has no material credit-relevant news in the last 60 days, return "No material news." for that company. But search harder than a typical search - check 8-K filings, earnings press releases, agency websites, financial press. Multiple search queries per company are encouraged.

Search query patterns to use:
- "[Company] earnings Q1 2026 OR Q4 2025"
- "[Company] credit rating action 2026"
- "[Company] 8-K filing material event 2026"
- "[Company] acquisition OR divestiture OR spin-off 2026"

OUTPUT FORMAT: Your ENTIRE response must be ONLY a single JSON object. Start with {{ as the very first character. End with }} as the very last character. NO preamble, NO markdown, NO explanation.

{{"updates": [{{"company": "Exact Company Name", "key_dev": "1-2 sentences, under 200 characters, citing the specific event with date"}}]}}

Rules:
- Include every company in the input list; if truly no news, set key_dev to "No material news."
- key_dev must be SPECIFIC: cite dates, dollar amounts, percentages where applicable
- Use the EXACT company name as provided in the input list
- Public information only"""

    try:
        raw = call_claude(prompt, "Second-pass news")
        data, err = parse_json(raw, "Second-pass news")
        if err or not data:
            print(f"Second-pass news: parse error, skipping. Detail: {err}")
            return all_rows
        updates = data.get('updates', [])
        if not updates:
            print("Second-pass news: response had no updates list.")
            return all_rows
        updated_count = 0
        name_to_update = {u.get('company', '').strip(): u.get('key_dev', '') for u in updates}
        for r in all_rows:
            co = r.get('company', '')
            if co in name_to_update:
                new_dev = name_to_update[co]
                if new_dev and new_dev.lower() not in ('no material news.', 'no material news', 'n/a', ''):
                    r['key_dev'] = new_dev
                    updated_count += 1
        print(f"Second-pass news: updated {updated_count} of {len(candidates)} candidates with new material developments.")
    except Exception as e:
        print(f"Second-pass news: exception during call, skipping. Detail: {str(e)[:200]}")
    return all_rows


def main():
    run_start = datetime.now(pytz.utc)

    # Decide run mode (full vs cheap) based on day-of-week and cache freshness
    run_mode = determine_run_mode()

    if run_mode == "full":
        # FULL MODE: Refresh Claude Batches A through E from scratch
        raw_a = call_claude(PROMPT_A, "Batch A")
        raw_b = call_claude(PROMPT_B, "Batch B")
        raw_c = call_claude(PROMPT_C, "Batch C")
        raw_d = call_claude(PROMPT_D, "Batch D")
        raw_e = call_claude(PROMPT_E, "Batch E")

        data_a, err_a = parse_json(raw_a, "Batch A")
        data_b, err_b = parse_json(raw_b, "Batch B")
        data_c, err_c = parse_json(raw_c, "Batch C")
        data_d, err_d = parse_json(raw_d, "Batch D")
        data_e, err_e = parse_json(raw_e, "Batch E")

        if err_a: print(f"WARNING: {err_a}")
        if err_b: print(f"WARNING: {err_b}")
        if err_c: print(f"WARNING: {err_c}")
        if err_d: print(f"WARNING: {err_d}")
        if err_e: print(f"WARNING: {err_e}")

        rows_a = data_a.get('rows', []) if data_a else []
        rows_b = data_b.get('rows', []) if data_b else []
        rows_c = data_c.get('rows', []) if data_c else []
        rows_d = data_d.get('rows', []) if data_d else []
        rows_e = data_e.get('rows', []) if data_e else []
        all_rows = rows_a + rows_b + rows_c + rows_d + rows_e
        # Macro and top3 come from Batch E (the final batch carries these payloads)
        macro = (data_e or {}).get('macro', {}) or {}
        top3 = (data_e or {}).get('top3', []) or []
        print(f"Full mode batch totals: A={len(rows_a)} B={len(rows_b)} C={len(rows_c)} D={len(rows_d)} E={len(rows_e)} | Total={len(all_rows)}")
    else:
        # CHEAP MODE: Load cached Claude output from last full run
        cached_rows, cached_macro, cached_top3, last_refresh = load_claude_cache()
        if not cached_rows:
            # Fail-safe: cache load failed unexpectedly, fall back to full mode
            print("WARNING: cheap-mode cache load failed, escalating to full mode")
            run_mode = "full"
            raw_a = call_claude(PROMPT_A, "Batch A")
            raw_b = call_claude(PROMPT_B, "Batch B")
            raw_c = call_claude(PROMPT_C, "Batch C")
            raw_d = call_claude(PROMPT_D, "Batch D")
            raw_e = call_claude(PROMPT_E, "Batch E")
            data_a, err_a = parse_json(raw_a, "Batch A")
            data_b, err_b = parse_json(raw_b, "Batch B")
            data_c, err_c = parse_json(raw_c, "Batch C")
            data_d, err_d = parse_json(raw_d, "Batch D")
            data_e, err_e = parse_json(raw_e, "Batch E")
            if err_a: print(f"WARNING: {err_a}")
            if err_b: print(f"WARNING: {err_b}")
            if err_c: print(f"WARNING: {err_c}")
            if err_d: print(f"WARNING: {err_d}")
            if err_e: print(f"WARNING: {err_e}")
            rows_a = data_a.get('rows', []) if data_a else []
            rows_b = data_b.get('rows', []) if data_b else []
            rows_c = data_c.get('rows', []) if data_c else []
            rows_d = data_d.get('rows', []) if data_d else []
            rows_e = data_e.get('rows', []) if data_e else []
            all_rows = rows_a + rows_b + rows_c + rows_d + rows_e
            macro = (data_e or {}).get('macro', {}) or {}
            top3 = (data_e or {}).get('top3', []) or []
        else:
            all_rows = cached_rows
            macro = cached_macro
            top3 = cached_top3
            rows_a = []
            rows_b = []
            print(f"Cheap mode: reusing {len(all_rows)} rows from cache; skipping Batches A+B (saved ~$3-5)")

    all_rows = apply_overrides(all_rows)

    # Normalize Claude-expanded company names back to WATCHLIST keys so SEC EDGAR,
    # yfinance, and override matches don't silently fail on name mismatches.
    all_rows = _normalize_company_names(all_rows, WATCHLIST)

    sec_metadata = {"from_cache": False, "names_succeeded": 0, "names_attempted": 0}
    sec_warnings = []
    sec_data = {}
    if SEC_EDGAR_AVAILABLE:
        sec_data, sec_warnings, sec_metadata = sec_edgar.fetch_financials(WATCHLIST)
        all_rows = sec_edgar.apply_sec_overrides(all_rows, sec_data)

    # yfinance balance-sheet fallback for names where SEC EDGAR returned no total_debt
    all_rows = fetch_yfinance_balance_sheet_fallback(all_rows, sec_data, WATCHLIST)

    market_data = fetch_market_data()
    all_rows = apply_market_overrides(all_rows, market_data)

    commodities = fetch_commodities_fx()

    fred_metadata = {"from_cache": False, "series_succeeded": 0, "series_attempted": 0, "series_failed": []}
    fred_warnings = []
    fred_data = {}
    if FRED_AVAILABLE:
        print("Calling FRED for macro economic data...")
        fred_data, fred_warnings, fred_metadata = fred.fetch_macro_data(
            cache_path="macro_cache.json",
            force_refresh=False,
        )
        print(f"FRED: {fred_metadata.get('series_succeeded',0)}/{fred_metadata.get('series_attempted',0)} series succeeded")

    census_metadata = {"from_cache": False, "rows_returned": 0}
    census_warnings = []
    census_data = {}
    if CENSUS_AVAILABLE:
        print("Calling Census Bureau for data center construction...")
        census_data, census_warnings, census_metadata = census_construction.fetch_data_center_construction(
            cache_path="data_center_cache.json",
            force_refresh=False,
        )
        print(f"Census: {census_metadata.get('rows_returned', 0)} monthly observations")

    # Pipeline reordering for flag-driven status:
    # 1. Apply provisional status from Claude (existing rows already have status field)
    # 2. Run news refresh based on provisional status (so amber/red names get fresh news)
    # 3. Save cache if full mode (preserves Claude output even before reclassification)
    # 4. Evaluate 15-flag framework (needs key_dev for Flag 11, financials for others)
    # 5. Recompute final status from flag count (overrides Claude's provisional)
    # 6. Build HTML with final status

    # Mode-specific news refresh (uses provisional status from Claude)
    if run_mode == "full":
        # Second-pass news search for amber/red names that returned "No material news"
        all_rows = second_pass_news(all_rows)
        # Save Claude output to cache for cheap-mode days to reuse
        save_claude_cache(all_rows, macro, top3)
    else:
        # Cheap mode: targeted news refresh ONLY for amber/red names
        all_rows = cheap_mode_news_refresh(all_rows)

    # Evaluate 15-flag framework (the canonical credit stress model)
    flag_summary = None
    if RED_FLAGS_AVAILABLE:
        all_rows, flag_summary = red_flags.evaluate_flags(all_rows, sec_data)
        flagged_co = sum(1 for r in all_rows if r.get('_flag_count', 0) >= 1)
        print(f"Red Flags: {flag_summary['total_flagged_triggers']} total flagged triggers across {flagged_co} companies")

    # Recompute status from flag count (replaces concern_score-driven logic)
    all_rows = compute_status_from_flags(all_rows)

    # Recompute top3 based on flag count (deterministic, no longer Claude's judgment)
    sorted_for_top3 = sorted(
        all_rows,
        key=lambda r: (
            -int(r.get('_flag_count', 0) or 0),
            -int(r.get('_watch_count', 0) or 0),
            r.get('company', '')
        )
    )
    top3 = []
    for r in sorted_for_top3[:3]:
        co = r.get('company', '')
        flag_count = int(r.get('_flag_count', 0) or 0)
        watch_count = int(r.get('_watch_count', 0) or 0)
        key_dev = r.get('key_dev', 'No material news.')
        # Truncate key_dev to fit
        if len(key_dev) > 180:
            key_dev = key_dev[:177] + "..."
        note = f"{flag_count} flagged + {watch_count} watch. {key_dev}"
        top3.append({"name": co, "note": note})

    print(f"Run mode: {run_mode} | Batch A: {len(rows_a)} rows, Batch B: {len(rows_b)} rows, Total: {len(all_rows)}")

    html = build_html(all_rows, macro, top3, datetime_str, commodities, fred_data, sec_data, census_data, run_mode)

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print("index.html written successfully.")

    if RUN_LOG_AVAILABLE:
        run_end = datetime.now(pytz.utc)
        red_count = sum(1 for r in all_rows if str(r.get('status','')).lower()=='red')
        amber_count = sum(1 for r in all_rows if str(r.get('status','')).lower()=='amber')
        green_count = sum(1 for r in all_rows if str(r.get('status','')).lower()=='green')
        log_entry = {
            "run_id": now.strftime("%Y-%m-%d-%H%M"),
            "run_started": run_start.isoformat(),
            "run_completed": run_end.isoformat(),
            "duration_seconds": int((run_end - run_start).total_seconds()),
            "data_sources": {
                "anthropic_claude": {
                    "model": "claude-sonnet-4-6",
                    "calls": (5 if run_mode == "full" else 1),
                    "run_mode": run_mode,
                    "batches_succeeded": (
                        ((1 if (locals().get("data_a")) else 0) +
                         (1 if (locals().get("data_b")) else 0) +
                         (1 if (locals().get("data_c")) else 0) +
                         (1 if (locals().get("data_d")) else 0) +
                         (1 if (locals().get("data_e")) else 0))
                        if run_mode == "full" else "n/a (cheap mode, cache reused)"
                    ),
                },
                "sec_edgar": {
                    "from_cache": sec_metadata.get("from_cache", False),
                    "names_attempted": sec_metadata.get("names_attempted", 0),
                    "names_succeeded": sec_metadata.get("names_succeeded", 0),
                    "names_failed": sec_metadata.get("names_failed", []),
                    "names_no_sec_filer": sec_metadata.get("names_no_sec_filer", []),
                    "total_warnings": sec_metadata.get("total_warnings", 0),
                },
                "yfinance": {
                    "market_data_companies": len(market_data) if market_data else 0,
                    "commodities_indices": len(commodities) if commodities else 0,
                },
                "fred": {
                    "from_cache": fred_metadata.get("from_cache", False),
                    "series_attempted": fred_metadata.get("series_attempted", 0),
                    "series_succeeded": fred_metadata.get("series_succeeded", 0),
                    "series_failed": fred_metadata.get("series_failed", []),
                    "warnings": fred_warnings[:20],
                },
                "census": {
                    "from_cache": census_metadata.get("from_cache", False),
                    "rows_returned": census_metadata.get("rows_returned", 0),
                    "warnings": census_warnings[:5],
                },
            },
            "overrides_applied": {
                "ratings_override": sum(1 for k in RATINGS_OVERRIDE if not k.startswith('_')),
            },
            "validation_warnings": sec_warnings[:50],
            "output": {
                "total_rows": len(all_rows),
                "red_count": red_count,
                "amber_count": amber_count,
                "green_count": green_count,
                "html_bytes": len(html),
            },
        }
        run_log.append_run_log(log_entry, path="runs.json", keep_last=60)


if __name__ == '__main__':
    main()
