'use client';

import { useState } from 'react';
import { Save, Locked, Unlocked, View, Edit, TrashCan, Add } from '@carbon/icons-react';

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
    id: 'api_access',
    name: 'API 存取',
    description: '使用 API 金鑰存取系統',
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
  {
    id: 'kb_manage',
    name: '知識庫管理',
    description: '完整管理知識庫',
    roles: { admin: true, user: false, guest: false }
  },
];

export default function PermissionsPage() {
  const [permissions, setPermissions] = useState<Permission[]>(initialPermissions);
  const [saved, setSaved] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  const handleToggle = (permId: string, role: 'admin' | 'user' | 'guest') => {
    // Prevent disabling admin permissions for admin role
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
    // TODO: Save to backend
    setSaved(true);
    setHasChanges(false);
    setTimeout(() => setSaved(false), 2000);
  };

  const getRoleStats = (role: 'admin' | 'user' | 'guest') => {
    const enabled = permissions.filter(p => p.roles[role]).length;
    return `${enabled}/${permissions.length}`;
  };

  return (
    <div className="settings-container" style={{ maxWidth: 1000 }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '1.5rem'
      }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 600 }}>
          權限管理
        </h1>
        <button 
          className="btn btn-primary" 
          onClick={handleSave}
          disabled={!hasChanges}
        >
          <Save size={16} />
          儲存變更
        </button>
      </div>

      {saved && (
        <div style={{
          padding: '0.75rem 1rem',
          background: '#defbe6',
          color: '#198038',
          borderRadius: 8,
          marginBottom: '1rem',
          fontSize: '0.875rem'
        }}>
          ✓ 權限設定已儲存
        </div>
      )}

      {/* Role Summary */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(3, 1fr)', 
        gap: '1rem',
        marginBottom: '1.5rem'
      }}>
        {[
          { role: 'admin' as const, label: '管理員', color: '#da1e28', icon: Locked },
          { role: 'user' as const, label: '使用者', color: '#0043ce', icon: Unlocked },
          { role: 'guest' as const, label: '訪客', color: '#525252', icon: View },
        ].map(({ role, label, color, icon: Icon }) => (
          <div key={role} className="settings-section" style={{ textAlign: 'center' }}>
            <Icon size={24} style={{ color, marginBottom: '0.5rem' }} />
            <div style={{ fontWeight: 600, color }}>{label}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              {getRoleStats(role)} 權限
            </div>
          </div>
        ))}
      </div>

      {/* Permissions Table */}
      <div className="settings-section" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '35%' }}>權限項目</th>
              <th style={{ textAlign: 'center' }}>管理員</th>
              <th style={{ textAlign: 'center' }}>使用者</th>
              <th style={{ textAlign: 'center' }}>訪客</th>
            </tr>
          </thead>
          <tbody>
            {permissions.map((perm) => (
              <tr key={perm.id}>
                <td>
                  <div style={{ fontWeight: 500 }}>{perm.name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    {perm.description}
                  </div>
                </td>
                {(['admin', 'user', 'guest'] as const).map((role) => (
                  <td key={role} style={{ textAlign: 'center' }}>
                    <label style={{ cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={perm.roles[role]}
                        onChange={() => handleToggle(perm.id, role)}
                        disabled={role === 'admin' && ['user_management', 'permission_management', 'system_settings'].includes(perm.id)}
                        style={{ 
                          width: 20, 
                          height: 20,
                          accentColor: 'var(--primary)'
                        }}
                      />
                    </label>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Info */}
      <div style={{ 
        marginTop: '1.5rem',
        padding: '1rem',
        background: '#edf5ff',
        borderRadius: 8,
        fontSize: '0.875rem',
        color: '#0043ce',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem'
      }}>
        <Locked size={20} style={{ flexShrink: 0, marginTop: 2 }} />
        <div>
          <strong>注意：</strong>管理員的核心權限（使用者管理、權限管理、系統設定）無法被停用，以確保系統安全。
        </div>
      </div>
    </div>
  );
}
