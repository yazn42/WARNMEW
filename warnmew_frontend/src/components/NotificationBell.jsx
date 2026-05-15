import { useState, useEffect, useRef } from 'react';
import { fetchAlerts, fetchAlertSummary, markAlertRead } from '../api';

export default function NotificationBell() {
    const [isOpen, setIsOpen] = useState(false);
    const [alerts, setAlerts] = useState([]);
    const [summary, setSummary] = useState({ unread: 0, critical: 0, high: 0 });
    const panelRef = useRef(null);

    useEffect(() => {
        loadSummary();
        const interval = setInterval(loadSummary, 30000); // Poll every 30s
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (isOpen) loadAlerts();
    }, [isOpen]);

    // Close panel when clicking outside
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (panelRef.current && !panelRef.current.contains(e.target)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const loadSummary = async () => {
        try {
            const res = await fetchAlertSummary();
            setSummary(res.data);
        } catch { /* ignore */ }
    };

    const loadAlerts = async () => {
        try {
            const res = await fetchAlerts({ unread_only: true });
            setAlerts(res.data);
        } catch { /* ignore */ }
    };

    const handleMarkRead = async (alertId) => {
        try {
            await markAlertRead(alertId);
            setAlerts((prev) => prev.filter((a) => a.id !== alertId));
            setSummary((prev) => ({ ...prev, unread: Math.max(0, prev.unread - 1) }));
        } catch { /* ignore */ }
    };

    const severityColors = {
        critical: '#ff4757',
        high: '#ff6b35',
        medium: '#ffa502',
        low: '#2ed573',
    };

    return (
        <div className="notification-bell-wrapper" ref={panelRef}>
            <button
                className="notification-bell-btn"
                onClick={() => setIsOpen(!isOpen)}
                title="Notifications"
            >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                {summary.unread > 0 && (
                    <span className="notification-badge">{summary.unread}</span>
                )}
            </button>

            {isOpen && (
                <div className="notification-panel">
                    <div className="notification-panel-header">
                        <h3>Alerts</h3>
                        <span className="notification-count">{summary.unread} unread</span>
                    </div>

                    <div className="notification-list">
                        {alerts.length === 0 ? (
                            <div className="notification-empty">
                                <p>No unread alerts</p>
                            </div>
                        ) : (
                            alerts.map((alert) => (
                                <div
                                    key={alert.id}
                                    className="notification-item"
                                    style={{ borderLeft: `3px solid ${severityColors[alert.severity]}` }}
                                >
                                    <div className="notification-item-header">
                                        <span
                                            className="notification-severity"
                                            style={{ color: severityColors[alert.severity] }}
                                        >
                                            {alert.severity.toUpperCase()}
                                        </span>
                                        <span className="notification-time">
                                            {new Date(alert.created_at).toLocaleDateString()}
                                        </span>
                                    </div>
                                    <p className="notification-title">{alert.title}</p>
                                    <p className="notification-message">{alert.message}</p>
                                    <button
                                        className="notification-dismiss"
                                        onClick={() => handleMarkRead(alert.id)}
                                    >
                                        Dismiss
                                    </button>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
