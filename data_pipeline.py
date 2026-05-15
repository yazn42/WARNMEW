import pandas as pd
import numpy as np
import os
import re
import glob
from datetime import datetime, timedelta
import warnings
import logging
import requests
import time
from pytrends.request import TrendReq

# Configure logging
logging.basicConfig(
    filename='pipeline.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

# --- Configuration ---
EXCEL_DIR = "excel_files"
OUTPUT_FILE = "warnmew_training_dataset.csv"

# Kerala Districts (14)
DISTRICTS = [
    "Thiruvananthapuram", "Kollam", "Pathanamthitta", "Alappuzha", "Kottayam", 
    "Idukki", "Ernakulam", "Thrissur", "Palakkad", "Malappuram", 
    "Kozhikode", "Wayanad", "Kannur", "Kasaragod"
]

# Robust Abbreviation Mapping
DISTRICT_ABBR = {
    # Standard 3-letter codes
    "TVM": "Thiruvananthapuram", "TRV": "Thiruvananthapuram", "TPM": "Thiruvananthapuram",
    "KLM": "Kollam", "QLN": "Kollam", "KOLLAM": "Kollam",
    "PTA": "Pathanamthitta", "PATHANAMTHITTA": "Pathanamthitta",
    "ALP": "Alappuzha", "ALPY": "Alappuzha", "ALLE": "Alappuzha", "ALE": "Alappuzha",
    "KTM": "Kottayam", "KTYM": "Kottayam",
    "IDK": "Idukki", "IDUKKI": "Idukki",
    "EKM": "Ernakulam", "ERN": "Ernakulam", "ERNAKULAM": "Ernakulam",
    "TCR": "Thrissur", "TSR": "Thrissur", "THRISSUR": "Thrissur",
    "PKD": "Palakkad", "PLK": "Palakkad", "PGT": "Palakkad", "PALAKKAD": "Palakkad",
    "MLP": "Malappuram", "MPM": "Malappuram", "MALAPPURAM": "Malappuram",
    "KKD": "Kozhikode", "CLT": "Kozhikode", "KZD": "Kozhikode", "KOZHIKODE": "Kozhikode", "CALICUT": "Kozhikode",
    "WYD": "Wayanad", "WND": "Wayanad", "WAYANAD": "Wayanad",
    "KNR": "Kannur", "CAN": "Kannur", "CNN": "Kannur", "KANNUR": "Kannur",
    "KSD": "Kasaragod", "KGD": "Kasaragod", "KGQ": "Kasaragod", "KASARAGOD": "Kasaragod"
}

# Weather API Coordinates (Lat, Lon)
DISTRICT_COORDS = {
    "Thiruvananthapuram": (8.5241, 76.9366),
    "Kollam": (8.8932, 76.6141),
    "Pathanamthitta": (9.2648, 76.7870),
    "Alappuzha": (9.4981, 76.3388),
    "Kottayam": (9.5916, 76.5222),
    "Idukki": (9.8494, 76.9809),
    "Ernakulam": (9.9816, 76.2999),
    "Thrissur": (10.5276, 76.2144),
    "Palakkad": (10.7867, 76.6548),
    "Malappuram": (11.0510, 76.0711),
    "Kozhikode": (11.2588, 75.7804),
    "Wayanad": (11.6854, 76.1320),
    "Kannur": (11.8745, 75.3704),
    "Kasaragod": (12.4996, 74.9869)
}

# Common Disease Abbreviations -> Full Name
DISEASE_ABBR_MAPPING = {
    "ADD": "Acute Diarrhoeal Disease", "ACUTE DIARRHOEAL DISEASE": "Acute Diarrhoeal Disease",
    "Fever": "Fever", 
    "Dengue": "Dengue", 
    "Hep A": "Hepatitis A", "Hep B": "Hepatitis B", "Hep C": "Hepatitis C", "Hep E": "Hepatitis E",
    "Hepatitis": "Hepatitis",
    "KFD": "Kyasanur Forest Disease",
    "Lepto": "Leptospirosis",
    "Chik": "Chikungunya", "CG": "Chikungunya",
    "M Pox": "Monkeypox", "Mpox": "Monkeypox", "M P O X": "Monkeypox",
    "JE": "Japanese Encephalitis", "AES": "Japanese Encephalitis", "AES/JE": "Japanese Encephalitis",
    "H1N1": "H1N1",
    "H3N2": "H3N2",
    "Typhoid": "Typhoid",
    "Scrub": "Scrub Typhus",
    "Measles": "Measles",
    "Chicken Pox": "Chickenpox", "Cpox": "Chickenpox", "C Pox": "Chickenpox", "Varicella": "Chickenpox",
    "Cpo x": "Chickenpox", "Cpox": "Chickenpox", "C p o x": "Chickenpox",
    "Mumps": "Mumps",
    "Dysentery": "Dysentery",
    "Malaria": "Malaria",
    "Cholera": "Cholera",
    "Diphtheria": "Diphtheria",
    "Amebic": "Amebic Meningoencephalitis",
    "Nipah": "Nipah",
    "Shigella": "Shigella",
    "West Nile": "West Nile Fever",
    "Meloidosis": "Meloidosis",
    "Covid-19": "Covid-19", "Covid": "Covid-19", "Covid19": "Covid-19",
    "S H I G E L L A": "Shigella",
    "Influen Za": "Influenza", "Influenz A": "Influenza", "Influenza A": "Influenza",
    "Cutaneous Leishmaniasi S": "Cutaneous Leishmaniasis",
    "Rota D": "Rotavirus", "Sari": "SARI"
}

# Diseases that often appear as single columns with no sub-header
SINGLE_COLUMN_DISEASES = [
    "Acute Diarrhoeal Disease", "Chickenpox", "H1N1", 
    "Scrub Typhus", "Measles", "Typhoid", 
    "Diphtheria", "Amebic Meningoencephalitis",
    "Rabies", "Influenza"
]

# STRICT SCHEMA MAPPING
FINAL_COLUMNS = [
    "report_date", "district",
    # Fever
    "fever_op_cases", "fever_ip_cases",
    # Chikungunya
    "chikungunya_suspected", "chikungunya_confirmed", "chikungunya_deaths",
    # Dengue
    "dengue_suspected", "dengue_confirmed", "dengue_deaths",
    # Lepto
    "lepto_suspected", "lepto_confirmed", "lepto_deaths",
    # Others
    "add_cases",
    "chickenpox_cases",
    "hepatitis_a_cases", "hepatitis_b_cases",
    "cholera_suspected", "cholera_confirmed",
    "je_suspected", "je_confirmed",
    "malaria_imported", "malaria_indigenous",
    "typhoid_cases",
    "h1n1_cases",
    "measles_cases",
    "scrub_typhus_cases",
    "diphtheria_cases",
    "amebic_meningoencephalitis_cases",
    "nipah_cases",
    "shigella_cases",
    "west_nile_fever_cases",
    "monkeypox_cases",
    "covid19_cases", "covid19_deaths",
    "rabies_cases", "influenza_cases",
    # External
    "climate_rainfall_mm", "climate_avg_temp_c", "climate_humidity_percent",
    "social_search_index_dengue", "social_search_index_fever"
]

# --- Helper Functions ---

def clean_number(val):
    if not val: return 0
    val = str(val).strip().upper()
    if val in ['-', 'NIL', 'NA', 'NAN', '']:
        return 0
    match = re.search(r'\d+', val)
    if match: return int(match.group(0))
    return 0

def normalize_disease_name(name):
    if not isinstance(name, str): return None
    name = name.strip()
    if not name or len(name) < 2 or len(name) > 50: return None
    
    # 1. Cleanup Whitespace FIRST to handle newlines (e.g. "Cpo\nx")
    name = re.sub(r'\s+', ' ', name)
    
    # Exclusions
    if re.search(r'\d{1,2}[\.\-\/]\d{1,2}[\.\-\/]\d{2,4}', name): return None
    if re.match(r'^\d', name) and name.upper() not in DISEASE_ABBR_MAPPING: return None
    if name.upper() in ['TOTAL', 'SL NO', 'NO', 'DATE', 'DISTRICT', 'REMARKS', 'NAME', 'DISEASE']: return None
    
    # 2. Check Abbr Mapping
    u_name = name.upper()
    for abbr, full in DISEASE_ABBR_MAPPING.items():
        if u_name == abbr.upper(): return full
            
    name = name.title()
    
    # 3. Known fixes
    u_name = name.upper()
    if "DENGUE" in u_name: return "Dengue"
    if "LEPTO" in u_name: return "Leptospirosis"
    if "CHICKEN" in u_name and "POX" in u_name: return "Chickenpox"
    if "CPOX" in u_name: return "Chickenpox"
    if "CHIK" in u_name: return "Chikungunya"
    if "HEPATITIS" in u_name:
        if "A" in u_name: return "Hepatitis A"
        if "B" in u_name: return "Hepatitis B"
        if "C" in u_name: return "Hepatitis C"
        if "E" in u_name: return "Hepatitis E"
        return "Hepatitis"
    if "H1N1" in u_name: return "H1N1"
    if "AMEBIC" in u_name: return "Amebic Meningoencephalitis"
    if "ACUTE DIARRHOEAL" in u_name or "ADD" == u_name: return "Acute Diarrhoeal Disease"
    if "SCRUB" in u_name: return "Scrub Typhus"
    
    return name

def map_to_schema(disease, metric):
    """Map extracted (disease, metric) to final column name."""
    d = disease.lower()
    m = metric.lower()
    
    if "fever" in d:
        if "op" in m: return "fever_op_cases"
        if "ip" in m: return "fever_ip_cases"
        
    if "chikungunya" in d:
        if "sus" in m: return "chikungunya_suspected"
        if "death" in m: return "chikungunya_deaths"
        return "chikungunya_confirmed"
        
    if "dengue" in d:
        if "sus" in m: return "dengue_suspected"
        if "death" in m: return "dengue_deaths"
        return "dengue_confirmed"
        
    if "lepto" in d:
        if "sus" in m: return "lepto_suspected"
        if "death" in m: return "lepto_deaths"
        return "lepto_confirmed"
        
    if "acute diarrhoeal" in d: return "add_cases"
    if "chickenpox" in d: return "chickenpox_cases"
    
    if "hepatitis" in d:
        # Check specific types explicitly to avoid 'a' in 'hepatitis' matching everything
        if "hepatitis a" in d or "hep a" in d or d.endswith(" a"): return "hepatitis_a_cases"
        if "hepatitis b" in d or "hep b" in d or d.endswith(" b"): return "hepatitis_b_cases"
        
    if "cholera" in d:
        if "sus" in m: return "cholera_suspected"
        return "cholera_confirmed"
        
    if "japanese" in d or "je" in d.split():
        if "sus" in m: return "je_suspected"
        return "je_confirmed"
        
    if "malaria" in d:
        if "import" in m: return "malaria_imported"
        # PV, PF, Mx -> Indigenous
        if "indigen" in m or "pv" in m or "pf" in m or "mx" in m: return "malaria_indigenous"
        return "malaria_indigenous"
        
    if "typhoid" in d: return "typhoid_cases"
    if "h1n1" in d: return "h1n1_cases"
    if "measles" in d: return "measles_cases"
    if "scrub" in d: return "scrub_typhus_cases"
    if "diphtheria" in d: return "diphtheria_cases"
    if "amebic" in d: return "amebic_meningoencephalitis_cases"
    if "nipah" in d: return "nipah_cases"
    if "shigella" in d: return "shigella_cases"
    if "west nile" in d: return "west_nile_fever_cases"
    if "monkeypox" in d: return "monkeypox_cases"
    if "covid" in d:
        if "death" in m: return "covid19_deaths"
        return "covid19_cases"
    if "rabies" in d: return "rabies_cases"
    if "influenza" in d: return "influenza_cases"
    
    return None

# --- External Data Fetching ---

def fetch_weather_data(start_date, end_date):
    """Fetch daily Max Temp, Rainfall, Humidity with Incremental Caching."""
    cache_file = "weather_cache_v2.csv"
    existing_df = pd.DataFrame()
    fetch_start = start_date
    
    if os.path.exists(cache_file):
        logging.info("Loading Weather Cache...")
        try:
            existing_df = pd.read_csv(cache_file)
            existing_df['date'] = pd.to_datetime(existing_df['date']).dt.date
            
            if not existing_df.empty:
                last_cached_date = existing_df['date'].max()
                if last_cached_date >= end_date:
                    logging.info("Cache is up to date.")
                    return existing_df
                else:
                    logging.info(f"Cache partial. Fetching from {last_cached_date + timedelta(days=1)}...")
                    fetch_start = last_cached_date + timedelta(days=1)
        except Exception as e:
            logging.warning(f"Corrupt cache, re-fetching all: {e}")
            existing_df = pd.DataFrame() # Reset on error

    logging.info(f"Fetching Weather Data ({fetch_start} to {end_date})...")
    all_weather = []
    # Open-Meteo URL
    url = "https://archive-api.open-meteo.com/v1/archive"
    
    for dist, (lat, lon) in DISTRICT_COORDS.items():
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": fetch_start.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "daily": ["temperature_2m_max", "precipitation_sum", "relative_humidity_2m_mean"],
                "timezone": "IST"
            }
            res = requests.get(url, params=params)
            if res.status_code == 200:
                data = res.json().get("daily", {})
                times = data.get("time", [])
                temps = data.get("temperature_2m_max", [])
                rains = data.get("precipitation_sum", [])
                hums = data.get("relative_humidity_2m_mean", [])
                
                for i, date_str in enumerate(times):
                    all_weather.append({
                        "date": pd.to_datetime(date_str).date(),
                        "district": dist,
                        "climate_avg_temp_c": temps[i] if i < len(temps) else 0.0,
                        "climate_rainfall_mm": rains[i] if i < len(rains) else 0.0,
                        "climate_humidity_percent": hums[i] if i < len(hums) else 0.0
                    })
            time.sleep(0.5)
        except Exception as e:
            logging.error(f"Weather Fetch Error {dist}: {e}")
            
    new_df = pd.DataFrame(all_weather)
    if not new_df.empty:
        if not existing_df.empty:
            final_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            final_df = new_df
            
        # Deduplicate just in case
        final_df = final_df.drop_duplicates(subset=['date', 'district'], keep='last')
        final_df = final_df.sort_values(by=['date', 'district'])
        final_df.to_csv(cache_file, index=False)
        return final_df
    
    return existing_df if not existing_df.empty else pd.DataFrame()

