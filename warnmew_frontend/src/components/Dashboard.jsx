import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { fetchDiseases, fetchHistory, fetchForecast } from '../api';
import { useAuth } from '../context/AuthContext';
import DiseaseSelect from './DiseaseSelect';
import TrendChart from './TrendChart';
import Heatmap from './Heatmap';
import Map from './Map';
import NotificationBell from './NotificationBell';
import FilterBar from './FilterBar';
import ClimatePanel from './ClimatePanel';
import DistrictTable from './DistrictTable';

const Dashboard = () => {
    const { user, logout } = useAuth();
    const [diseases, setDiseases] = useState([]);
    const [selectedDisease, setSelectedDisease] = useState('');
    const [historyData, setHistoryData] = useState([]);
    const [forecastData, setForecastData] = useState([]);
    const [modelConfidence, setModelConfidence] = useState(null);
    const [modelTypeLabel, setModelTypeLabel] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [filters, setFilters] = useState({ district: 'all' });

    // Date filter state
    const [dateFilter, setDateFilter] = useState('30');

    useEffect(() => {
        fetchDiseases()
            .then(res => setDiseases(res.data))
            .catch(err => console.error("Failed to load diseases", err));
    }, []);

    useEffect(() => {
        if (!selectedDisease) return;
        setLoading(true);
        setError(null);
        setHistoryData([]);
        setForecastData([]);

        const p1 = fetchHistory(selectedDisease, filters)
            .then(res => setHistoryData(res.data))
            .catch(err => {
                console.error("History fetch failed", err);
                setError("Failed to load data.");
            });

        const p2 = fetchForecast(selectedDisease, filters)
            .then(res => {
                if (res.data.predictions) {
                    setForecastData(res.data.predictions);
                }
                setModelConfidence(res.data.model_confidence ?? null);
                setModelTypeLabel(res.data.model_type_label || '');
            })
            .catch(err => console.error("Forecast fetch failed", err));

        Promise.all([p1, p2]).finally(() => setLoading(false));
    }, [selectedDisease, filters]);

    // Filter history data based on selected date range
    const filteredHistoryData = useMemo(() => {
        if (!historyData.length || dateFilter === 'all') return historyData;

        const days = parseInt(dateFilter);
        if (isNaN(days)) return historyData;

        return historyData.slice(-days);
    }, [historyData, dateFilter]);

    const latestRecord = historyData[historyData.length - 1];
    const totalForecast = forecastData.reduce((acc, curr) => acc + Math.round(curr.predicted_cases), 0);
    const searchInterest = Math.round(latestRecord?.search_interest || 0);

    const getTrend = () => {
        if (!latestRecord || !historyData.length) return { level: 'No Data', class: 'safe', icon: '—' };

        // Compare 7-day forecast avg against last 7 days of history
        const recent7 = historyData.slice(-7);
        const recentAvg = recent7.reduce((s, d) => s + (d.confirmed_case_count || 0), 0) / (recent7.length || 1);

        if (forecastData.length > 0) {
            const forecastAvg = forecastData.reduce((s, d) => s + (d.predicted_cases || 0), 0) / forecastData.length;
            const change = recentAvg > 0 ? ((forecastAvg - recentAvg) / recentAvg) * 100 : 0;

            if (change > 20) return { level: 'Rising', class: 'danger', icon: '↑' };
            if (change < -20) return { level: 'Declining', class: 'safe', icon: '↓' };
            return { level: 'Stable', class: 'warning', icon: '→' };
        }

        // No forecast available — just show current volume context
        return { level: 'Stable', class: 'warning', icon: '→' };
    };
    const trend = getTrend();

    const dateFilterOptions = [
        { value: '7', label: '7 Days' },
        { value: '30', label: '30 Days' },
        { value: '90', label: '3 Months' },
        { value: '365', label: '1 Year' },
        { value: 'all', label: 'All Data' },
    ];

    // CSV Export
    const exportCSV = useCallback(() => {
        if (!filteredHistoryData.length) return;
        const headers = ['Date', 'Confirmed Cases', 'Suspected Cases', 'Deaths', 'Temp (C)', 'Rain (mm)', 'Humidity (%)'];
        const rows = filteredHistoryData.map(d => [
            d.date, d.confirmed_case_count || 0, d.suspected_case_count || 0,
            d.confirmed_death_count || 0, d.temp_mean?.toFixed(1) || '', d.rain_sum?.toFixed(1) || '', d.humidity_mean?.toFixed(1) || ''
        ]);
        const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const districtPart = filters.district && filters.district !== 'all' ? `_${filters.district}` : '_All_Districts';
        a.download = `${selectedDisease}${districtPart}_data.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }, [filteredHistoryData, selectedDisease, filters]);

    return (
        <div className="min-h-screen bg-kerala-950 text-slate-100 font-sans bg-grid">

            {/* Hero Header */}
            <header className="hero-header relative z-50">
                <div className="max-w-7xl mx-auto px-6 py-6">
                    <div className="flex flex-col lg:flex-row justify-between items-center gap-6">

                        {/* Branding - Kerala Map + Text */}
                        <div className="flex items-center gap-4">
                            {/* Kerala Map - Circular image without border */}
                            <div className="w-14 h-14 flex-shrink-0 rounded-full overflow-hidden">
                                <img
                                    src="/kerala-map.png"
                                    alt="Kerala"
                                    className="w-full h-full object-cover"
                                />
                            </div>
                            {/* Text Content */}
                            <div>
                                <h1 className="text-2xl lg:text-3xl font-black tracking-tight text-gold leading-tight">
                                    WARNMEW
                                </h1>
                                <p className="text-sm text-kerala-300 font-medium">
                                    Epidemic Early Warning System
                                </p>
                                <p className="text-xs text-slate-500">
                                    Department of Health Services • Kerala
                                </p>
                            </div>
                        </div>

                        {/* Disease Select + User Info */}
                        <div className="flex items-center gap-4 w-full lg:w-auto">
                            <div className="w-full lg:w-80">
                                <DiseaseSelect
                                    diseases={diseases}
                                    selected={selectedDisease}
                                    onChange={setSelectedDisease}
                                />
                            </div>
                            <NotificationBell />
                            {user && (
                                <div className="flex items-center gap-3">
                                    <span className="text-xs text-kerala-300 hidden lg:inline">
                                        {user.username}
                                    </span>
                                    <button
                                        onClick={logout}
                                        className="text-xs text-slate-400 hover:text-white transition-colors px-2 py-1 rounded border border-slate-700 hover:border-kerala-400"
                                    >
                                        Logout
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </header>

            {/* Filter Bar */}
            {selectedDisease && (
                <div className="max-w-7xl mx-auto px-6 pt-4">
                    <FilterBar filters={filters} onFilterChange={setFilters} />
                </div>
            )}

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-6 py-8">

                {/* Welcome State */}
                {!selectedDisease && (
                    <div className="animate-fade-in">
                        <div className="glass-card p-16 text-center mt-8">
                            <div className="w-28 h-28 mx-auto mb-8 rounded-3xl bg-gradient-to-br from-kerala-700 to-kerala-900 flex items-center justify-center shadow-glow-green animate-float">
                                <span className="text-6xl">📊</span>
                            </div>
                            <h2 className="text-4xl font-extrabold mb-4 bg-gradient-to-r from-white via-kerala-200 to-white bg-clip-text text-transparent">
                                Disease Surveillance Dashboard
                            </h2>
                            <p className="text-slate-400 max-w-xl mx-auto text-lg leading-relaxed">
                                Real-time epidemic monitoring powered by AI. Select a disease to view historical trends,
                                predictive analytics, and outbreak forecasts for Kerala.
                            </p>

                            {/* Feature Pills - Properly Centered */}
                            <div className="mt-10 flex flex-wrap justify-center gap-4">
                                <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-kerala-900/50 border border-kerala-600/30 text-kerala-300 text-sm font-medium">
                                    <span className="w-2.5 h-2.5 rounded-full animate-pulse" style={{ backgroundColor: '#2eb860' }}></span>
                                    <span>24 Diseases</span>
                                </div>
                                <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-kerala-900/50 border border-gold/30 text-gold text-sm font-medium">
                                    <span className="w-2.5 h-2.5 rounded-full animate-pulse" style={{ backgroundColor: '#e5b72a' }}></span>
                                    <span>AI Forecasting</span>
                                </div>
                                <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-kerala-900/50 border border-water/30 text-water text-sm font-medium">
                                    <span className="w-2.5 h-2.5 rounded-full animate-pulse" style={{ backgroundColor: '#38bdf8' }}></span>
                                    <span>Live Data</span>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Dashboard Content */}
                {selectedDisease && (
                    <div className="space-y-8 animate-fade-in">

                        {/* Disease Title */}
                        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                            <div className="flex items-center gap-4">
                                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-kerala-600 to-kerala-800 flex items-center justify-center shadow-glow-green">
                                    <span className="text-2xl">🦠</span>
                                </div>
                                <div>
                                    <h2 className="text-2xl font-bold text-white">{selectedDisease}</h2>
                                    <p className="text-slate-500 text-sm">
                                        Last updated: {latestRecord?.date || 'Loading...'}
                                    </p>
                                </div>
                            </div>
                            {filters.district && filters.district !== 'all' && (
                                <div className={`badge-glow ${trend.class}`}>
                                    <span className="w-2 h-2 rounded-full bg-current animate-pulse"></span>
                                    {trend.icon} {trend.level}
                                </div>
                            )}
                        </div>

                        {/* Loading */}
                        {loading && (
                            <div className="glass-card p-20 text-center">
                                <div className="w-16 h-16 mx-auto mb-4 rounded-full border-4 border-kerala-600 border-t-kerala-400 animate-spin"></div>
                                <p className="text-kerala-300 font-semibold">Analyzing surveillance data...</p>
                            </div>
                        )}

                        {/* Error */}
                        {error && (
                            <div className="glass-card p-6 border-l-4 border-red-500">
                                <p className="text-red-400">{error}</p>
                            </div>
                        )}

                        {/* Stats & Charts */}
                        {!loading && historyData.length > 0 && (
                            <>
                                {/* Stats Grid */}
                                <div className={`grid grid-cols-1 ${filters.district && filters.district !== 'all' ? 'md:grid-cols-3' : 'md:grid-cols-2'} gap-6`}>

                                    {/* Current Cases */}
                                    <div className="neon-card p-6">
                                        <div className="flex items-start justify-between">
                                            <div>
                                                <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                                                    Confirmed Cases
                                                </p>
                                                <p className="stat-number text-5xl font-black">
                                                    {latestRecord?.confirmed_case_count || 0}
                                                </p>
                                                <p className="text-slate-500 text-sm mt-3">
                                                    Reported today
                                                </p>
                                            </div>
                                            <div className="w-14 h-14 rounded-2xl bg-kerala-800/50 flex items-center justify-center text-3xl">
                                                📋
                                            </div>
                                        </div>
                                    </div>

                                    {/* Forecast - Only when a specific district is selected */}
                                    {filters.district && filters.district !== 'all' && (
                                        <div className="neon-card gold p-6">
                                            <div className="flex items-start justify-between">
                                                <div>
                                                    <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                                                        7-Day Forecast
                                                    </p>
                                                    <p className="stat-number gold text-5xl font-black">
                                                        {totalForecast}
                                                    </p>
                                                    <div className="flex items-center gap-2 mt-3 flex-wrap">
                                                        <span className="badge-glow safe text-[10px]">AI Predicted</span>
                                                        {modelConfidence !== null && (
                                                            <span className={`text-[10px] px-2 py-0.5 rounded-full border ${modelConfidence >= 70 ? 'bg-emerald-900/50 text-emerald-400 border-emerald-700' :
                                                                modelConfidence >= 40 ? 'bg-yellow-900/50 text-yellow-400 border-yellow-700' :
                                                                    'bg-red-900/50 text-red-400 border-red-700'
                                                                }`}>
                                                                {modelConfidence >= 70 ? '✓ High Confidence' :
                                                                    modelConfidence >= 40 ? '~ Moderate Confidence' :
                                                                        '⟳ Low Confidence'}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                                <div className="w-14 h-14 rounded-2xl bg-gold/10 flex items-center justify-center text-3xl">
                                                    🔮
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {/* Search Interest */}
                                    <div className="neon-card cyan p-6">
                                        <div className="flex items-start justify-between">
                                            <div>
                                                <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                                                    Public Awareness
                                                </p>
                                                <p className="stat-number cyan text-5xl font-black">
                                                    {searchInterest}%
                                                </p>
                                                <p className="text-slate-500 text-sm mt-3">
                                                    Google Trends
                                                </p>
                                            </div>
                                            <div className="w-14 h-14 rounded-2xl bg-water/10 flex items-center justify-center text-3xl">
                                                📈
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Trend Chart with Date Filter */}
                                <div className="chart-glass p-6">
                                    {/* Header with Title and Date Filters */}
                                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
                                        <div>
                                            <h3 className="text-xl font-bold text-white">
                                                Infection Trends & AI Forecast
                                            </h3>
                                            <p className="text-slate-500 text-sm mt-1">
                                                Historical data with 7-day prediction
                                            </p>
                                        </div>

                                        {/* Date Filter + Export */}
                                        <div className="flex items-center gap-3">
                                            <div className="flex flex-wrap gap-2">
                                                {dateFilterOptions.map(opt => (
                                                    <button
                                                        key={opt.value}
                                                        onClick={() => setDateFilter(opt.value)}
                                                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${dateFilter === opt.value
                                                            ? 'bg-kerala-600 text-white shadow-glow-green'
                                                            : 'bg-kerala-900/50 text-slate-400 hover:bg-kerala-800/50 hover:text-white'
                                                            }`}
                                                    >
                                                        {opt.label}
                                                    </button>
                                                ))}
                                            </div>
                                            <button
                                                onClick={exportCSV}
                                                className="px-4 py-2 rounded-lg text-sm font-medium bg-kerala-900/50 text-slate-400 hover:bg-kerala-800/50 hover:text-white border border-slate-700 hover:border-kerala-400 transition-all flex items-center gap-2"
                                                title="Export data as CSV"
                                            >
                                                <span>📥</span> CSV
                                            </button>
                                        </div>
                                    </div>

                                    {/* Chart - Legend is built into the chart component via Recharts */}
                                    <TrendChart historyData={filteredHistoryData} forecastData={forecastData} />
                                </div>

                                {/* Spatial Analysis - Map */}
                                <div className="chart-glass p-6">
                                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
                                        <div>
                                            <h3 className="text-xl font-bold text-white">
                                                District-Wise Spread
                                            </h3>
                                            <p className="text-slate-500 text-sm mt-1">
                                                Latest Spatial Distribution
                                            </p>
                                        </div>
                                    </div>
                                    {/* Map Component */}
                                    <Map diseaseName={selectedDisease} />
                                </div>

                                {/* Climate Correlation */}
                                <ClimatePanel historyData={filteredHistoryData} />

                                {/* District Rankings Table */}
                                <DistrictTable diseaseName={selectedDisease} />

                                {/* Heatmap */}
                                <div className="chart-glass p-6">
                                    <div className="flex items-center justify-between mb-4">
                                        <div>
                                            <h3 className="text-xl font-bold text-white">
                                                Case Intensity Calendar
                                            </h3>
                                            <p className="text-slate-500 text-sm mt-1">
                                                12-month case distribution
                                            </p>
                                        </div>
                                    </div>
                                    <Heatmap data={historyData} />
                                </div>
                            </>
                        )}
                    </div>
                )}
            </main>

            {/* Footer */}
            <footer className="footer-gradient mt-16 py-10">
                <div className="max-w-7xl mx-auto px-6 text-center">
                    <p className="text-slate-500 text-sm">
                        © 2026 Department of Health Services, Government of Kerala
                    </p>
                    <p className="text-slate-600 text-xs mt-2">
                        Powered by AI Surveillance Technology
                    </p>
                </div>
            </footer>
        </div>
    );
};

export default Dashboard;
