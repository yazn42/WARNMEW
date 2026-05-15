@echo off
echo ========================================================
echo  WARNMEW DATA UPDATE UTILITY
echo  Adds new data, retrains models, and refreshes alerts.
echo  Existing data is NEVER overwritten or deleted.
echo ========================================================
echo.

REM --------------------------------------------------------
REM Activate Virtual Environment
REM --------------------------------------------------------
call venv\Scripts\activate

REM --------------------------------------------------------
REM Step 1: Scrape new PDF reports from DHS Kerala website
REM Only downloads reports that haven't been fetched before.
REM --------------------------------------------------------
echo [1/6] SCRAPING NEW REPORTS FROM DHS KERALA...
python idsp_reports_scraping.py
if %errorlevel% neq 0 (
    echo [ERROR] Scraping failed. Check your internet connection.
    pause
    exit /b %errorlevel%
)

REM --------------------------------------------------------
REM Step 2: Convert new PDFs to Excel using OCR
REM Skips files that have already been converted.
REM --------------------------------------------------------
echo.
echo [2/6] CONVERTING NEW PDFS TO EXCEL...
python pdf_to_excel_converter.py --batch
if %errorlevel% neq 0 (
    echo [ERROR] PDF conversion failed. Check Poppler installation and Gemini API keys.
    pause
    exit /b %errorlevel%
)

REM --------------------------------------------------------
REM Step 3: Process Excel files into a unified dataset
REM Merges new data with existing data (append, not replace).
REM Adds weather data and seasonal search interest.
REM Produces a single unified warnmew_training_dataset.csv.
REM --------------------------------------------------------
echo.
echo [3/6] PROCESSING AND ENHANCING DATA...
python data_pipeline.py
if %errorlevel% neq 0 (
    echo [ERROR] Data pipeline failed.
    pause
    exit /b %errorlevel%
)

REM --------------------------------------------------------
REM Step 4: Ingest CSVs into PostgreSQL database
REM Uses bulk_create with ignore_conflicts=True, which means:
REM   - New records are ADDED to the database
REM   - Existing records are SKIPPED (not overwritten)
REM   - No data is ever deleted
REM --------------------------------------------------------
echo.
echo [4/6] INGESTING NEW RECORDS TO DATABASE...
cd warnmew_backend
python manage.py ingest_data
if %errorlevel% neq 0 (
    echo [ERROR] Database ingestion failed. Check .env credentials.
    cd ..
    pause
    exit /b %errorlevel%
)

REM --------------------------------------------------------
REM Step 5: Retrain prediction models with latest data
REM Trains per-district models (14 models per disease).
REM Uses default config (--no-optuna) for faster batch updates.
REM Existing model files are updated (not deleted).
REM If training fails for one disease/district, others still proceed.
REM --------------------------------------------------------
echo.
echo [5/6] RETRAINING PER-DISTRICT PREDICTION MODELS (this may take a while)...
python manage.py train_optimized --all --no-optuna
if %errorlevel% neq 0 (
    echo [WARNING] Some models had training issues. Dashboard still works with previous models.
)

REM --------------------------------------------------------
REM Step 6: Generate alerts from updated forecasts
REM Checks predicted cases against disease thresholds.
REM Duplicate alerts (same disease + title + date) are skipped.
REM --------------------------------------------------------
echo.
echo [6/6] GENERATING ALERTS FROM FRESH FORECASTS...
python manage.py generate_alerts
if %errorlevel% neq 0 (
    echo [WARNING] Alert generation had issues. Check model availability.
)
cd ..

echo.
echo ========================================================
echo  UPDATE COMPLETE!
echo.
echo  - New reports scraped and converted
echo  - Data ingested (existing records preserved)
echo  - Per-district prediction models retrained
echo  - Alerts refreshed from latest forecasts
echo.
echo  Restart the backend server to see updated data:
echo    cd warnmew_backend
echo    python manage.py runserver
echo ========================================================
pause
