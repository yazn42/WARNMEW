import os
import io
import re
import time
import json
import argparse
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import threading
import itertools
from concurrent.futures import ThreadPoolExecutor

# Libraries
import pandas as pd
import pdfplumber
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from PIL import Image, ImageEnhance
from pdf2image import convert_from_path
import openpyxl
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# New Digital Extraction Imports
from img2table.document import PDF
try:
    from pdfminer.high_level import extract_text
except ImportError:
    # Fallback or strict requirement?
    # extract_text is needed for the patcher.
    pass

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('conversion.log')
    ]
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
PDF_FOLDER = SCRIPT_DIR / "IDSP_Reports_All"
OUTPUT_FOLDER = SCRIPT_DIR / "excel_files"
OUTPUT_FOLDER.mkdir(exist_ok=True)
OCR_LOG_FILE = SCRIPT_DIR / "ocr_files.log"

# API KEYS (Round Robin)
API_KEYS = [
    "AIzaSyDiVMJCnN8QxmeDqJzYnJk2OxGG3-H2JzQ"
]

class KeyManager:
    def __init__(self, keys):
        self.keys = itertools.cycle(keys)
        self.lock = threading.Lock()
    
    def get_next_key(self):
        with self.lock:
            return next(self.keys)

key_manager = KeyManager(API_KEYS)

# --- VOCABULARY ---
# Spell corrections for truncated/misspelled/garbled vertical text
SPELL_CORRECTIONS = {
    # Truncated words
    "Hepati": "Hepatitis",
    "Hepatit": "Hepatitis",
    "Chickenp": "Chickenpox",
    "Leptospi": "Leptospirosis",
    "Encephal": "Encephalitis",
    "Meningit": "Meningitis",
    "Influen": "Influenza",
    # Vertical text garbling - Correct to readable names
    "b\nu\nr": "Scrub",
    "c\nS": "Scrub",
    "S\nc": "Scrub",
    "n\ne\nua\nlz": "Influenza",
    "f\nn\nI": "Influenza",
    "n\noE\nCJ": "JE",
    "o\npx\nC": "Chickenpox",
    "D\nD\nA": "ADD",
    "S\nE\nA": "AES",
    ".\no\nN": "No.",
    ".\\no\\nN": "No.",
    # Common OCR errors
    "Dengu": "Dengue",
    "Chikungury": "Chikungunya",
    # OCR merged header/subheader errors
    "Con JE": "JE",
    "Sus JE": "JE",
    "Con AES": "AES",
    "Sus AES": "AES",
    "Con Malaria": "Malaria",
    "Sus Malaria": "Malaria",
}

# DISABLED: Abbreviation expansion (User requested 1:1)
KERALA_DISEASE_VOCAB = {
    "NO.": "No.", ".ON": "No.", 
    "REPORT TITLE": ""
}

def expand_token(text: str) -> str:
    """Returns text AS-IS to match PDF exactly."""
    if not isinstance(text, str): return text
    return text.strip()

def clean_cell_value(val):
    """Cleans OCR text stuttering from PDFs (e.g., 'Disease\nDisease' -> 'Disease')."""
    if val is None: return None
    val_str = str(val).strip()
    if not val_str: return None
        
    if '\n' in val_str:
        lines = [line.strip() for line in val_str.split('\n') if line.strip()]
        if lines and all(line == lines[0] for line in lines):
            if lines[0].isdigit(): return int(lines[0])
            return lines[0]
            
    words = val_str.split()
    if len(words) > 1 and all(word == words[0] for word in words):
        if words[0].isdigit(): return int(words[0])
        return words[0]
        
    return val

def fix_spelling(text: str) -> str:
    """Fixes known spelling errors/truncations."""
    if not isinstance(text, str): return text
    for wrong, correct in SPELL_CORRECTIONS.items():
        if text == wrong:
            return correct
    return text