def fetch_google_trends(start_date, end_date):
    """Fetch daily Google Trends with Incremental Caching."""
    cache_file = "trends_cache.csv"
    existing_df = pd.DataFrame()
    fetch_start = start_date
    
    if os.path.exists(cache_file):
        logging.info("Loading Trends Cache...")
        try:
            existing_df = pd.read_csv(cache_file)
            existing_df['date'] = pd.to_datetime(existing_df['date']).dt.date
            
            if not existing_df.empty:
                last_cached_date = existing_df['date'].max()
                if last_cached_date >= end_date:
                    logging.info("Trends Cache is up to date.")
                    return existing_df
                else:
                    logging.info(f"Trends Cache partial. Fetching from {last_cached_date + timedelta(days=1)}...")
                    fetch_start = last_cached_date + timedelta(days=1)
        except Exception as e:
             logging.warning(f"Corrupt trends cache: {e}")
             existing_df = pd.DataFrame()

    logging.info(f"Fetching Google Trends ({fetch_start} to {end_date})...")
    keywords = ["Dengue", "Fever"]
    geo = "IN-KL"
    timeframe = f"{fetch_start.strftime('%Y-%m-%d')} {end_date.strftime('%Y-%m-%d')}"
    
    try:
        pytrends = TrendReq(hl='en-US', tz=330)
        pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo)
        
        df = pytrends.interest_over_time()
        if df.empty: 
            return existing_df
            
        if 'isPartial' in df.columns:
            df = df.drop(columns=['isPartial'])
            
        df_daily = df.resample('D').mean().interpolate(method='linear')
        df_daily = df_daily.reset_index().rename(columns={
            "date": "date",
            "Dengue": "social_search_index_dengue",
            "Fever": "social_search_index_fever"
        })
        df_daily['date'] = df_daily['date'].dt.date
        
        if not existing_df.empty:
            final_df = pd.concat([existing_df, df_daily], ignore_index=True)
        else:
            final_df = df_daily
            
        final_df = final_df.drop_duplicates(subset=['date'], keep='last')
        final_df = final_df.sort_values(by='date')
        final_df.to_csv(cache_file, index=False)
        return final_df
        
    except Exception as e:
        logging.error(f"Google Trends failed: {e}")
        return existing_df

