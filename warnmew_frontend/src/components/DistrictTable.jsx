import React, { useState, useEffect } from 'react';
import { fetchMapData } from '../api';

const DistrictTable = ({ diseaseName }) => {
    const [districts, setDistricts] = useState([]);
    const [sortKey, setSortKey] = useState('confirmed_case_count');
    const [sortAsc, setSortAsc] = useState(false);

    useEffect(() => {
        if (!diseaseName) return;
        fetchMapData(diseaseName)
            .then(res => {
                setDistricts(res.data || []);
            })
            .catch(() => setDistricts([]));
    }, [diseaseName]);

    if (!districts.length) return null;

    const handleSort = (key) => {
        if (sortKey === key) {
            setSortAsc(!sortAsc);
        } else {
            setSortKey(key);
            setSortAsc(false);
        }
    };

    const sorted = [...districts].sort((a, b) => {
        const av = a[sortKey] ?? 0;
        const bv = b[sortKey] ?? 0;
        return sortAsc ? av - bv : bv - av;
    });

    const totalCases = districts.reduce((s, d) => s + (d.confirmed_case_count || 0), 0);
    const maxCases = Math.max(...districts.map(d => d.confirmed_case_count || 0), 1);

    const SortIcon = ({ active, asc }) => (
        <span className="ml-1 inline-block opacity-60">
            {active ? (asc ? '↑' : '↓') : '⇅'}
        </span>
    );

    return (
        <div className="chart-glass p-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
                <div>
                    <h3 className="text-xl font-bold text-white">District Rankings</h3>
                    <p className="text-slate-500 text-sm mt-1">
                        Click column headers to sort • Total: <span className="text-kerala-400 font-semibold">{totalCases}</span> cases
                    </p>
                </div>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-slate-700/50">
                            <th className="text-left py-3 px-4 text-xs font-bold text-slate-500 uppercase tracking-wider">
                                Rank
                            </th>
                            <th
                                className="text-left py-3 px-4 text-xs font-bold text-slate-500 uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                                onClick={() => handleSort('district')}
                            >
                                District <SortIcon active={sortKey === 'district'} asc={sortAsc} />
                            </th>
                            <th
                                className="text-right py-3 px-4 text-xs font-bold text-slate-500 uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                                onClick={() => handleSort('confirmed_case_count')}
                            >
                                Cases <SortIcon active={sortKey === 'confirmed_case_count'} asc={sortAsc} />
                            </th>
                            <th className="text-left py-3 px-4 text-xs font-bold text-slate-500 uppercase tracking-wider w-1/3">
                                Distribution
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {sorted.map((d, i) => {
                            const cases = d.confirmed_case_count || 0;
                            const pct = maxCases > 0 ? (cases / maxCases) * 100 : 0;
                            const rankColor =
                                i === 0 ? 'text-red-400 font-bold' :
                                    i === 1 ? 'text-orange-400 font-semibold' :
                                        i === 2 ? 'text-yellow-400 font-semibold' :
                                            'text-slate-400';
                            return (
                                <tr
                                    key={d.district}
                                    className="border-b border-slate-800/40 hover:bg-kerala-900/30 transition-colors"
                                >
                                    <td className={`py-3 px-4 ${rankColor}`}>
                                        {i < 3 ? ['🥇', '🥈', '🥉'][i] : `#${i + 1}`}
                                    </td>
                                    <td className="py-3 px-4 text-white font-medium">{d.district}</td>
                                    <td className="py-3 px-4 text-right font-mono text-white font-bold">{cases}</td>
                                    <td className="py-3 px-4">
                                        <div className="w-full bg-slate-800/60 rounded-full h-2.5 overflow-hidden">
                                            <div
                                                className="h-full rounded-full transition-all duration-500"
                                                style={{
                                                    width: `${pct}%`,
                                                    background: pct > 75 ? 'linear-gradient(90deg, #ef4444, #dc2626)'
                                                        : pct > 40 ? 'linear-gradient(90deg, #f59e0b, #d97706)'
                                                            : 'linear-gradient(90deg, #2eb860, #22c55e)',
                                                }}
                                            />
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default DistrictTable;
