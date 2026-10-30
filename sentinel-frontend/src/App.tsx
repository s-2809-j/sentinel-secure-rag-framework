import { useEffect } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { initAxiosAuth } from './api/axiosInstance';
import { useAuth } from './context/AuthContext';
import ProtectedRoute from './routes/ProtectedRoute';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ChatPage from './pages/ChatPage';
import AnalyzePage from './pages/AnalyzePage';
import UploadPage from './pages/UploadPage';
import AuditPage from './pages/AuditPage';
import Navbar from './components/Navbar';
import AdminUsersPage from './pages/AdminUsersPage';
function AppRoutes() {
  const { user, userRef, updateTokens, logout } = useAuth();
  const navigate = useNavigate();

  // Wire Axios interceptors to auth context (once at mount)
  useEffect(() => {
    initAxiosAuth(userRef, updateTokens, logout, navigate);
  }, [userRef, updateTokens, logout, navigate]);

  return (
    <>
      {user && <Navbar />}
      <Routes>
        {/* Public routes — redirect if already authed */}
        <Route
          path="/login"
          element={user ? <Navigate to="/chat" replace /> : <LoginPage />}
        />
        <Route
          path="/register"
          element={user ? <Navigate to="/chat" replace /> : <RegisterPage />}
        />

        {/* Protected — all roles */}
        <Route element={<ProtectedRoute />}>
          <Route path="/chat" element={<ChatPage />} />
        </Route>

        {/* Protected — ANALYST, ADMIN */}
        <Route element={<ProtectedRoute allowedRoles={['ANALYST', 'ADMIN']} />}>
          <Route path="/analyze" element={<AnalyzePage />} />
          <Route path="/upload" element={<UploadPage />} />
        </Route>

        {/* Protected — ADMIN only */}
        <Route element={<ProtectedRoute allowedRoles={['ADMIN']} />}>
          <Route path="/audit" element={<AuditPage />} />
        </Route>
        <Route element={<ProtectedRoute allowedRoles={['ADMIN']} />}>
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/admin/users" element={<AdminUsersPage />} />
        </Route>

        {/* Root redirect */}
        <Route
          path="/"
          element={<Navigate to={user ? '/chat' : '/login'} replace />}
        />

        {/* Catch-all */}
        <Route
          path="*"
          element={<Navigate to={user ? '/chat' : '/login'} replace />}
        />
      </Routes>
    </>
  );
}

export default function App() {
  return <AppRoutes />;
}