def remove_header_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Removes duplicate disease names from header rows (0-5) across ALL rows."""
    # Disease names that should only appear once in the entire header region
    disease_names = {'Scrub', 'Influenza', 'JE', 'Chickenpox', 'ADD', 'AES', 'DENGUE', 'LEPTO', 
                     'Malaria', 'Cholera', 'Hepatitis', 'Fever', 'CG', 'No.'}
    
    seen = set()  # Track across ALL header rows
    for row_idx in range(min(6, len(df))):
        for col_idx in range(len(df.columns)):
            val = str(df.iloc[row_idx, col_idx]).strip()
            if val in disease_names:
                if val in seen:
                    # Clear duplicate
                    df.iloc[row_idx, col_idx] = ""
                else:
                    seen.add(val)
    return df

def align_tot_row(df: pd.DataFrame) -> pd.DataFrame:
    """Ensures 'TOT' or 'Total' label is in Column 1 (District Column)."""
    # Simple heuristic to identify District column: usually index 1
    # Check if we have at least 2 cols
    if df.shape[1] < 2: return df
    
    for r in range(len(df)):
        row_str = str(df.iloc[r, :].values).upper()
        
        # Robust Total Row Detection
        is_tot = "TOT" in row_str or "TOTAL" in row_str or "GRAND TOTAL" in row_str
        
        if is_tot:
            # Find where TOT is
            tot_col = -1
            for c_idx in range(len(df.columns)):
                val_upper = str(df.iloc[r, c_idx]).upper().strip()
                if "TOT" in val_upper or "TOTAL" in val_upper:
                    tot_col = c_idx
                    break
            
            # If found and NOT in Col 1, move it
            if tot_col != -1 and tot_col != 1:
                # Move 'TOT' string to Col 1
                df.iloc[r, 1] = "TOT" # Standardize to TOT
                if tot_col != 1: df.iloc[r, tot_col] = "" # Clear old pos if not same
            
            # Ensure Col 0 is empty for visual clean if it's a Total row (usually spans)
            df.iloc[r, 0] = ""
            
    return df

def add_calculated_total_row(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates and appends a Total row if one is missing."""
    # Check if Total row exists (in first 5 cols or any col labeled TOT)
    for r in range(len(df)):
        row_str = str(df.iloc[r, :].values).upper()
        if "TOT" in row_str or "TOTAL" in row_str or "GRAND TOTAL" in row_str:
            return df # Already exists
            
    # If we are here, Total is missing. Calculate it.
    new_row = [""] * len(df.columns)
    if len(new_row) > 1:
        new_row[1] = "TOT"
    else:
        new_row[0] = "TOT"
        
    for c in range(len(df.columns)):
        # Skip District column (Col 1) AND Index column (Col 0)
        if c <= 1: continue
        
        # Try to sum this column
        total = 0.0
        is_numeric_col = False
        valid_count = 0
        
        for r in range(len(df)):
            val = str(df.iloc[r, c]).strip()
            # Treat PDF visual spacers '-' as 0
            val_clean = val.replace('-', '0').replace('', '0')
            try:
                # Remove common OCR noise like 'l' -> '1'? No, risky. 
                # Just parse standard numbers
                num = float(val_clean)
                total += num
                if val_clean != '0': valid_count += 1
                is_numeric_col = True # At least one number found implies potential numeric col
            except:
                pass
                
        # Heuristic: Only fill total if the column looks numeric (has valid numbers)
        # OR if it's strictly empty (sum 0) but we want to show '-'?
        if is_numeric_col:
            if total.is_integer():
                new_row[c] = str(int(total))
            else:
                new_row[c] = str(total)
            
            # If sum is 0, use '-' style?
            if total == 0: new_row[c] = "-"
             
    # Append the row
    df.loc[len(df)] = new_row
    return df

# --- HELPER FUNCTIONS ---

def clean_value(val: Any) -> Union[int, float, str]:
    """Cleans cell values for DATA ROWS only."""
    # Strict Rule: Empty/None/NaN/- -> 0
    if pd.isna(val): return 0
    s_val = str(val).strip()
    if s_val == "" or s_val.lower() == "none" or s_val.lower() == "nan": return 0
    if s_val in ['-', '.', 'Nil', 'NA', 'N/A']: return 0
    
    try:
        # Remove trailing periods common in OCR (e.g. "12.")
        if s_val.endswith('.'): s_val = s_val[:-1]
        
        if s_val.replace('.', '', 1).isdigit():
             return float(s_val) if '.' in s_val else int(s_val)
    except: pass
    return s_val

def enhance_image(image: Image.Image) -> Image.Image:
    """Enhances image for better OCR."""
    image = image.convert('L')
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.5)
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(3.5)
    
    return image

def is_data_row(row: List[Any]) -> bool:
    """Heuristic to check if a row is a 'Data Row'."""
    non_empty = [str(x).strip() for x in row if str(x).strip() not in ['', 'nan']]
    if not non_empty: return False 
    
    # If explicit 0, counts as data
    if len(non_empty) == 1 and not non_empty[0].replace('.','',1).isdigit(): return False 
    
    numeric_count = 0
    for x in non_empty:
        if x in ['0', '-', 'Nil'] or x.replace('.','',1).isdigit(): numeric_count += 1
        
    first_col = str(row[0]).strip()
    if first_col.isdigit() and int(first_col) < 100: return True
    if numeric_count > 0 and len(non_empty) > 1: return True
    return False

