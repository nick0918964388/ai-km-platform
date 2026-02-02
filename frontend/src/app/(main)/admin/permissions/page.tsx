'use client';

import { useState } from 'react';
import {
  Save,
  Locked,
  Unlocked,
  View,
  UserMultiple,
  Notification,
  CheckmarkFilled,
  Add,
  TrashCan,
  Edit,
} from '@carbon/icons-react';

interface Permission {
  id: string;
  name: string;
  description: string;
  roles: {
    admin: boolean;
    user: boolean;
    guest: boolean;
  };
}

interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'user' | 'guest';
  status: 'active' | 'inactive';
  lastActive: string;
}

const initialPermissions: Permission[] = [
  {
    id: 'chat_access',
    name: '對話功能',
    description: '使用 AI 對話功能',
    roles: { admin: true, user: true, guest: true }
  },
  {
    id: 'chat_history',
    name: '對話歷史',
    description: '查看和管理對話歷史',
    roles: { admin: true, user: true, guest: false }
  },
  {
    id: 'voice_input',
    name: '語音輸入',
    description: '使用語音輸入功能',
    roles: { admin: true, user: true, guest: false }
  },
  {
    id: 'image_upload',
    name: '圖片上傳',
    description: '上傳圖片進行分析',
    roles: { admin: true, user: true, guest: false }
  },
  {
    id: 'export_data',
    name: '匯出資料',
    description: '匯出對話記錄和報告',
    roles: { admin: true, user: false, guest: false }
  },
  {
    id: 'user_management',
    name: '使用者管理',
    description: '新增、編輯、刪除使用者',
    roles: { admin: true, user: false, guest: false }
  },
  {
    id: 'system_settings',
    name: '系統設定',
    description: '修改系統全域設定',
    roles: { admin: true, user: false, guest: false }
  },
  {
    id: 'permission_management',
    name: '權限管理',
    description: '修改角色權限設定',
    roles: { admin: true, user: false, guest: false }
  },
  {
    id: 'kb_view',
    name: '知識庫查詢',
    description: '查詢知識庫內容',
    roles: { admin: true, user: true, guest: true }
  },
  {
    id: 'kb_upload',
    name: '知識庫上傳',
    description: '上傳文件到知識庫',
    roles: { admin: true, user: true, guest: false }
  },
  {
    id: 'kb_delete',
    name: '知識庫刪除',
    description: '刪除知識庫文件',
    roles: { admin: true, user: false, guest: false }
  },
];

const mockUsers: User[] = [
  { id: '1', name: '王小明', email: 'wang@tra.gov.tw', role: 'admin', status: 'active', lastActive: '5 分鐘前' },
  { id: '2', name: '李大偉', email: 'lee@tra.gov.tw', role: 'user', status: 'active', lastActive: '1 小時前' },
  { id: '3', name: '張美玲', email: 'chang@tra.gov.tw', role: 'user', status: 'active', lastActive: '2 小時前' },
  { id: '4', name: '陳建國', email: 'chen@tra.gov.tw', role: 'user', status: 'inactive', lastActive: '3 天前' },
  { id: '5', name: '林志明', email: 'lin@tra.gov.tw', role: 'guest', status: 'active', lastActive: '1 天前' },
];