# --- Excel Parsing Logic ---

def get_daily_disease_list(xls):
    """Parse 'ANALYSIS OF COMMUNICABLE DISEASES' sheet to get full names."""
    diseases = set()
    try:
        target_sheet = None
        for s in xls.sheet_names:
            if "ANALYSIS" in s.upper():
                target_sheet = s
                break
        
        if target_sheet:
            df = pd.read_excel(xls, target_sheet, header=None)
            disease_col_idx = -1
            start_row = -1
            
            for r in range(min(10, len(df))):
                for c in range(min(10, df.shape[1])):
                    val = str(df.iloc[r, c]).upper()
                    if "DISEASE" in val and "NAME" not in val:
                        disease_col_idx = c
                        start_row = r + 1
                        break
                if disease_col_idx != -1: break
            
            if disease_col_idx != -1:
                col_vals = df.iloc[start_row:, disease_col_idx].astype(str).tolist()
                for val in col_vals:
                    val = val.strip()
                    if val.upper() in ['TOTAL', 'GRAND TOTAL']: break
                    if not val or val.lower() == 'nan': continue
                    
                    clean = normalize_disease_name(val)
                    if clean:
                        diseases.add(clean)
    except Exception as e:
        logging.warning(f"Could not parse Analysis sheet: {e}")
    return diseases