def merge_vertical_headers(table_content: List[List[Any]]) -> List[List[Any]]:
    """Merges vertical headers in Digital report."""
    table_start_idx = -1
    for i, row in enumerate(table_content):
        if len(row) > 3:
            table_start_idx = i
            break
    if table_start_idx == -1: return table_content
    
    rows_to_check = 6 
    end_idx = min(len(table_content), table_start_idx + rows_to_check)
    num_cols = len(table_content[table_start_idx])
    
    for c in range(num_cols):
        col_text_stack = []
        for r in range(table_start_idx, end_idx):
            val = table_content[r][c]
            if isinstance(val, str) and val.strip():
                col_text_stack.append((r, val.strip()))
            elif val is not None and str(val).strip():
                col_text_stack.append((r, str(val).strip()))
                
        if len(col_text_stack) >= 2:
            merged = "".join(txt for _, txt in col_text_stack)
            # Remove newlines for vertical text
            fixed = merged.replace('\n', '')
            
            # Heuristic: If text looks inverted (e.g. 'fnI' ending for Influenza, 'CJC' for JE), reverse it
            # Also 'burcS' -> 'Scrub'
            if fixed.endswith('fnI') or fixed.endswith('CJC') or fixed.endswith('otpeL') or 'burc' in fixed:
                fixed = fixed[::-1]
            
            # Manual patch for common scramble "Infzlaun" etc if simple reversal didn't work perfectly
            if "Infzl" in fixed or "neualz" in fixed: 
                 # Often 'neualzfnI' -> reversed is 'Infzlauen'. Close enough to 'Influenza' to be readable?
                 # Or just force fix if it's this specific glitch
                 pass

            # If fix changed it OR checking for short split tokens
            if fixed != merged or all(len(txt)<=2 for _, txt in col_text_stack):
                top_row = col_text_stack[0][0]
                table_content[top_row][c] = fixed
                for r, _ in col_text_stack[1:]:
                    table_content[r][c] = "" 
    return table_content

def forward_fill_headers(df: pd.DataFrame, header_idx: int) -> pd.DataFrame:
    """Forward fills header names for visual merging."""
    last_header = ""
    for c in range(len(df.columns)):
        val = str(df.iloc[header_idx, c]).strip().replace('nan', '').replace('None', '')
        if val:
            last_header = val
        elif last_header and c > 0:
            df.iloc[header_idx, c] = last_header
    return df

def post_process_excel(file_path: Path):
    """Applies visual merging and formatting to the Excel file."""
    wb = openpyxl.load_workbook(file_path)
    for sheet in wb.worksheets:
        # Check if generic "Analysis" table (Page 1) or "District Wise" (Page 2)
        is_district_table = False
        header_row_idx = 1
        found_header = False
        
        # Scan for header rows
        for i, row in enumerate(sheet.iter_rows(max_row=30, values_only=True), 1):
            row_str = [str(x).upper() for x in row if x]
            # Analysis Table Pattern: "DISEASE", "TODAY", "CUMULATIVE"
            if any("DISEASE" in x for x in row_str) and any("CUMULATIVE" in x for x in row_str):
                header_row_idx = i
                found_header = True
                break
            # District Table Pattern: "MALARIA", "FEVER", "DISTRICT"
            if any("MALARIA" in x for x in row_str) or (any("FEVER" in x for x in row_str) and len(row_str) > 5):
                header_row_idx = i
                found_header = True
                is_district_table = True
                break
        
        if found_header:
            row = list(sheet[header_row_idx])
            start_col = 0
            current_val = None
            
            for c in range(len(row)):
                cell = row[c]
                val = str(cell.value).strip() if cell.value else ""
                
                # Normalize Nan/None
                if val.lower() == "none" or val.lower() == "nan": val = ""
                
                # Logic: Merge if Identical OR (Val is empty AND CurrentVal exists -> implies span)
                should_merge = False
                if val == current_val:
                    should_merge = True
                elif val == "" and current_val:
                    # Allow merging empty neighbors even in District Table
                    should_merge = True
                
                if should_merge:
                    # Continue span
                    pass 
                else:
                    # Close previous span
                    if current_val and (c - start_col) > 1:
                        top_cell = sheet.cell(row=header_row_idx, column=start_col+1)
                        # Only merge if start/end are valid ranges
                        try:
                            sheet.merge_cells(start_row=header_row_idx, start_column=start_col+1, 
                                              end_row=header_row_idx, end_column=c)
                            top_cell.alignment = Alignment(horizontal='center', vertical='center')
                        except: pass 
                    
                    current_val = val
                    start_col = c
            
            # Close final span
            if current_val and (len(row) - start_col) > 1:
                try:
                    sheet.merge_cells(start_row=header_row_idx, start_column=start_col+1, 
                                  end_row=header_row_idx, end_column=len(row))
                    cell = sheet.cell(row=header_row_idx, column=start_col+1)
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                except: pass

    wb.save(file_path)

