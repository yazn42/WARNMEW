import { createContext, useContext, useState, useEffect } from 'react';
import { login as apiLogin, register as apiRegister, getUserProfile } from '../api';

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    // Check for existing token on mount
    useEffect(() => {
        const token = localStorage.getItem('access_token');
        if (token) {
            getUserProfile()
                .then((res) => setUser(res.data))
                .catch(() => {
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                })
                .finally(() => setLoading(false));
        } else {
            setLoading(false);
        }
    }, []);

    const loginUser = async (username, password) => {
        const res = await apiLogin(username, password);
        localStorage.setItem('access_token', res.data.access);
        localStorage.setItem('refresh_token', res.data.refresh);

        const profileRes = await getUserProfile();
        setUser(profileRes.data);
        return profileRes.data;
    };

    const registerUser = async (data) => {
        const res = await apiRegister(data);
        return res.data;
    };

    const logout = () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        setUser(null);
    };

    const value = {
        user,
        loading,
        login: loginUser,
        register: registerUser,
        logout,
        isAuthenticated: !!user,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
