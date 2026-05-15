# 🛡️ WARNMEW — Epidemic Early Warning System for Kerala

**AI-powered disease surveillance dashboard with 7-day outbreak forecasting, climate correlation analysis, district rankings, and automated alert generation.**

WARNMEW (Warning and Alert Response Network for Medical Early Warning) monitors 24 communicable diseases across all 14 districts of Kerala using IDSP (Integrated Disease Surveillance Programme) weekly reports. It combines LSTM/GRU deep learning models with district-specific weather data and seasonal patterns to forecast outbreaks before they escalate, training separate models for each disease × district combination.

---

## 📋 Table of Contents

1. [System Requirements](#-system-requirements)
2. [Project Structure](#-project-structure)
3. [Step 1 — Install Prerequisites](#-step-1--install-prerequisites)
4. [Step 2 — Set Up the Database](#-step-2--set-up-the-database)
5. [Step 3 — Build the Data Pipeline (First Time Only)](#-step-3--build-the-data-pipeline-first-time-only)
6. [Step 4 — Configure and Start the Backend](#-step-4--configure-and-start-the-backend)
7. [Step 5 — Start the Frontend](#-step-5--start-the-frontend)
8. [Step 6 — Open the Dashboard](#-step-6--open-the-dashboard)
9. [Keeping Data Up-to-Date](#-keeping-data-up-to-date)
10. [Management Commands Reference](#-management-commands-reference)
11. [Troubleshooting](#-troubleshooting)

---

## 💻 System Requirements

Install these **before** starting setup:

| Software | Version | Download Link | Verify With |
|---|---|---|---|
| **Python** | **3.11 only** | [python.org/downloads/release/python-3117](https://www.python.org/downloads/release/python-3117/) | `python --version` |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) | `node -v` |
| **PostgreSQL** | 14+ | [postgresql.org](https://www.postgresql.org/download/) | `psql --version` |
| **Poppler** | Latest | [poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases/) | `pdftoppm -v` |

> **Important (Windows):** During installation, check **"Add to PATH"** for Python, and manually add Poppler's `bin` folder to your system PATH. To verify, open a **new** terminal and run the verification commands above.

---

## 📁 Project Structure

```
warnmew latest project/
│
├── warnmew_backend/                # Django REST API + ML Engine
│   ├── ml_engine/                  #   Forecasting models (LSTM, GRU, SARIMA, RF, XGBoost, SVR)
│   │   ├── forecaster.py           #     Main forecaster (train + predict)
│   │   ├── feature_engineering.py  #     Enhanced feature generation (80+ features)
│   │   ├── baseline_models.py      #     RF, XGBoost, SVR baselines
│   │   └── sarima_model.py         #     SARIMA time-series model
│   ├── surveillance/               #   Django app (models, views, API endpoints)
│   │   ├── models.py               #     DailyDiseaseRecord, Alert, UserProfile
│   │   ├── views.py                #     REST API endpoints (history, forecast, map, alerts)
│   │   ├── auth_views.py           #     Registration, login, profile
│   │   └── management/commands/    #     CLI commands (ingest, train, alerts)
│   ├── models/                     #   Trained model weights (.pt, .pkl) — per-disease × per-district
│   ├── warnmew_backend/            #   Django project settings
│   ├── manage.py                   #   Django entry point
│   ├── .env                        #   Database credentials (you create this)
│   └── .env.example                #   Template for .env (copy and fill in)
│
├── warnmew_frontend/               # React + Vite + Tailwind CSS
│   └── src/
│       ├── components/
│       │   ├── Dashboard.jsx        #   Main dashboard layout + stats + CSV export
│       │   ├── TrendChart.jsx       #   Historical cases + forecast line chart
│       │   ├── ClimatePanel.jsx     #   Climate correlation (cases vs temp/rain/humidity)
│       │   ├── DistrictTable.jsx    #   District rankings table with sorting
│       │   ├── Map.jsx              #   Leaflet choropleth map of Kerala
│       │   ├── Heatmap.jsx          #   Calendar heatmap (GitHub contribution style)
│       │   ├── NotificationBell.jsx #   Alert notification dropdown
│       │   ├── FilterBar.jsx        #   District filter selector
│       │   ├── DiseaseSelect.jsx    #   Disease dropdown component
│       │   ├── LoginPage.jsx        #   User login page
│       │   └── RegisterPage.jsx     #   User registration page
│       ├── context/AuthContext.jsx  #   JWT auth context provider
│       ├── api.js                   #   Axios API client with token refresh
│       └── index.css                #   Global styles + design system
│
├── IDSP_Reports_All/               # Raw PDF reports scraped from DHS Kerala
├── excel_files/                    # PDFs converted to Excel
├── warnmew_training_dataset.csv    # Unified 42-column dataset (auto-generated)
│
├── idsp_reports_scraping.py        # Step 1: Scrape PDFs from DHS Kerala website
├── pdf_to_excel_converter.py       # Step 2: Convert PDFs → Excel using OCR + Gemini AI
├── data_pipeline.py                # Step 3: Excel → Enhanced CSV (adds district-level weather, trends)
│
├── requirements.txt                # Python dependencies
├── .gitignore                      # Git ignore rules
├── update_data.bat                 # One-click data refresh (Windows)
└── README.md                       # This file
```

---

## 🔧 Step 1 — Install Prerequisites

Open **PowerShell** or **Command Prompt** in the project root folder.

### 1.1 Create a Python virtual environment

This project requires **Python 3.11**. If you have multiple Python versions installed, use the **py launcher** to select 3.11:

```
py -3.11 -m venv venv
```

If Python 3.11 is your only installed version:
```
python -m venv venv
```

### 1.2 Activate the virtual environment

**Windows (PowerShell or Command Prompt):**

⚠️ **First time on a new system?** PowerShell blocks scripts by default. Run this **once** first:
```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Type **Y** when prompted. You only need to do this once per Windows user account.

```
.\venv\Scripts\activate
```

**Mac/Linux:**
```
source venv/bin/activate
```

You should see `(venv)` at the start of your terminal prompt. **All `python` and `pip` commands below assume the venv is active.**

### 1.3 Install Python libraries

```
pip install -r requirements.txt
```

> This installs Django, PyTorch, img2table, Polars, and all other dependencies. Python 3.11 is required — other versions may cause compatibility issues with `img2table` and `torch`.

### 1.4 Install frontend dependencies

Open a **second terminal**, navigate to the frontend folder:

```
cd warnmew_frontend
npm install
```

---

## 🗄️ Step 2 — Set Up the Database

### 2.1 Install PostgreSQL

If you don't already have PostgreSQL installed:

1. Download PostgreSQL from https://www.postgresql.org/download/windows/
2. Run the installer and follow the setup wizard
3. **Remember the password** you set for the `postgres` user — you will need it below
4. When asked which components to install, keep the defaults (make sure **pgAdmin 4** is checked)
5. Keep the default port as **5432**

### 2.2 Create the database

You can create the database using **either** pgAdmin (GUI) or the command line.

**Option A — Using pgAdmin 4 (recommended for beginners):**

1. Open **pgAdmin 4** from the Start menu
2. In the left sidebar, expand **Servers** → **PostgreSQL** → right-click on **Databases**
3. Click **Create** → **Database...**
4. In the **Database** field, type: `warnmew_database`
5. Make sure **Owner** is set to `postgres`
6. Click **Save**

**Option B — Using the command line (psql):**

Open a terminal and run:
```
psql -U postgres
```
Enter your PostgreSQL password when prompted. Then run:
```
CREATE DATABASE warnmew_database OWNER postgres ENCODING 'UTF8';
```
Type `\q` and press Enter to exit psql.

### 2.3 Create the environment file

Navigate to the backend folder (from the project root) and copy the template:

```
cd warnmew_backend
copy .env.example .env
```

Open the newly created `.env` file in any text editor and replace `your_password_here` with the password you set during PostgreSQL installation:

```
DB_NAME=warnmew_database
DB_USER=postgres
DB_PASSWORD=YOUR_POSTGRES_PASSWORD
DB_HOST=localhost
DB_PORT=5432
DEBUG=True
SECRET_KEY=your-secret-key-here
```

> 💡 The `SECRET_KEY` can be any random string — it is used by Django for session security. For local development, any value works.

### 2.4 Run database migrations

Make sure you are inside the `warnmew_backend` folder, then run:

```
python manage.py migrate
```

This creates all the necessary tables in your database (`DailyDiseaseRecord`, `Alert`, `UserProfile`, etc.). You should see output like:
```
Applying contenttypes.0001_initial... OK
Applying auth.0001_initial... OK
Applying surveillance.0001_initial... OK
...
```

---

## 📊 Step 3 — Build the Data Pipeline (First Time Only)

> **Skip this step** if the `warnmew_training_dataset.csv` file already exists and is containing the latest data. The pre-trained models in `warnmew_backend/models/` work with the existing data. For automating the steps from 3.1 to 3.6, just run the command below:

```
.\update_data.bat
```

If you need to understand what each step does in the 'update_data.bat' file or want to build the dataset from scratch manually, follow the steps below:

### 3.1 Scrape IDSP reports

Downloads weekly PDF reports from the DHS Kerala website:

```
python idsp_reports_scraping.py
```

### 3.2 Convert PDFs to Excel

Uses **img2table** for high-accuracy extraction from digital PDFs, falling back to **Google Gemini AI** (OCR) only for scanned image-based reports.

```
python pdf_to_excel_converter.py --batch
```

> ⏱️ This is slow — 2000+ files can take several hours. It's safe to interrupt with `Ctrl+C`; it resumes from where it left off.

### 3.3 Process and enhance the data

Extracts disease counts from Excel files, adds weather data (OpenMeteo API), adds seasonal search interest, and saves enhanced CSVs:

```
python data_pipeline.py
```

### 3.4 Load data into the database

```
cd warnmew_backend
python manage.py ingest_data
```

Wait until you see `INGESTION COMPLETE`. This uses `ignore_conflicts` — running it again on updated CSVs **only adds new records** without overwriting or duplicating existing ones.

### 3.5 Train prediction models (optional)

Pre-trained models are included. To retrain on your data:

```
# Train all diseases × all 14 districts:
python manage.py train_optimized --all

# Train a specific disease for all 14 districts:
python manage.py train_optimized "Dengue"

# Train a specific disease + district:
python manage.py train_optimized "Dengue" --district Ernakulam

# Skip hyperparameter search for faster training:
python manage.py train_optimized --all --no-optuna

# Compare model types (LSTM vs SARIMA vs RF vs XGBoost vs SVR):
python manage.py compare_models --disease "Dengue"
```

### 3.6 Generate alerts

```
python manage.py generate_alerts
```

This clears old alerts, runs the trained models, generates 7-day forecasts for all disease × district combinations, and creates new alerts when predicted cases exceed statistical thresholds (based on Z-scores against the 30-day baseline). Use `--dry-run` to preview without saving.

---

## ⚙️ Step 4 — Configure and Start the Backend

In **Terminal 1** (with `venv` activated):

```
cd warnmew_backend
python manage.py runserver
```

✅ You should see: `Starting development server at http://127.0.0.1:8000/`

---

## 🎨 Step 5 — Start the Frontend

In **Terminal 2** (no venv needed):

```
cd warnmew_frontend
npm run dev
```

✅ You should see: `Local: http://localhost:5173/`

---

## 🌐 Step 6 — Open the Dashboard

Open your browser and go to: **http://localhost:5173**

The dashboard shows:
- **Confirmed case stats** with latest daily data
- **7-day AI forecasts** with confidence level indicator (High / Moderate / Low)
- **Public awareness index** from Google Trends
- **Historical trend chart** with actual vs predicted cases + date range filters
- **CSV data export** — download filtered data as spreadsheet (includes climate data)
- **Interactive Kerala map** — choropleth of district-wise case distribution
- **Climate correlation panel** — cases vs temperature, rainfall & humidity (per-district)
- **District rankings table** — sortable table with case counts and distribution bars
- **Calendar heatmap** — GitHub-style activity heatmap over the past year
- **Automated epidemic alerts** — notification bell with severity-based color coding
- **User authentication** — JWT-based login/register for authenticated access

To stop the servers, press `Ctrl+C` in each terminal window.

---

## 🔄 Keeping Data Up-to-Date

### Automated (Windows)

Double-click `update_data.bat` or run:

```
.\update_data.bat
```

This automatically:
1. Scrapes new PDF reports from DHS Kerala
2. Converts new PDFs to Excel
3. Processes and enhances the data with weather/trends
4. Ingests **only new records** into the database (existing data is preserved)
5. Retrains all prediction models with the latest data
6. Generates fresh alerts from updated forecasts

### Manual (Any OS)

Run these commands in order from the project root:

```
python idsp_reports_scraping.py
python pdf_to_excel_converter.py --batch
python data_pipeline.py
cd warnmew_backend
python manage.py ingest_data
python manage.py train_optimized --all
python manage.py generate_alerts
```

---

## 📚 Management Commands Reference

All commands are run from the `warnmew_backend/` directory:

| Command | Description |
|---|---|
| `python manage.py ingest_data` | Import CSVs into database (appends only, no overwrites) |
| `python manage.py ingest_data --dry-run` | Preview import without writing to database |
| `python manage.py train_optimized --all` | Train per-district models for all diseases (14 models per disease) |
| `python manage.py train_optimized "Dengue"` | Train Dengue models for all 14 districts |
| `python manage.py train_optimized "Dengue" --district Ernakulam` | Train one specific disease+district model |
| `python manage.py train_optimized --all --no-optuna` | Fast batch training (default config, no hyperparameter search) |
| `python manage.py compare_models --disease "Dengue"` | Compare all model architectures for a disease |
| `python manage.py generate_alerts` | Generate alerts from current forecasts |
| `python manage.py generate_alerts --dry-run` | Preview alerts without saving |
| `python manage.py createsuperuser` | Create an admin user for Django Admin |
| `python manage.py migrate` | Apply database schema changes |

---

## 🔧 Troubleshooting

| Problem | Solution |
|---|---|
| `python` is not recognized | Reinstall Python with "Add to PATH" checked, or use `py` instead |
| `npm` is not recognized | Install Node.js from [nodejs.org](https://nodejs.org/) |
| Frontend shows "Network Error" | Backend is not running. Start it in Terminal 1 first |
| Database connection failed | Check credentials in `warnmew_backend/.env`. Ensure PostgreSQL service is running |
| `ModuleNotFoundError` | Activate venv (`.\venv\Scripts\activate`) then run `pip install -r requirements.txt` |
| `pdftoppm` not found | Install Poppler and add its `bin` folder to system PATH |
| `img2table` install errors | Ensure you are using Python 3.11. Other versions are not supported |
| Training accuracy is low | Try `--n-trials 100` for more hyperparameter search iterations |
| Port 8000 already in use | Kill the process: `taskkill /F /IM python.exe` or use `python manage.py runserver 8001` |
| Port 5173 already in use | Kill Node: `taskkill /F /IM node.exe` or change port in `vite.config.js` |

---

© 2026 WARNMEW — Department of Health Services, Kerala.