def merge_date_into_title(df: pd.DataFrame) -> pd.DataFrame:
    """Merges Date Row into Title Row."""
    rows_to_drop = []
    for i in range(1, min(10, len(df))):
        row = df.iloc[i].astype(str)
        date_pattern = re.compile(r'\d{2}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2}|\bDate\b', re.IGNORECASE)
        has_date = row.apply(lambda x: bool(date_pattern.search(x))).any()
        
        if has_date:
            for c in range(len(df.columns)):
                val = str(df.iloc[i, c])
                if date_pattern.search(val):
                    df.iloc[i, c] = "" # Clear original
                    target_col = 2 # Force Col 2
                    if target_col < len(df.columns):
                        current = str(df.iloc[i-1, target_col])
                        if current == "" or current == "nan":
                            df.iloc[i-1, target_col] = val
                        else:
                            df.iloc[i-1, target_col] = current + " " + val
            rows_to_drop.append(i)
            
    if rows_to_drop:
        df = df.drop(index=rows_to_drop).reset_index(drop=True)
    return df

def align_tot_row(df: pd.DataFrame) -> pd.DataFrame:
    """Forces 'TOT' (Total) row to start at the SAME Column as 'District' header."""
    target_col = 0
    # Find Dist header
    for r in range(min(10, len(df))):
        row_vals = [str(x).upper() for x in df.iloc[r]]
        for c, txt in enumerate(row_vals):
            if "DIST" in txt:
                target_col = c
                break
        if target_col != 0: break
        
    for i, row in df.iterrows():
        row_str_upper = [str(x).upper() for x in row]
        has_tot = any("TOT" in x for x in row_str_upper)
        if has_tot:
            src_col = -1
            for idx, x in enumerate(row_str_upper):
                if "TOT" in x:
                    src_col = idx
                    break
            if src_col != -1 and src_col != target_col:
                val = df.iloc[i, src_col]
                # Shift Left/Right
                if src_col < target_col:
                    # Insert emptiness? Hard to shift pandas row without rebuilding
                    # Simple swap for now (works if alignment is just slightly off)
                    df.iloc[i, target_col] = val
                    df.iloc[i, src_col] = ""
                else:
                    # Shift left implies deleting leading empty cells
                    # Safer: Just move the TOT label. 
                    # If values are shifted, we assume they follow the label.
                    # This is complex. For now, move label.
                    df.iloc[i, src_col] = ""
                    df.iloc[i, target_col] = val
                    
                    # Heuristic: If we moved label L->R, we likely need to shift data too?
                    # Usually "TOT" and "345" are in subsequent columns.
                    # If we move TOT, we preserve relative order? No.
                    # Let's hope cleaning handled data.
    return df

def clean_stray_data(df: pd.DataFrame, header_idx: int) -> pd.DataFrame:
    """ Removes data from columns/rows that have NO headers."""
    # 1. Identify Valid Columns
    # A column is valid if Row[header_idx] is NOT empty OR Row[header_idx+1] is NOT empty
    valid_cols = []
    
    # Bounds check
    if header_idx + 1 < len(df):
        sub_header_idx = header_idx + 1
    else:
        sub_header_idx = header_idx # No subheader?
        
    for c in range(len(df.columns)):
        h1_raw = str(df.iloc[header_idx, c]).strip().replace('nan', '')
        h2_raw = str(df.iloc[sub_header_idx, c]).strip().replace('nan', '') if sub_header_idx != header_idx else ""
        
        # Heuristic: If H1 is empty, H2 must be meaningful (Text) to be a valid subheader.
        # If H2 is just a number (e.g. '0'), it's likely stray data, not a header.
        h2_is_valid = h2_raw and not h2_raw.replace('.', '', 1).isdigit()
        
        # Valid if Main Header exists OR (Subheader exists and is not just a number)
        # OR if it is Col 0 (Index)
        if h1_raw or h2_is_valid or c == 0: 
            valid_cols.append(c)
        else:
            # Check if this column has ANY data below subheader
            # If strictly empty, fine. If numbers, it is "stray".
            pass

    # Apply Cleaning: Set stray cols to ""
    for r in range(header_idx + 1, len(df)):
        # Check Row validity: If Col 0 is empty, is it a data row?
        col0 = str(df.iloc[r, 0]).strip().replace('nan', '')
        row_str = str(df.iloc[r, :].values).upper()
        
        # Robust Total Row Detection
        is_tot = "TOT" in row_str or "TOTAL" in row_str or "GRAND TOTAL" in row_str
        
        # ALIGNMENT FIX: If it is a Total row, ensure "TOT" is in Col 1 (District Column)
        if is_tot:
            # Find where TOT is
            tot_col = -1
            for c_idx in range(len(df.columns)):
                val_upper = str(df.iloc[r, c_idx]).upper().strip()
                if "TOT" in val_upper or "TOTAL" in val_upper:
                    tot_col = c_idx
                    break
            
            # If found and NOT in Col 1, move it
            if tot_col != -1 and tot_col != 1:
                # Move 'TOT' string to Col 1
                current_val = df.iloc[r, tot_col]
                df.iloc[r, 1] = "TOT" # Standardize to TOT
                if tot_col != 1: df.iloc[r, tot_col] = "" # Clear old pos if not same
            
            # Also ensure Col 0 is empty for visual clean
            df.iloc[r, 0] = ""
            continue # Skip wiping logic for Total row

        row_values = [str(x).strip() for x in df.iloc[r, :] if str(x).strip() not in ['', 'nan', 'None']]
        
        # DEBUG LOGGING for missing Total row investigation
        with open("ocr_debug.txt", "a", encoding="utf-8") as f:
            f.write(f"DEBUG ROW {r}: Col0='{col0}' is_tot={is_tot} Data={row_values[:10]}...\n")
            f.write(f"  Raw: {row_str}\n")

        # Heuristic: Valid Section Header?
        # If Col 0 is empty, but we have text like "VIRAL DISEASES" in other columns, keep it.
        start_with_text = len(row_values) > 0 and not row_values[0].replace('.','',1).isdigit()
        
        # Delete ONLY if: Col 0 is empty AND Not Total AND Not a Text definition row
        if not col0 and not is_tot and not start_with_text:
             df.iloc[r, :] = ""
             continue
             
        for c in range(len(df.columns)):
            if c not in valid_cols and c != 0:
                # Strictly wipe stray columns to prevent '0' generation
                # Unless it's a special text row
                if not start_with_text:
                    df.iloc[r, c] = ""
                
    return df

