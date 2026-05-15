import { useState, useEffect } from 'react';
import { fetchDistricts } from '../api';

export default function FilterBar({ filters, onFilterChange }) {
    const [districts, setDistricts] = useState([]);

    useEffect(() => {
        fetchDistricts()
            .then((res) => setDistricts(res.data))
            .catch(() => { });
    }, []);

    const handleChange = (field, value) => {
        onFilterChange({ ...filters, [field]: value });
    };

    return (
        <div className="filter-bar">
            <div className="filter-group">
                <label className="filter-label">District</label>
                <select
                    className="filter-select"
                    value={filters.district || 'all'}
                    onChange={(e) => handleChange('district', e.target.value)}
                >
                    <option value="all">All Districts</option>
                    {districts.map((d) => (
                        <option key={d} value={d}>{d}</option>
                    ))}
                </select>
            </div>

            {filters.district !== 'all' && (
                <button
                    className="filter-clear"
                    onClick={() => onFilterChange({ district: 'all' })}
                >
                    Clear Filter
                </button>
            )}
        </div>
    );
}
