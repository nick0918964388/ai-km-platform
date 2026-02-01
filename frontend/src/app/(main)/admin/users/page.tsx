'use client';

import { useState } from 'react';
import { Add, Edit, TrashCan, Search } from '@carbon/icons-react';
import { User, UserRole } from '@/types';
import UserModal from '@/components/ui/UserModal';

// Demo users
const initialUsers: User[] = [
  { id: '1', name: '管理員', email: 'admin@example.com', role: 'admin', createdAt: new Date('2024-01-01') },
  { id: '2', name: '技師 A', email: 'tech.a@example.com', role: 'user', createdAt: new Date('2024-02-15') },
  { id: '3', name: '技師 B', email: 'tech.b@example.com', role: 'user', createdAt: new Date('2024-03-01') },
  { id: '4', name: '訪客', email: 'guest@example.com', role: 'guest', createdAt: new Date('2024-04-01') },
];

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>(initialUsers);
  const [search, setSearch] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);

  const filteredUsers = users.filter(u => 
    u.name.toLowerCase().includes(search.toLowerCase()) ||
    u.email.toLowerCase().includes(search.toLowerCase())
  );

  const handleDelete = (id: string) => {
    if (confirm('確定要刪除此使用者？')) {
      setUsers(users.filter(u => u.id !== id));
    }
  };

  const handleSave = (userData: Partial<User> & { password?: string }) => {
    if (userData.id) {
      // Update existing user
      setUsers(users.map(u => 
        u.id === userData.id 
          ? { ...u, name: userData.name!, email: userData.email!, role: userData.role! }
          : u
      ));
    } else {
      // Create new user
      const newUser: User = {
        id: Date.now().toString(),
        name: userData.name!,
        email: userData.email!,
        role: userData.role!,
        createdAt: new Date(),
      };
      setUsers([...users, newUser]);
    }
    setEditingUser(null);
  };

  const handleEdit = (user: User) => {
    setEditingUser(user);
    setShowModal(true);
  };

  const handleAddNew = () => {
    setEditingUser(null);
    setShowModal(true);
  };

  const getRoleBadgeClass = (role: UserRole) => {
    switch (role) {
      case 'admin': return 'badge badge-admin';
      case 'user': return 'badge badge-user';
      default: return 'badge badge-guest';
    }
  };

  const getRoleLabel = (role: UserRole) => {
    switch (role) {
      case 'admin': return '管理員';
      case 'user': return '使用者';
      default: return '訪客';
    }
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
          使用者管理
        </h1>
        <button className="btn btn-primary" onClick={handleAddNew}>
          <Add size={16} />
          新增使用者
        </button>
      </div>

      {/* Search */}
      <div className="settings-section" style={{ padding: '1rem' }}>
        <div style={{ position: 'relative' }}>
          <Search 
            size={18} 
            style={{ 
              position: 'absolute', 
              left: 12, 
              top: '50%', 
              transform: 'translateY(-50%)',
              color: 'var(--text-secondary)'
            }} 
          />
          <input
            type="text"
            className="form-input"
            placeholder="搜尋使用者..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ paddingLeft: 40 }}
          />
        </div>
      </div>

      {/* Users Table */}
      <div className="settings-section" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>名稱</th>
              <th>電子郵件</th>
              <th>角色</th>
              <th>建立日期</th>
              <th style={{ width: 100 }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.map((user) => (
              <tr key={user.id}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{
                      width: 32,
                      height: 32,
                      borderRadius: '50%',
                      background: 'var(--primary)',
                      color: 'white',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '0.75rem',
                      fontWeight: 500
                    }}>
                      {user.name.charAt(0)}
                    </div>
                    {user.name}
                  </div>
                </td>
                <td>{user.email}</td>
                <td>
                  <span className={getRoleBadgeClass(user.role)}>
                    {getRoleLabel(user.role)}
                  </span>
                </td>
                <td>{user.createdAt.toLocaleDateString('zh-TW')}</td>
                <td>
                  <div style={{ display: 'flex', gap: '0.25rem' }}>
                    <button 
                      className="input-btn" 
                      title="編輯"
                      onClick={() => handleEdit(user)}
                    >
                      <Edit size={16} />
                    </button>
                    <button 
                      className="input-btn" 
                      title="刪除"
                      onClick={() => handleDelete(user.id)}
                      style={{ color: '#da1e28' }}
                    >
                      <TrashCan size={16} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filteredUsers.length === 0 && (
          <div style={{ 
            padding: '3rem', 
            textAlign: 'center', 
            color: 'var(--text-secondary)' 
          }}>
            找不到符合的使用者
          </div>
        )}
      </div>

      {/* Stats */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(3, 1fr)', 
        gap: '1rem',
        marginTop: '1.5rem'
      }}>
        {[
          { label: '管理員', count: users.filter(u => u.role === 'admin').length, color: '#da1e28' },
          { label: '使用者', count: users.filter(u => u.role === 'user').length, color: '#0043ce' },
          { label: '訪客', count: users.filter(u => u.role === 'guest').length, color: '#525252' },
        ].map((stat) => (
          <div key={stat.label} className="settings-section" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 600, color: stat.color }}>
              {stat.count}
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
              {stat.label}
            </div>
          </div>
        ))}
      </div>

      {/* User Modal */}
      <UserModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false);
          setEditingUser(null);
        }}
        onSave={handleSave}
        user={editingUser}
      />
    </div>
  );
}
