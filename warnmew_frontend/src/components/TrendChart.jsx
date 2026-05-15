import React from 'react';
import {
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Area,
    ComposedChart,
    Legend,
    Line,
} from 'recharts';
import { format, parseISO } from 'date-fns';

const TrendChart = ({ historyData, forecastData }) => {
    // Format history data - ensure 0 values are kept (not null/undefined)
    const formattedHistory = historyData.map(d => ({
        date: d.date,
        cases: Number(d.confirmed_case_count) || 0,
        search: Number(d.search_interest) || 0,
    }));

    // Create combined data with forecast connected to last history point
    let combinedData = [...formattedHistory];

    if (forecastData.length > 0 && formattedHistory.length > 0) {
        // Get the last historical point
        const lastHistoryIndex = formattedHistory.length - 1;
        const lastHistoryPoint = formattedHistory[lastHistoryIndex];

        // Add forecast value to the last history point (connection point)
        combinedData[lastHistoryIndex] = {
            ...combinedData[lastHistoryIndex],
            forecast: lastHistoryPoint.cases,
        };

        // Add all forecast data points
        forecastData.forEach(d => {
            combinedData.push({
                date: d.date,
                forecast: Math.round(d.predicted_cases) || 0,
            });
        });
    }

    // Calculate Y-axis domain to ensure 0 is always visible and values are integers
    const allCases = combinedData.map(d => d.cases).filter(v => v !== undefined && v !== null);
    const allForecasts = combinedData.map(d => d.forecast).filter(v => v !== undefined && v !== null);
    const allSearch = combinedData.map(d => d.search).filter(v => v !== undefined && v !== null);

    const maxDataValue = Math.max(
        ...allCases,
        ...allForecasts,
        ...allSearch,
        10 // Minimum max value to prevent empty charts
    );

    // Round up to nearest nice number to avoid floating point issues
    const maxValue = Math.ceil(maxDataValue * 1.1);

    // Custom Tooltip - Dark Theme
    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
            // Filter out casesArea and duplicates
            const uniquePayload = payload.filter(p =>
                p.name !== 'casesArea' && p.dataKey !== 'casesArea'
            );

            return (
                <div style={{
                    backgroundColor: 'rgba(6, 43, 31, 0.95)',
                    backdropFilter: 'blur(10px)',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    border: '1px solid rgba(56, 189, 248, 0.3)',
                    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
                }}>
                    <p style={{
                        fontWeight: 'bold',
                        color: '#38bdf8',
                        marginBottom: '8px',
                        fontSize: '13px'
                    }}>
                        {label ? format(parseISO(label), 'MMM d, yyyy') : ''}
                    </p>
                    {uniquePayload.map((entry, index) => (
                        <div key={index} style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            fontSize: '13px',
                            padding: '2px 0',
                        }}>
                            <span style={{
                                width: '10px',
                                height: '10px',
                                borderRadius: '50%',
                                backgroundColor: entry.color
                            }} />
                            <span style={{ color: '#94a3b8' }}>{entry.name}:</span>
                            <span style={{ fontWeight: 'bold', color: '#f1f5f9' }}>
                                {typeof entry.value === 'number' ? Math.round(entry.value) : entry.value}
                            </span>
                        </div>
                    ))}
                </div>
            );
        }
        return null;
    };

    // Custom Legend
    const renderLegend = (props) => {
        const { payload } = props;
        // Filter out casesArea from legend
        const filtered = payload.filter(p =>
            p.value !== 'casesArea' && p.dataKey !== 'casesArea'
        );

        return (
            <div style={{
                display: 'flex',
                justifyContent: 'center',
                gap: '24px',
                marginTop: '16px',
                fontSize: '13px',
            }}>
                {filtered.map((entry, index) => (
                    <div key={index} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {entry.value === 'Forecast' ? (
                            // Dashed line for Forecast
                            <span style={{
                                width: '20px',
                                height: '0',
                                borderTop: `3px dashed ${entry.color}`,
                            }} />
                        ) : (
                            // Solid line for other entries
                            <span style={{
                                width: '20px',
                                height: '3px',
                                borderRadius: '2px',
                                backgroundColor: entry.color,
                            }} />
                        )}
                        <span style={{ color: '#94a3b8' }}>{entry.value}</span>
                    </div>
                ))}
            </div>
        );
    };

    return (
        <div style={{ width: '100%', height: '420px' }}>
            <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={combinedData} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                    <defs>
                        {/* Gradient for cases area - Cyan/Blue theme */}
                        <linearGradient id="casesGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.4} />
                            <stop offset="50%" stopColor="#0ea5e9" stopOpacity={0.15} />
                            <stop offset="100%" stopColor="#0284c7" stopOpacity={0.02} />
                        </linearGradient>
                        {/* Glow effect */}
                        <filter id="glow">
                            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                            <feMerge>
                                <feMergeNode in="coloredBlur" />
                                <feMergeNode in="SourceGraphic" />
                            </feMerge>
                        </filter>
                    </defs>

                    <CartesianGrid
                        strokeDasharray="3 3"
                        vertical={false}
                        stroke="rgba(56, 189, 248, 0.1)"
                    />

                    <XAxis
                        dataKey="date"
                        tickFormatter={(str) => {
                            try {
                                return format(parseISO(str), 'MMM d');
                            } catch {
                                return str;
                            }
                        }}
                        stroke="#475569"
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        tickLine={false}
                        axisLine={{ stroke: 'rgba(56, 189, 248, 0.2)' }}
                    />

                    {/* Single Y-Axis for all data - Always start from 0 */}
                    <YAxis
                        stroke="#38bdf8"
                        tick={{ fontSize: 11, fill: '#64748b' }}
                        tickLine={false}
                        axisLine={false}
                        domain={[0, maxValue]}
                        allowDataOverflow={false}
                        tickFormatter={(value) => Math.round(value)}
                        allowDecimals={false}
                    />

                    <Tooltip content={<CustomTooltip />} />

                    <Legend content={renderLegend} />

                    {/* Area fill - No legend entry */}
                    <Area
                        type="monotone"
                        dataKey="cases"
                        name="casesArea"
                        fill="url(#casesGradient)"
                        stroke="transparent"
                        legendType="none"
                        isAnimationActive={false}
                    />

                    {/* Cases Line - Cyan Blue - Always visible */}
                    <Line
                        type="monotone"
                        dataKey="cases"
                        name="Cases"
                        stroke="#38bdf8"
                        strokeWidth={3}
                        dot={false}
                        filter="url(#glow)"
                        connectNulls={true}
                        isAnimationActive={false}
                        activeDot={{
                            r: 6,
                            fill: "#38bdf8",
                            stroke: "#041c14",
                            strokeWidth: 2
                        }}
                    />

                    {/* Forecast Line - Orange/Amber */}
                    <Line
                        type="monotone"
                        dataKey="forecast"
                        name="Forecast"
                        stroke="#f97316"
                        strokeWidth={3}
                        strokeDasharray="8 4"
                        dot={{
                            r: 5,
                            fill: "#f97316",
                            stroke: "#041c14",
                            strokeWidth: 2
                        }}
                        connectNulls={true}
                        isAnimationActive={false}
                    />

                    {/* Search Interest - Gold */}
                    <Line
                        type="monotone"
                        dataKey="search"
                        name="Search"
                        stroke="#e5b72a"
                        strokeWidth={2}
                        dot={false}
                        opacity={0.7}
                        connectNulls={true}
                        isAnimationActive={false}
                    />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
};

export default TrendChart;