def expand_headers_horizontal(df: pd.DataFrame, header_idx: int) -> pd.DataFrame:
    """Expands abbreviations in the header row."""
    for c in range(len(df.columns)):
        val = str(df.iloc[header_idx, c])
        if val and val != 'nan':
            df.iloc[header_idx, c] = expand_token(val)
    return df

# --- EXTRACTION ENGINES ---

def smart_clean_dataframe(df: pd.DataFrame, is_ocr: bool = False) -> pd.DataFrame:
    """Applies cleaning rules ONLY to data rows."""
    if is_ocr and not df.empty:
      # Removed "Report Title" cleaning to preserve top content
      pass

    # Identify Header Row (Row with most strings)
    header_idx = -1
    max_text = -1
    for i, row in df.iterrows():
        text_cols = sum(1 for x in row if isinstance(x, str) and len(str(x).strip()) > 3) 
        if text_cols > max_text:
            max_text = text_cols
            header_idx = i
            
    if header_idx == -1 and is_ocr: header_idx = 1 # Guess 
    
    # 1. Expand Headers (DISABLED)
    # df = expand_headers_horizontal(df, header_idx)
    
    # 2. Clean Stray Data (RE-ENABLED for Zero Removal)
    # We must remove stray columns so they don't get filled with 0s
    df = clean_stray_data(df, header_idx)
    
    # 3. Forward Fill Headers (For Merging)
    # Identifiy Valid Columns (Header is not empty and significant)
    valid_cols = set()
    for c in range(len(df.columns)):
        h_val = str(df.iloc[header_idx, c]).strip()
        # Header must be >1 char (ignore '.', '|') OR be specific known headers
        if h_val not in ['', 'nan', 'None'] and (len(h_val) > 1 or h_val.isalnum()):
            valid_cols.add(c)
    # Ensure ID/Dist cols are always valid
    valid_cols.add(0)
    valid_cols.add(1)

    cleaned_rows = []
    for i in range(len(df)):
        row = df.iloc[i].tolist()
        new_row = []
        is_header = (i <= header_idx)
        should_clean = is_data_row(row) and not is_header
        
        for c_idx, val in enumerate(row):
            if is_header:
                 new_row.append(val if not pd.isna(val) else "")
            elif not should_clean:
                 new_row.append(val if not pd.isna(val) else "")
            elif c_idx == 0:
                 new_row.append(val if not pd.isna(val) else "")
            elif c_idx in valid_cols:
                 # Inside Table: Apply 0-filling
                 new_row.append(clean_value(val))
            else:
                 # Outside Table: Force Empty
                 new_row.append("")
        cleaned_rows.append(new_row)
        
    df_cleaned = pd.DataFrame(cleaned_rows, columns=df.columns)
    
    # POST-PROCESSING
    df_cleaned = align_tot_row(df_cleaned)
    if is_ocr:
        df_cleaned = merge_date_into_title(df_cleaned)
        
    return df_cleaned