def resolve_header(row1, row2):
    """Identify (Disease, Metric) from header pairs with enhanced detection."""
    mapping = {}
    last_disease = None
    
    for i, (v1, v2) in enumerate(zip(row1, row2)):
        v1 = str(v1).strip()
        v2 = str(v2).strip()
        
        # Determine Disease
        if v1 and v1.lower() != 'nan':
            # New header block starts here
            norm_v1 = normalize_disease_name(v1)
            if norm_v1:
                last_disease = norm_v1
            else:
                last_disease = None
            
        if not last_disease: continue
        
        disease = last_disease
        metric = "cases" # Default
        v2_u = v2.upper()
        
        # Check for empty sub-header (Single Column Diseases)
        if (not v2 or v2.lower() == 'nan'):
            if disease in SINGLE_COLUMN_DISEASES:
                mapping[i] = (disease, "cases")
            continue

        # Specific Metric Parsing
        if "OP" in v2_u: metric = "op"
        elif "IP" in v2_u: metric = "ip"
        elif "IMP" in v2_u or "IMPORTED" in v2_u: metric = "imported"
        elif "IND" in v2_u or "INDIGENOUS" in v2_u: metric = "indigenous"
        elif "DEATH" in v2_u or v2_u == "D": metric = "deaths"
        elif "SUS" in v2_u or v2_u == "S": metric = "suspected"
        elif "CON" in v2_u or v2_u == "C": metric = "confirmed"
        elif v2_u in ['A', 'B', 'C', 'E']:
            if "HEPATITIS" in disease.upper():
                disease = f"Hepatitis {v2_u}"
                metric = "cases" # Reset metric to cases for specific Hep Type
        
        # Malaria Specific Types (PV, PF, Mx)
        if disease == "Malaria" and v2_u in ['PV', 'PF', 'MX']:
            metric = "indigenous"

        mapping[i] = (disease, metric)
        
    return mapping

