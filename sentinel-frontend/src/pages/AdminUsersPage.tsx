import { useCallback, useEffect, useState } from 'react';
import axiosInstance from '../api/axiosInstance';
import { useAuth } from '../context/AuthContext';
import type { UserSummary } from '../types';

const ROLES = ['VIEWER', 'ANALYST', 'ADMIN'];

function errorMessage(err: unknown): string {
  const res = (err as { response?: { status?: number; data?: { message?: string } } })?.response;
  if (res?.data?.message) return res.data.message;
  if (res?.status === 403) return 'You are not allowed to do that.';
  if (res?.status === 404) return 'User not found.';
  if (res?.status === 409) return 'This change is not allowed.';
  return 'Something went wrong. Please try again.';
}

export default function AdminUsersPage() {
  const { user: me } = useAuth();
  const [users,    setUsers]    = useState<UserSummary[]>([]);
  const [drafts,   setDrafts]   = useState<Record<string, string>>({});
  const [loading,  setLoading]  = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error,    setError]    = useState('');
  const [success,  setSuccess]  = useState('');

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await axiosInstance.get<UserSummary[]>('/api/v1/admin/users');
      setUsers(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleSave = async (target: UserSummary) => {
    const role = drafts[target.id];
    if (!role || role === target.role) return;
    if (!window.confirm(`Change ${target.username} from ${target.role} to ${role}?`)) return;

    setSavingId(target.id);
    setError('');
    setSuccess('');
    try {
      const { data } = await axiosInstance.patch<UserSummary>(
        `/api/v1/admin/users/${target.id}/role`,
        { role },
      );
      setUsers((prev) => prev.map((u) => (u.id === data.id ? data : u)));
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[target.id];
        return next;
      });
      setSuccess(`${data.username} is now ${data.role}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-10 animate-fade-in">
      <div className="flex items-center justify-between mb-8 flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-sentinel-light">User Management</h1>
          <p className="text-sentinel-muted text-sm mt-1">
            Promote or demote users. A changed role applies on that user's next request.
          </p>
        </div>
        <button
          onClick={fetchUsers}
          disabled={loading}
          className="btn-secondary flex items-center gap-2 px-4 py-2 text-sm"
        >
          {loading && <span className="spinner w-4 h-4" />}
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-sentinel-danger/10 border border-sentinel-danger/30 rounded-xl px-4 py-3 text-sentinel-danger text-sm mb-6">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-sentinel-success/10 border border-sentinel-success/30 rounded-xl px-4 py-3 text-sentinel-success text-sm mb-6">
          {success}
        </div>
      )}

      <div className="glass-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-sentinel-border/40 bg-sentinel-surface/40">
                {['Username', 'Email', 'Status', 'Role', ''].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left font-semibold text-sentinel-muted text-xs uppercase tracking-wider whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u, idx) => {
                const isSelf  = u.username === me?.username;
                const draft   = drafts[u.id] ?? u.role;
                const changed = draft !== u.role;
                return (
                  <tr
                    key={u.id}
                    className={`border-b border-sentinel-border/20 ${
                      idx % 2 === 0 ? 'bg-transparent' : 'bg-sentinel-surface/20'
                    }`}
                  >
                    <td className="px-4 py-3 text-sentinel-text">
                      {u.username}
                      {isSelf && <span className="ml-2 text-xs text-sentinel-muted">(you)</span>}
                    </td>
                    <td className="px-4 py-3 text-sentinel-muted">{u.email}</td>
                    <td className="px-4 py-3 text-xs text-sentinel-muted">
                      {u.active ? 'Active' : 'Inactive'}
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={draft}
                        disabled={isSelf || savingId === u.id}
                        onChange={(e) => setDrafts((prev) => ({ ...prev, [u.id]: e.target.value }))}
                        className="bg-sentinel-dark border border-sentinel-border/60 rounded-lg px-3 py-1.5 text-sentinel-light text-sm focus:outline-none focus:border-sentinel-accent disabled:opacity-50 disabled:cursor-not-allowed"
                        title={isSelf ? 'You cannot change your own role' : undefined}
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleSave(u)}
                        disabled={isSelf || !changed || savingId === u.id}
                        className="btn-secondary px-4 py-1.5 text-xs"
                      >
                        {savingId === u.id ? 'Saving…' : 'Save'}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!loading && users.length === 0 && !error && (
                <tr>
                  <td colSpan={5} className="text-center py-12 text-sentinel-muted">
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}