class DigitalExtractor:
    @staticmethod
    def extract(pdf_path: Path, output_excel_path: Path) -> bool:
        print(f"DEBUG: Starting Digital Extraction for {pdf_path.name}")
        temp_excel_path = output_excel_path.parent / ("temp_" + output_excel_path.name)
        
        try:
             # 1. GENERATE NATIVE EXCEL 
            pdf = PDF(src=str(pdf_path), detect_rotation=False)
            pdf.to_xlsx(dest=str(temp_excel_path), implicit_rows=False, borderless_tables=False, min_confidence=50)

            # 2. GROUP SHEETS BY PAGE
            wb_temp = openpyxl.load_workbook(temp_excel_path)
            page_groups = {}
            for ws in wb_temp.worksheets:
                page_match = re.search(r'Page\s*(\d+)', ws.title, re.IGNORECASE)
                p_num = int(page_match.group(1)) if page_match else 999
                if p_num not in page_groups: page_groups[p_num] = []
                page_groups[p_num].append(ws)

            # 3. BUILD FINAL EXCEL
            wb_final = openpyxl.Workbook()
            wb_final.remove(wb_final.active)
            
            if not page_groups:
                print("  -> No tables found.")
                wb_temp.close()
                if temp_excel_path.exists(): os.remove(temp_excel_path)
                return False

            pages_list = sorted(page_groups.keys())
            
            # Common Fonts/Borders
            thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                                 top=Side(style='thin'), bottom=Side(style='thin'))
            bold_font = Font(bold=True)
            header_font = Font(bold=True, size=12)

            # Extract date for header
            date_str = ""
            match = re.search(r'(\d{4})-(\d{2})-(\d{2})', pdf_path.name)
            if match:
                year, month, day = match.groups()
                date_str = f"{day}.{month}.{year}"

            for p_num in pages_list:
                # --- EXTRACT RAW PDF TEXT FOR THIS PAGE ---
                try:
                    # pdfminer uses 0-indexed page numbers
                    # Check if pdfminer is available
                    raw_page_text = extract_text(pdf_path, page_numbers=[p_num - 1])
                    page_lines = [re.sub(r'\s+', ' ', line).strip() for line in raw_page_text.split('\n') if line.strip()]
                except Exception:
                    page_lines = []

                ws_final = wb_final.create_sheet(title=f"Page {p_num}")
                tables_in_page = page_groups[p_num]
                current_row = 1 

                for t_idx, ws_temp in enumerate(tables_in_page):
                    is_first_table = (p_num == pages_list[0] and t_idx == 0)
                    is_last_table = (p_num == pages_list[-1] and t_idx == len(tables_in_page) - 1)
                    
                    max_col = ws_temp.max_column
                    max_row = ws_temp.max_row
                    num_cols = max_col if max_col >= 3 else 3
                    mid_col = (num_cols // 2) + 1

                    # --- INJECT HEADERS ---
                    if is_first_table:
                        ws_final.cell(row=current_row, column=1, value='DISTRICT WISE DAILY REPORTING FORMAT').font = header_font
                        ws_final.cell(row=current_row, column=mid_col, value='Kerala State').font = header_font
                        ws_final.cell(row=current_row, column=mid_col).alignment = Alignment(horizontal='center')
                        ws_final.cell(row=current_row, column=num_cols, value=date_str).font = header_font
                        ws_final.cell(row=current_row, column=num_cols).alignment = Alignment(horizontal='right')
                        current_row += 2

                    if is_last_table:
                        ws_final.cell(row=current_row, column=1, value='ANALYSIS OF COMMUNICABLE DISEASES').font = header_font
                        ws_final.cell(row=current_row, column=num_cols, value=date_str).font = header_font
                        ws_final.cell(row=current_row, column=num_cols).alignment = Alignment(horizontal='right')
                        current_row += 2

                    row_offset = current_row - 1
                    
                    # --- COPY TABLE DATA ---
                    for r in range(1, max_row + 1):
                        dest_r = r + row_offset
                        
                        # Lock the row height so cells don't become massive
                        ws_final.row_dimensions[dest_r].height = 18 
                        
                        row_vals = []
                        
                        for c in range(1, max_col + 1):
                            col_letter = get_column_letter(c)
                            ws_final.column_dimensions[col_letter].width = 12 
                            
                            s_cell = ws_temp.cell(row=r, column=c)
                            d_cell = ws_final.cell(row=dest_r, column=c)
                            
                            cleaned_val = clean_cell_value(s_cell.value)
                            d_cell.value = cleaned_val
                            d_cell.border = thin_border
                            
                            if s_cell.font and s_cell.font.bold:
                                d_cell.font = bold_font

                            d_cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=False)

                            # Track non-empty values to trigger our text recovery
                            if cleaned_val is not None and str(cleaned_val).strip() != "":
                                row_vals.append((c, str(cleaned_val).strip()))

                        # --- THE SMART TEXT PATCHER ---
                        if len(row_vals) >= 2:
                            last_col_idx, valB = row_vals[-1]
                            prev_col_idx, valA = row_vals[-2]
                            
                            if re.match(r'^[\d\-]+$', valB):
                                pattern = re.escape(valA) + r'\s+' + re.escape(valB) + r'\s+(?P<missing>[A-Za-z0-9].*)'
                                
                                for line in page_lines:
                                    match = re.search(pattern, line)
                                    if match:
                                        missing_text = match.group('missing').strip()
                                        if missing_text:
                                            patch_col = last_col_idx + 1
                                            patch_cell = ws_final.cell(row=dest_r, column=patch_col)
                                            patch_cell.value = missing_text
                                            patch_cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=False)
                                            
                                            if patch_col < max_col:
                                                ws_final.merge_cells(start_row=dest_r, start_column=patch_col, end_row=dest_r, end_column=max_col)
                                        break

                    # --- COPY MERGES ---
                    for m_range in ws_temp.merged_cells.ranges:
                        min_col, min_row, max_col_bound, max_row_bound = m_range.bounds
                        try:
                            ws_final.merge_cells(
                                start_row=min_row + row_offset, 
                                start_column=min_col, 
                                end_row=max_row_bound + row_offset, 
                                end_column=max_col_bound
                            )
                        except Exception: pass 

                    current_row += max_row + 2 

            # 4. SAVE AND CLEANUP
            wb_final.save(output_excel_path)
            wb_temp.close()
            os.remove(temp_excel_path)
            
            print(f"  -> Success! Missing text fully recovered and injected.")
            return True

        except Exception as e:
            print(f"DEBUG: Digital Extraction Failed: {e}")
            import traceback
            traceback.print_exc()
            return False