def parse_grid_data(df, dist_col_idx):
    """Extract grid data."""
    extracted = []
    header_map = {} 
    header_row = -1
    
    for r in range(min(30, len(df)-1)):
        row1 = df.iloc[r].tolist()
        row2 = df.iloc[r+1].tolist()
        m = resolve_header(row1, row2)
        if len(m) > 0:
            header_map = m
            header_row = r + 1
            break
            
    if not header_map: return []
        
    for r in range(header_row + 1, len(df)):
        row = df.iloc[r].tolist()
        dist_name = None
        if dist_col_idx < len(row):
            raw_dist = str(row[dist_col_idx]).strip().upper()
            if raw_dist in DISTRICT_ABBR:
                dist_name = DISTRICT_ABBR[raw_dist]
            elif raw_dist.title() in DISTRICTS:
                dist_name = raw_dist.title()
                
        if not dist_name: continue
        
        for col, (dis, met) in header_map.items():
            if col < len(row):
                val = clean_number(row[col])
                if val >= 0:
                     extracted.append({
                         "district": dist_name,
                         "disease": dis,
                         "metric": met,
                         "count": val
                     })
    return extracted

def parse_text_data(df):
    """Parse text rows for cases."""
    extracted = []
    text_blob = df.astype(str).values.flatten()
    dist_codes = "|".join(DISTRICT_ABBR.keys())
    
    # Pattern 1: Disease: District: Location (e.g., Shigella: TVM: xyz)
    pattern1 = re.compile(fr"([A-Za-z\s]+)[:\-] ({dist_codes})[:\-] (.+)", re.IGNORECASE)
    # Pattern 2: District: Disease: Location (e.g., TVM: Shigella: xyz)
    pattern2 = re.compile(fr"({dist_codes})[:\-] ([A-Za-z\s]+)[:\-] (.+)", re.IGNORECASE)
    
    def _process(raw_disease, raw_dist, locs):
        disease = normalize_disease_name(raw_disease)
        if not disease: disease = raw_disease.strip().title()
        
        dist_name = DISTRICT_ABBR.get(raw_dist.upper())
        if not dist_name: return
        
        locs_clean = re.sub(r'\(.*?\)', '', locs)
        count = len([x for x in locs_clean.split(',') if x.strip()])
        
        if count > 0:
            extracted.append({
                "district": dist_name,
                "disease": disease,
                "metric": "confirmed", 
                "count": count
            })

    for line in text_blob:
        line = line.strip()
        if len(line) < 10: continue
        
        for m in pattern1.findall(line):
            _process(m[0], m[1], m[2])
            
        for m in pattern2.findall(line):
            _process(m[1], m[0], m[2])
            
    return extracted

