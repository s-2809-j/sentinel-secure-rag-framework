import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axiosInstance from '../api/axiosInstance';

// Role → allowed nav items
const NAV_ITEMS: { label: string; path: string; roles: string[] }[] = [
  { label: 'Chat', path: '/chat', roles: ['VIEWER', 'ANALYST', 'ADMIN'] },
  { label: 'Analyze', path: '/analyze', roles: ['ANALYST', 'ADMIN'] },
  { label: 'Upload', path: '/upload', roles: ['ANALYST', 'ADMIN'] },
  { label: 'Audit', path: '/audit', roles: ['ADMIN'] },
  { label: 'Users', path: '/admin/users', roles: ['ADMIN'] },
];

const ROLE_COLORS: Record<string, string> = {
  ADMIN: 'bg-sentinel-accent/10 text-sentinel-accent border-sentinel-accent/30',
  ANALYST: 'bg-violet-500/10 text-violet-400 border-violet-500/30',
  VIEWER: 'bg-sentinel-muted/10 text-sentinel-muted border-sentinel-muted/30',
};

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await axiosInstance.post('/api/v1/auth/logout');
    } catch {
      // Best-effort — clear state regardless
    }
    logout();                          // AuthContext already clears localStorage via setUserBoth(null)
    navigate('/login', { replace: true });
  };

  if (!user) return null;

  const visibleLinks = NAV_ITEMS.filter((item) => item.roles.includes(user.role));
  const roleColor = ROLE_COLORS[user.role] ?? ROLE_COLORS['VIEWER'];

  return (
    <nav className="sticky top-0 z-50 border-b border-sentinel-border/40 bg-sentinel-dark/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sentinel-accent to-violet-500 flex items-center justify-center shadow-accent">
              <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4z" />
              </svg>
            </div>
            <span className="text-sentinel-light font-bold text-lg tracking-tight">
              Sentinel
            </span>
          </div>

          {/* Nav links */}
          <div className="hidden sm:flex items-center gap-1">
            {visibleLinks.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  isActive ? 'nav-link-active' : 'nav-link'
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>

          {/* User info + logout */}
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2">
              <span className="text-sentinel-muted text-sm">{user.username}</span>
              <span className={`badge border text-xs ${roleColor}`}>
                {user.role}
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="btn-danger text-xs px-3 py-1.5"
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