class OCRExtractor:
    @staticmethod
    def extract(pdf_path: Path) -> List[pd.DataFrame]:
        print(f"DEBUG: Starting OCR for {pdf_path.name}")
        tables = []
        try:
            images = convert_from_path(pdf_path, dpi=300, fmt='jpeg')
            
            page_results = [None] * len(images)
            
            def process_page(idx, img):
                img_byte_arr = io.BytesIO()
                enhance_image(img).save(img_byte_arr, format='JPEG', quality=95)
                # Retry loop - Try all keys if needed
                max_retries = len(API_KEYS) + 1
                for attempt in range(max_retries):
                    try:
                        df = OCRExtractor.call_gemini(img_byte_arr.getvalue())
                        if df is not None:
                            # Apply spelling corrections only
                            df = df.applymap(fix_spelling)
                            # Apply alignment and deduplication for OCR too
                            df = remove_header_duplicates(df)
                            df = align_tot_row(df)
                            df = add_calculated_total_row(df)
                            return df
                    except Exception as e:
                        print(f"DEBUG: Page {idx+1} Attempt {attempt+1}/{max_retries} Failed: {e}")
                        # Key is rotated automatically by call_gemini at start of next call (via get_next_key)
                
                return pd.DataFrame([["ERROR: PAGE FAILED"]], columns=["Error"])

            for i, img in enumerate(images):
                print(f"DEBUG: Processing Page {i+1}...")
                current_result = process_page(i, img) 
                
                # STRICT SEQUENTIAL CHECK
                # If this page failed, STOP immediately. Do not proceed to next page.
                if current_result is not None and "Error" in current_result.columns and len(current_result) == 1 and str(current_result.iloc[0,0]).startswith("ERROR"):
                     print(f"CRITICAL: Page {i+1} Extraction Failed after {len(API_KEYS)} attempts. Stopping.")
                     return [] # Return empty to signal total failure
                
                page_results[i] = current_result
                
            tables = [df for df in page_results if df is not None]
            
        except Exception as e:
            logger.error(f"OCR failed: {e}")
        return tables

    @staticmethod
    def call_gemini(img_bytes: bytes) -> Optional[pd.DataFrame]:
        key = key_manager.get_next_key()
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = """
        ACT AS A DATA ENTRY AND OCR SPECIALIST. 
        TASK: TRANSCRIPT THE *ENTIRE* PAGE CONTENT INTO A 2D GRID PRESERVING THE VISUAL LAYOUT.
        
        0. **TABLE POPULATION** : Make sure all tables are entirely populated accurately and correctly.
        1. **VERTICAL TEXT HANDLING** :  Some column headers contains vertical text which has to be read from bottom to top. Sometimes there are multiple lines of vertical text which is seperated by a new line but it should be read as a single column header for example there is vertical text 'Cpo' in one line and 'x' in another line, it should be read as 'Cpox' which is abbreviated form of chicken pox disease. Another example is 'Con' in one line and 'JE' in another line as vertical text, this is the disease named 'Con JE'.
        
        Return ONLY valid JSON (list of lists). NO CODE BLOCKS.
        """
        try:
            resp = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_bytes}])
            text = resp.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[0]
            text = text.strip()
            return pd.DataFrame(json.loads(text))
        except Exception as e:
            print(f"DEBUG: Gemini call failed: {e}")
            raise e 

