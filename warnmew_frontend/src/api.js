import axios from 'axios';

const API = axios.create({
    baseURL: 'http://localhost:8000/api/',
});

// --- JWT Token Interceptors ---

// Attach Authorization header to every request
API.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Handle 401 responses - try token refresh
API.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            const refreshToken = localStorage.getItem('refresh_token');
            if (refreshToken) {
                try {
                    const res = await axios.post('http://localhost:8000/api/auth/refresh/', {
                        refresh: refreshToken,
                    });
                    localStorage.setItem('access_token', res.data.access);
                    if (res.data.refresh) {
                        localStorage.setItem('refresh_token', res.data.refresh);
                    }
                    originalRequest.headers.Authorization = `Bearer ${res.data.access}`;
                    return API(originalRequest);
                } catch (refreshError) {
                    // Refresh failed - clear tokens
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                    window.location.href = '/login';
                    return Promise.reject(refreshError);
                }
            }
        }
        return Promise.reject(error);
    }
);

// --- Auth Endpoints ---

export const login = (username, password) =>
    API.post('auth/login/', { username, password });

export const register = (data) =>
    API.post('auth/register/', data);

export const getUserProfile = () =>
    API.get('auth/profile/');

// --- Data Endpoints ---

export const fetchDiseases = () =>
    API.get('diseases/');

export const fetchDistricts = () =>
    API.get('districts/');

export const fetchHistory = (disease, params = {}) => {
    const queryParams = new URLSearchParams();
    if (params.district && params.district !== 'all') {
        queryParams.append('district', params.district);
    }
    if (params.date_from) queryParams.append('date_from', params.date_from);
    if (params.date_to) queryParams.append('date_to', params.date_to);

    const queryString = queryParams.toString();
    return API.get(`history/${disease}/${queryString ? '?' + queryString : ''}`);
};

export const fetchForecast = (disease, params = {}) => {
    const queryParams = new URLSearchParams();
    if (params.district && params.district !== 'all') {
        queryParams.append('district', params.district);
    }
    const queryString = queryParams.toString();
    return API.get(`forecast/${disease}/${queryString ? '?' + queryString : ''}`);
};

export const fetchMapData = (disease, date) =>
    API.get(`map/${disease}/${date ? '?date=' + date : ''}`);

// --- Alert Endpoints ---

export const fetchAlerts = (params = {}) => {
    const queryParams = new URLSearchParams();
    if (params.disease) queryParams.append('disease', params.disease);
    if (params.severity) queryParams.append('severity', params.severity);
    if (params.unread_only) queryParams.append('unread_only', 'true');
    const queryString = queryParams.toString();
    return API.get(`alerts/${queryString ? '?' + queryString : ''}`);
};

export const markAlertRead = (alertId) =>
    API.post(`alerts/${alertId}/read/`);

export const fetchAlertSummary = () =>
    API.get('alerts/summary/');

export default API;
