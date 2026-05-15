import React from 'react';
import {
    ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip,
    Legend, ResponsiveContainer
} from 'recharts';

const ClimatePanel = ({ historyData }) => {
    if (!historyData || historyData.length === 0) return null;

    // Sample data to avoid over-plotting (max 90 points)
    const step = Math.max(1, Math.floor(historyData.length / 90));
    const data = historyData.filter((_, i) => i % step === 0).map(d => ({
        date: d.date?.slice(5) || '', // MM-DD
        cases: d.confirmed_case_count || 0,
        temp: d.temp_mean ? Math.round(d.temp_mean * 10) / 10 : null,
        rain: d.rain_sum ? Math.round(d.rain_sum * 10) / 10 : null,
        humidity: d.humidity_mean ? Math.round(d.humidity_mean * 10) / 10 : null,
    }));

    const CustomTooltip = ({ active, payload, label }) => {
        if (!active || !payload) return null;
        return (
            <div style={{
                background: 'rgba(10, 25, 20, 0.95)',
                border: '1px solid rgba(46, 184, 96, 0.3)',
                borderRadius: '12px',
                padding: '12px 16px',
                fontSize: '12px',
                color: '#e2e8f0',
                backdropFilter: 'blur(8px)',
            }}>
                <p style={{ fontWeight: 700, marginBottom: 6, color: '#94a3b8' }}>{label}</p>
                {payload.map((p, i) => (
                    <p key={i} style={{ color: p.color, margin: '2px 0' }}>
                        {p.name}: <strong>{p.value ?? '—'}</strong>
                    </p>
                ))}
            </div>
        );
    };

    return (
        <div className="chart-glass p-6">
            <div className="mb-6">
                <h3 className="text-xl font-bold text-white">Climate Correlation</h3>
                <p className="text-slate-500 text-sm mt-1">
                    Disease cases vs temperature, rainfall & humidity
                </p>
            </div>
            <ResponsiveContainer width="100%" height={400}>
                <ComposedChart data={data} margin={{ top: 10, right: 30, left: 10, bottom: 35 }}>
                    <defs>
                        <linearGradient id="casesGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#2eb860" stopOpacity={0.4} />
                            <stop offset="100%" stopColor="#2eb860" stopOpacity={0.02} />
                        </linearGradient>
                        <linearGradient id="rainGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.3} />
                            <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.02} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.08)" />
                    <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false}
                        label={{ value: 'Date', position: 'insideBottom', offset: -5, fill: '#94a3b8', fontSize: 11 }}
                    />
                    <YAxis yAxisId="cases" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false}
                        label={{ value: 'Number of Cases', angle: -90, position: 'insideLeft', offset: 10, fill: '#2eb860', fontSize: 11, style: { textAnchor: 'middle' } }}
                    />
                    <YAxis yAxisId="climate" orientation="right" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false}
                        label={{ value: 'Weather Values', angle: 90, position: 'insideRight', offset: 10, fill: '#f59e0b', fontSize: 11, style: { textAnchor: 'middle' } }}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend
                        wrapperStyle={{ fontSize: '11px', color: '#94a3b8', paddingTop: '20px' }}
                        iconType="circle"
                    />
                    <Area
                        yAxisId="cases" type="monotone" dataKey="cases" name="Cases"
                        fill="url(#casesGrad)" stroke="#2eb860" strokeWidth={2}
                    />
                    <Line
                        yAxisId="climate" type="monotone" dataKey="temp" name="Temp (°C)"
                        stroke="#f59e0b" strokeWidth={1.5} dot={false} strokeDasharray="4 2"
                    />
                    <Area
                        yAxisId="climate" type="monotone" dataKey="rain" name="Rain (mm)"
                        fill="url(#rainGrad)" stroke="#38bdf8" strokeWidth={1.5}
                    />
                    <Line
                        yAxisId="climate" type="monotone" dataKey="humidity" name="Humidity (%)"
                        stroke="#a78bfa" strokeWidth={1.5} dot={false} strokeDasharray="6 3"
                    />
                </ComposedChart>
            </ResponsiveContainer>
        </div>
    );
};

export default ClimatePanel;