export default function PermissionsPage() {
  const [permissions, setPermissions] = useState<Permission[]>(initialPermissions);
  const [users] = useState<User[]>(mockUsers);
  const [saved, setSaved] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [activeTab, setActiveTab] = useState<'permissions' | 'users'>('permissions');

  const handleToggle = (permId: string, role: 'admin' | 'user' | 'guest') => {
    if (role === 'admin' && ['user_management', 'permission_management', 'system_settings'].includes(permId)) {
      return;
    }

    setPermissions(prev => prev.map(p =>
      p.id === permId
        ? { ...p, roles: { ...p.roles, [role]: !p.roles[role] } }
        : p
    ));
    setHasChanges(true);
  };

  const handleSave = () => {
    setSaved(true);
    setHasChanges(false);
    setTimeout(() => setSaved(false), 2000);
  };

  const getRoleStats = (role: 'admin' | 'user' | 'guest') => {
    const enabled = permissions.filter(p => p.roles[role]).length;
    return `${enabled}/${permissions.length}`;
  };

  const getRoleBadgeClass = (role: string) => {
    switch (role) {
      case 'admin': return 'badge-admin';
      case 'user': return 'badge-user';
      default: return 'badge-guest';
    }
  };

  const getRoleLabel = (role: string) => {
    switch (role) {
      case 'admin': return '管理員';
      case 'user': return '使用者';
      default: return '訪客';
    }
  };

  return (
    <div style={{
      padding: '2rem',
      height: '100%',
      overflow: 'auto',
      background: 'var(--bg-primary)'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '1.5rem'
      }}>
        <div>
          <h1 style={{
            fontSize: '1.75rem',
            fontWeight: 700,
            color: 'var(--text-primary)',
            marginBottom: '0.25rem'
          }}>
            權限設定
          </h1>
          <p style={{
            fontSize: '0.875rem',
            color: 'var(--text-muted)'
          }}>
            管理系統角色與使用者權限
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn-icon">
            <Notification size={20} />
          </button>
          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={!hasChanges}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0 1.25rem',
              height: 44,
              opacity: hasChanges ? 1 : 0.5
            }}
          >
            <Save size={18} />
            儲存變更
          </button>
        </div>
      </div>

      {/* Success Message */}
      {saved && (
        <div style={{
          padding: '1rem 1.25rem',
          background: 'var(--success-light)',
          border: '1px solid rgba(25, 128, 56, 0.3)',
          borderRadius: 'var(--radius-lg)',
          marginBottom: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem'
        }}>
          <CheckmarkFilled size={20} style={{ color: 'var(--success)' }} />
          <span style={{ color: 'var(--success)', fontWeight: 500 }}>權限設定已成功儲存</span>
        </div>
      )}

      {/* Tabs */}
      <div style={{
        display: 'flex',
        gap: '0.5rem',
        marginBottom: '1.5rem',
        borderBottom: '1px solid var(--border)',
        paddingBottom: '0.5rem'
      }}>
        <button
          onClick={() => setActiveTab('permissions')}
          style={{
            padding: '0.75rem 1.25rem',
            background: activeTab === 'permissions' ? 'var(--accent)' : 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            color: activeTab === 'permissions' ? 'white' : 'var(--text-muted)',
            fontWeight: 500,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            transition: 'all var(--transition-fast)'
          }}
        >
          <Locked size={18} />
          角色權限
        </button>
        <button
          onClick={() => setActiveTab('users')}
          style={{
            padding: '0.75rem 1.25rem',
            background: activeTab === 'users' ? 'var(--accent)' : 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            color: activeTab === 'users' ? 'white' : 'var(--text-muted)',
            fontWeight: 500,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            transition: 'all var(--transition-fast)'
          }}
        >
          <UserMultiple size={18} />
          使用者列表
        </button>
      </div>

      {activeTab === 'permissions' && (
        <>
          {/* Role Summary Cards */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '1.25rem',
            marginBottom: '1.5rem'
          }}>
            {[
              { role: 'admin' as const, label: '管理員', color: 'var(--error)', icon: Locked, desc: '完整系統權限' },
              { role: 'user' as const, label: '使用者', color: 'var(--accent)', icon: Unlocked, desc: '基本功能權限' },
              { role: 'guest' as const, label: '訪客', color: 'var(--text-muted)', icon: View, desc: '僅限查詢功能' },
            ].map(({ role, label, color, icon: Icon, desc }) => (
              <div key={role} className="stat-card">
                <div className="stat-card-header">
                  <span className="stat-card-title">{label}</span>
                  <div className="stat-card-icon" style={{
                    background: role === 'admin' ? 'rgba(255, 107, 107, 0.15)' :
                      role === 'user' ? 'var(--primary-light)' : 'rgba(176, 196, 222, 0.1)'
                  }}>
                    <Icon size={20} style={{ color }} />
                  </div>
                </div>
                <div className="stat-card-value">{getRoleStats(role)}</div>
                <div className="stat-card-change neutral">{desc}</div>
              </div>
            ))}
          </div>

          {/* Permissions Table */}
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '40%' }}>權限項目</th>
                  <th style={{ textAlign: 'center', width: '20%' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                      <Locked size={16} style={{ color: 'var(--error)' }} />
                      管理員
                    </div>
                  </th>
                  <th style={{ textAlign: 'center', width: '20%' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                      <Unlocked size={16} style={{ color: 'var(--accent)' }} />
                      使用者
                    </div>
                  </th>
                  <th style={{ textAlign: 'center', width: '20%' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                      <View size={16} style={{ color: 'var(--text-muted)' }} />
                      訪客
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {permissions.map((perm) => (
                  <tr key={perm.id}>
                    <td>
                      <div style={{ fontWeight: 500, color: 'var(--text-primary)', marginBottom: '0.125rem' }}>
                        {perm.name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {perm.description}
                      </div>
                    </td>
                    {(['admin', 'user', 'guest'] as const).map((role) => {
                      const isLocked = role === 'admin' && ['user_management', 'permission_management', 'system_settings'].includes(perm.id);
                      return (
                        <td key={role} style={{ textAlign: 'center' }}>
                          <label style={{
                            cursor: isLocked ? 'not-allowed' : 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                          }}>
                            <input
                              type="checkbox"
                              checked={perm.roles[role]}
                              onChange={() => handleToggle(perm.id, role)}
                              disabled={isLocked}
                              className="checkbox"
                            />
                          </label>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Info Banner */}
          <div style={{
            marginTop: '1.5rem',
            padding: '1rem 1.25rem',
            background: 'var(--primary-light)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem'
          }}>
            <div style={{
              width: 32,
              height: 32,
              borderRadius: 'var(--radius-md)',
              background: 'var(--accent)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}>
              <Locked size={16} style={{ color: 'white' }} />
            </div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>注意：</strong>
              管理員的核心權限（使用者管理、權限管理、系統設定）無法被停用，以確保系統安全。
            </div>
          </div>
        </>
      )}

      {activeTab === 'users' && (
        <>
          {/* Add User Button */}
          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            marginBottom: '1rem'
          }}>
            <button
              className="btn-primary"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0 1.25rem',
                height: 44
              }}
            >
              <Add size={18} />
              新增使用者
            </button>
          </div>

          {/* Users Table */}
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>使用者</th>
                  <th>角色</th>
                  <th>狀態</th>
                  <th>最後活動</th>
                  <th style={{ width: 100, textAlign: 'center' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <div style={{
                          width: 40,
                          height: 40,
                          borderRadius: '50%',
                          background: 'var(--accent)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: 'white',
                          fontWeight: 600,
                          fontSize: '0.875rem'
                        }}>
                          {user.name.charAt(0)}
                        </div>
                        <div>
                          <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{user.name}</div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{user.email}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${getRoleBadgeClass(user.role)}`}>
                        {getRoleLabel(user.role)}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <div style={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          background: user.status === 'active' ? 'var(--success)' : 'var(--text-muted)'
                        }} />
                        <span style={{
                          color: user.status === 'active' ? 'var(--success)' : 'var(--text-muted)',
                          fontSize: '0.8125rem'
                        }}>
                          {user.status === 'active' ? '活躍' : '停用'}
                        </span>
                      </div>
                    </td>
                    <td style={{ color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
                      {user.lastActive}
                    </td>
                    <td>
                      <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem' }}>
                        <button className="btn-icon" title="編輯">
                          <Edit size={16} />
                        </button>
                        <button className="btn-icon" title="刪除" style={{ color: 'var(--error)' }}>
                          <TrashCan size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
