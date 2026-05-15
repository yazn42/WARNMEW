import React from 'react';

const DiseaseSelect = ({ diseases, selected, onChange }) => {
    return (
        <div className="relative">
            <select
                value={selected}
                onChange={(e) => onChange(e.target.value)}
                className="select-premium w-full"
            >
                <option value="" disabled className="bg-kerala-950 text-slate-400">
                    — Select a Disease —
                </option>
                {diseases.map((d) => (
                    <option key={d} value={d} className="bg-kerala-950 text-slate-200">
                        {d}
                    </option>
                ))}
            </select>

            {/* Arrow Icon */}
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4">
                <div className="w-8 h-8 rounded-lg bg-kerala-800/50 flex items-center justify-center">
                    <svg
                        className="w-4 h-4 text-gold"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2.5}
                            d="M19 9l-7 7-7-7"
                        />
                    </svg>
                </div>
            </div>
        </div>
    );
};

export default DiseaseSelect;
