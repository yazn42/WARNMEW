"""
IDSP Reports Scraper - Kerala Health Department
Downloads daily health reports from DHS Kerala website.
Skips files that already exist.

Usage:
    python idsp_reports_scraping.py
"""

import requests
from bs4 import BeautifulSoup
import re
import random
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin


# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_FOLDER = SCRIPT_DIR / "IDSP_Reports_All"
# ---------------------


def make_request_with_retry(url, headers, retries=3, backoff_factor=2):
    """Make a request with exponential backoff retry logic."""
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=60)
            if response.status_code == 200:
                return response
            
            # If server error, wait and retry
            if response.status_code in [500, 502, 503, 504]:
                wait_time = (backoff_factor ** attempt) + random.uniform(0, 1)
                print(f"    [RETRY] Server error {response.status_code}. Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                continue
                
            return response
            
        except requests.RequestException as e:
            wait_time = (backoff_factor ** attempt) + random.uniform(0, 1)
            print(f"    [RETRY] Connection failed. Retrying in {wait_time:.1f}s...")
            time.sleep(wait_time)
    
    return None


def get_date_from_string(text):
    """
    Extracts a date from text (e.g., "02/01/2026", "2-1-26").
    """
    date_patterns = [
        r'(\d{1,2})[\./-](\d{1,2})[\./-](\d{4})',  # 02.01.2026
        r'(\d{1,2})[\./-](\d{1,2})[\./-](\d{2})'   # 02.01.26
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            d, m, y = match.groups()
            if len(y) == 2:
                y = "20" + y
            try:
                return datetime(int(y), int(m), int(d))
            except ValueError:
                continue
    return None


def download_report(post_url, report_date, headers):
    """Download PDF from a post page."""
    try:
        # Check if file already exists BEFORE making request
        clean_filename = f"IDSP-Report-{report_date.strftime('%Y-%m-%d')}.pdf"
        save_path = OUTPUT_FOLDER / clean_filename
        
        if save_path.exists():
            return "skipped"
        
        response = make_request_with_retry(post_url, headers)
        if not response or response.status_code != 200:
            return "failed"
            
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find content area
        content_div = soup.find('div', class_='entry-content') or soup.find('body')

        pdf_links = []
        for a in content_div.find_all('a', href=True):
            if a['href'].lower().endswith('.pdf'):
                full_link = urljoin(post_url, a['href'])
                pdf_links.append(full_link)

        if not pdf_links:
            return "no_pdf"

        target_url = pdf_links[0]

        pdf_resp = requests.get(target_url, headers=headers, stream=True, timeout=30)
        if pdf_resp.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in pdf_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return "success"
        else:
            return "failed"

    except Exception as e:
        return "error"


def main():
    # Create output folder
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    current_url = "https://dhs.kerala.gov.in/en/category/idsp/"
    page_count = 1

    stats = {"success": 0, "skipped": 0, "failed": 0, "no_pdf": 0, "error": 0}
    consecutive_skips = 0

    print("=" * 60)
    print("IDSP Reports Scraper - Kerala Health Department")
    print("=" * 60)
    print(f"Output folder: {OUTPUT_FOLDER}")
    print(f"Existing files: {len(list(OUTPUT_FOLDER.glob('*.pdf')))}")
    print("=" * 60)
    print("\nStarting archive crawl (Ctrl+C to stop)...\n")

    print(f"Page {page_count}...", end="\r")
    try:
        while current_url:
                print(f"Page {page_count} - Fetching...", end="\r")

                try:
                    # Random delay between pages to be safe
                    if page_count > 1:
                        time.sleep(random.uniform(2.0, 4.0))

                    response = make_request_with_retry(current_url, headers)
                    
                    if not response:
                        print(f"\n[STOP] Failed to fetch page {page_count} after retries.")
                        break
                        
                    if response.status_code != 200:
                        print(f"\n[STOP] HTTP Error {response.status_code}")
                        break

                    soup = BeautifulSoup(response.content, 'html.parser')
                    articles = soup.find_all('article')

                    if not articles:
                        print("\n[STOP] No articles found on this page.")
                        break

                    # Process posts
                    for article in articles:
                        title_tag = article.find('h2', class_='entry-title')
                        if not title_tag:
                            continue

                        title_text = title_tag.get_text(strip=True)
                        link_tag = title_tag.find('a')
                        if not link_tag:
                            continue
                            
                        raw_link = link_tag['href']
                        full_post_link = urljoin(current_url, raw_link)

                        post_date = get_date_from_string(title_text)

                        if post_date:
                            result = download_report(full_post_link, post_date, headers)
                            stats[result] = stats.get(result, 0) + 1
                            
                            if result == "skipped":
                                consecutive_skips += 1
                                if consecutive_skips > 30:
                                    print(f"\n[INFO] Skipped 30 consecutive existing files. Assuming up-to-date.")
                                    current_url = None
                                    break
                            elif result == "success":
                                print(f"\n[DOWNLOAD] {post_date.strftime('%Y-%m-%d')}")
                                consecutive_skips = 0
                                # Safe delay after download (3-6 seconds)
                                time.sleep(random.uniform(3.0, 6.0))
                            else:
                                consecutive_skips = 0
                                # Small delay for other cases
                                time.sleep(random.uniform(1.0, 2.0))

                    # Find 'Next Page' link
                    next_link_tag = soup.find('a', class_='next page-numbers') or \
                                   soup.find('a', string=re.compile(r'Older posts|Next', re.I))

                    if next_link_tag and next_link_tag.get('href'):
                        raw_next_link = next_link_tag['href']
                        current_url = urljoin(current_url, raw_next_link)
                        page_count += 1
                    else:
                        print("\n\n[DONE] Reached the end of the archive.")
                        current_url = None

                except Exception as e:
                    print(f"\n[ERROR] Page {page_count}: {e}")
                    break

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Stopped by user.")

    # Summary
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETE")
    print("=" * 60)
    print(f"Downloaded: {stats['success']}")
    print(f"Skipped (already exists): {stats['skipped']}")
    print(f"No PDF found: {stats['no_pdf']}")
    print(f"Failed: {stats['failed']}")
    print(f"Errors: {stats['error']}")
    print(f"Total PDFs in folder: {len(list(OUTPUT_FOLDER.glob('*.pdf')))}")
    print("=" * 60)


if __name__ == "__main__":
    main()