# --- Main Pipeline ---

def main():
    if not os.path.exists(EXCEL_DIR):
        print("Excel directory not found.")
        return

    files = sorted(glob.glob(os.path.join(EXCEL_DIR, "*.xlsx")))
    if not files:
        print("No files.")
        return
        
    file_map = {}
    dates = []
    for f in files:
        base = os.path.basename(f).replace("IDSP-Report-", "").replace(".xlsx", "")
        try:
            d = datetime.strptime(base, "%Y-%m-%d").date()
            file_map[d] = f
            dates.append(d)
        except: pass
        
    if not dates: return
    dates.sort()
    start_date = dates[0]
    end_date = dates[-1]
    full_date_range = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    
    # Fetch External
    weather_df = fetch_weather_data(start_date, end_date)
    trends_df = fetch_google_trends(start_date, end_date)
    
    master_records = [] 
    logging.info(f"Processing {len(full_date_range)} days...")
    
    for current_date in full_date_range:
        fpath = file_map.get(current_date)
        daily_data = [] 
        
        if fpath:
            logging.info(f"  Parsing {current_date}...")
            try:
                xls = pd.ExcelFile(fpath)
                
                # Phase 1: Identify the absolute correct grid sheet 
                # (User Constraint: Sheet must contain "DISTRICT WISE DAILY REPORTING FORMAT")
                target_grid_sheet = None
                for sheet in xls.sheet_names:
                    try:
                        df_preview = pd.read_excel(xls, sheet, header=None, nrows=20)
                        # Flatten to string to find the title regardless of cell merges
                        text_blob = " ".join(df_preview.astype(str).values.flatten()).upper()
                        text_blob = re.sub(r'\s+', ' ', text_blob)
                        if "DISTRICT WISE DAILY" in text_blob or "DAILY REPORTING FORMAT" in text_blob:
                            target_grid_sheet = sheet
                            break
                    except: pass
                    
                # Fallback to the last sheet if we somehow miss the explicit title text
                if not target_grid_sheet and len(xls.sheet_names) > 0:
                    target_grid_sheet = xls.sheet_names[-1]
                
                # Phase 2: Process sheets
                for sheet in xls.sheet_names:
                    try:
                        df = pd.read_excel(xls, sheet, header=None)
                        
                        # Only extract numerical grid values if this is the target sheet
                        if sheet == target_grid_sheet:
                            dist_col = -1
                            for c in range(min(20, df.shape[1])):
                                 col_vals = df.iloc[:, c].astype(str).values
                                 matches = sum(1 for x in col_vals if x.strip().upper() in DISTRICT_ABBR)
                                 if matches > 5:
                                     dist_col = c
                                     break
                            
                            if dist_col != -1:
                                grid_recs = parse_grid_data(df, dist_col)
                                daily_data.extend(grid_recs)
                                
                        # Always parse text narratives from all sheets (for rare cases / deaths)
                        text_recs = parse_text_data(df)
                        daily_data.extend(text_recs)
                        
                    except Exception as e:
                        logging.error(f"Error parsing sheet {sheet}: {e}")
            except Exception as e:
                logging.error(f"Error opening {fpath}: {e}")
        else:
             logging.warning(f"  Missing file for {current_date}")
             
        # Create 14 rows for this date
        for dist in DISTRICTS:
            row = {
                "report_date": current_date,
                "district": dist,
                # Initialize strict schema with 0
                **{k: 0 for k in FINAL_COLUMNS if k not in ["report_date", "district"]}
            }
            
            # External Data
            if not weather_df.empty:
                w = weather_df[(weather_df['date'] == current_date) & (weather_df['district'] == dist)]
                if not w.empty:
                    row['climate_avg_temp_c'] = w.iloc[0].get('climate_avg_temp_c', 0)
                    row['climate_rainfall_mm'] = w.iloc[0].get('climate_rainfall_mm', 0)
                    row['climate_humidity_percent'] = w.iloc[0].get('climate_humidity_percent', 0)
            
            if not trends_df.empty:
                t = trends_df[trends_df['date'] == current_date]
                if not t.empty:
                     row['social_search_index_dengue'] = t.iloc[0].get('social_search_index_dengue', 0)
                     row['social_search_index_fever'] = t.iloc[0].get('social_search_index_fever', 0)

            # Map Extracted Data to Schema
            dist_recs = [r for r in daily_data if r['district'] == dist]
            for rec in dist_recs:
                col_name = map_to_schema(rec['disease'], rec['metric'])
                if col_name and col_name in row:
                    row[col_name] += rec['count']
                
            master_records.append(row)
            
    final_df = pd.DataFrame(master_records)
    # Reorder columns explicitly
    final_df = final_df[FINAL_COLUMNS]
    
    logging.info(f"Saving {OUTPUT_FILE} with shape {final_df.shape}...")
    final_df.to_csv(OUTPUT_FILE, index=False)
    print(f"Success! Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