# --- MAIN ---
def detect_scanned_pdf(pdf_path: Path) -> bool:
    """Detects if PDF is likely scanned (OCR needed)."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages: return True
            # Check first few pages
            for page in pdf.pages[:2]:
                text = page.extract_text() or ""
                # If very little text, assume scanned
                if len(text.strip()) < 50: return True
        return False
    except: return True

def log_ocr_file(pdf_path: Path, reason: str):
    """Logs files that require OCR extraction to ocr_files.log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} | {pdf_path.name} | OCR Required | Reason: {reason}\n"
    with open(OCR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)
    logger.info(f"OCR log: {pdf_path.name} - {reason}")

def process_pdf(pdf_path: Path, use_ocr: Optional[bool] = None):
    print(f"DEBUG: Processing {pdf_path}")
    
    # AUTO DETECTION
    if use_ocr is None:
        is_scanned = detect_scanned_pdf(pdf_path)
        use_ocr = is_scanned
        print(f"DEBUG: Auto-detection for {pdf_path.name} -> Scanned: {is_scanned}, Using OCR: {use_ocr}")
    
    # Log files that require OCR extraction
    if use_ocr:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text_len = len((pdf.pages[0].extract_text() or "").strip()) if pdf.pages else 0
            reason = f"Scanned/image PDF (extractable text: {text_len} chars, threshold: 50)"
        except Exception:
            reason = "Could not open PDF for text extraction - assuming scanned"
        log_ocr_file(pdf_path, reason)

    out = OUTPUT_FOLDER / f"{pdf_path.stem}.xlsx"

    if use_ocr:
        tables = OCRExtractor.extract(pdf_path)
        if not tables:
            print("DEBUG: No tables found (OCR)")
            return
        
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for i, df in enumerate(tables):
            ws = wb.create_sheet(f"Page {i+1}")
            for r in dataframe_to_rows(df, index=False, header=False):
                ws.append(r)
        wb.save(out)
    else:
        # New Digital Extraction (Returns bool, saves file directly)
        success = DigitalExtractor.extract(pdf_path, out)
        if not success:
            print("DEBUG: Digital extraction failed.")
            return
    
    # Post Process for Merging
    try:
        post_process_excel(out)
    except Exception as e:
        print(f"DEBUG: Post-processing failed: {e}")
        
    logger.info(f"Saved: {out}")
    print(f"DEBUG: Saved to {out}")

def main():
    print("DEBUG: Script Start")
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--file", type=str)
    parser.add_argument("--batch", action="store_true", help="Process all unprocessed PDFs in IDSP_Reports_All")
    args = parser.parse_args()
    
    if args.validate:
        p1 = PDF_FOLDER / "IDSP-Report-2026-01-08.pdf"
        p2 = PDF_FOLDER / "IDSP-Report-2026-01-27.pdf"
        
        if p1.exists(): process_pdf(p1, True)
        if p2.exists(): process_pdf(p2, False)
    elif args.batch:
        # Process all PDFs that don't have a corresponding Excel output
        pdf_files = sorted(PDF_FOLDER.glob("*.pdf"))
        total = len(pdf_files)
        skipped = 0
        processed = 0
        failed = 0
        ocr_needed = 0
        
        # Clear OCR log for a fresh scan of all files
        if OCR_LOG_FILE.exists():
            OCR_LOG_FILE.unlink()
        
        print(f"Found {total} PDFs in {PDF_FOLDER}")
        
        for i, pdf_path in enumerate(pdf_files, 1):
            excel_path = OUTPUT_FOLDER / f"{pdf_path.stem}.xlsx"
            
            # Always check if OCR was needed (even for already-processed files)
            is_scanned = detect_scanned_pdf(pdf_path)
            if is_scanned:
                ocr_needed += 1
                try:
                    with pdfplumber.open(pdf_path) as pdf:
                        text_len = len((pdf.pages[0].extract_text() or "").strip()) if pdf.pages else 0
                    reason = f"Scanned/image PDF (extractable text: {text_len} chars, threshold: 50)"
                except Exception:
                    reason = "Could not open PDF for text extraction - assuming scanned"
                log_ocr_file(pdf_path, reason)
            
            if excel_path.exists():
                skipped += 1
                continue
            
            print(f"\n[{i}/{total}] Processing: {pdf_path.name}")
            try:
                process_pdf(pdf_path, use_ocr=is_scanned)
                processed += 1
            except Exception as e:
                logger.error(f"Failed to process {pdf_path.name}: {e}")
                failed += 1
        
        print(f"\n--- Batch Complete ---")
        print(f"Total: {total} | Processed: {processed} | Skipped (already done): {skipped} | Failed: {failed}")
        print(f"Files requiring OCR: {ocr_needed} (see {OCR_LOG_FILE.name})")
    elif args.file:
        process_pdf(PDF_FOLDER / args.file, False)
    print("DEBUG: Script End")

if __name__ == "__main__":
    main()
