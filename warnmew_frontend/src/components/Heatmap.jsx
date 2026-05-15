import React from 'react';
import CalendarHeatmap from 'react-calendar-heatmap';
import 'react-calendar-heatmap/dist/styles.css';
import { Tooltip as ReactTooltip } from 'react-tooltip';
import { format, parseISO, subDays } from 'date-fns';

const Heatmap = ({ data }) => {
    const heatmapData = data.map(d => ({
        date: d.date,
        count: d.confirmed_case_count
    }));

    const today = new Date();
    const maxCount = Math.max(...heatmapData.map(d => d.count || 0), 1);

    // Using purple/violet color scheme instead of green
    const getColorClass = (value) => {
        if (!value || value.count === 0) return 'heatmap-empty';
        const ratio = value.count / maxCount;
        if (ratio < 0.15) return 'heatmap-level-1';
        if (ratio < 0.35) return 'heatmap-level-2';
        if (ratio < 0.55) return 'heatmap-level-3';
        if (ratio < 0.75) return 'heatmap-level-4';
        return 'heatmap-level-5';
    };

    return (
        <div className="w-full">
            <div className="w-full overflow-x-auto pb-2">
                <div className="min-w-[750px]">
                    <CalendarHeatmap
                        startDate={subDays(today, 365)}
                        endDate={today}
                        values={heatmapData}
                        classForValue={getColorClass}
                        tooltipDataAttrs={value => {
                            if (!value || !value.date) return {};
                            const date = format(parseISO(value.date), 'MMM d, yyyy');
                            const count = value.count || 0;
                            return {
                                'data-tooltip-content': `${date}: ${count} case${count !== 1 ? 's' : ''}`,
                                'data-tooltip-id': 'heatmap-tooltip'
                            };
                        }}
                        showWeekdayLabels
                        gutterSize={3}
                    />
                    <ReactTooltip
                        id="heatmap-tooltip"
                        style={{
                            backgroundColor: 'rgba(6, 43, 31, 0.95)',
                            color: '#f1f5f9',
                            borderRadius: '12px',
                            padding: '10px 16px',
                            fontSize: '13px',
                            fontWeight: '500',
                            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
                            border: '1px solid rgba(168, 85, 247, 0.3)',
                            backdropFilter: 'blur(8px)'
                        }}
                    />
                </div>
            </div>

            {/* Legend - Purple/Orange Colors */}
            <div className="flex items-center justify-end gap-2 mt-4 text-xs text-slate-500">
                <span>Less</span>
                <div className="flex gap-1">
                    <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'rgba(168, 85, 247, 0.1)' }}></div>
                    <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'rgba(168, 85, 247, 0.3)' }}></div>
                    <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: 'rgba(168, 85, 247, 0.5)' }}></div>
                    <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: '#a855f7' }}></div>
                    <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: '#9333ea' }}></div>
                    <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: '#7c3aed' }}></div>
                </div>
                <span>More</span>
            </div>

            {/* Heatmap Styles - Purple/Violet Theme */}
            <style>{`
                .react-calendar-heatmap text {
                    font-size: 9px;
                    fill: #64748b;
                    font-weight: 500;
                }
                
                .react-calendar-heatmap .react-calendar-heatmap-month-label {
                    font-size: 10px;
                    fill: #94a3b8;
                    font-weight: 600;
                }
                
                .react-calendar-heatmap rect {
                    rx: 3;
                    ry: 3;
                }
                
                .react-calendar-heatmap rect:hover {
                    stroke: #e5b72a;
                    stroke-width: 2;
                }
                
                .heatmap-empty { fill: rgba(168, 85, 247, 0.05); }
                .heatmap-level-1 { fill: rgba(168, 85, 247, 0.15); }
                .heatmap-level-2 { fill: rgba(168, 85, 247, 0.3); }
                .heatmap-level-3 { fill: rgba(168, 85, 247, 0.5); }
                .heatmap-level-4 { fill: #a855f7; }
                .heatmap-level-5 { fill: #7c3aed; }
            `}</style>
        </div>
    );
};

export default Heatmap;
