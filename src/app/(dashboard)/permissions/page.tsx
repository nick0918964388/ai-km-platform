"use client";

import { useState } from "react";
import AppHeader from "@/components/AppHeader";
import {
  DataTable,
  Table,
  TableHead,
  TableRow,
  TableHeader,
  TableBody,
  TableCell,
  TableToolbar,
  TableToolbarContent,
  TableToolbarSearch,
  TableContainer,
  Button,
  Modal,
  TextInput,
  Checkbox,
  Tag,
  OverflowMenu,
  OverflowMenuItem,
  Accordion,
  AccordionItem,
  Stack,
} from "@carbon/react";
import { Add, Security, Locked } from "@carbon/icons-react";

interface Role {
  id: string;
  name: string;
  description: string;
  userCount: number;
  permissions: string[];
}

const mockRoles: Role[] = [
  {
    id: "1",
    name: "系統管理員",
    description: "擁有系統所有權限",
    userCount: 2,
    permissions: ["all"],
  },
  {
    id: "2",
    name: "知識管理員",
    description: "管理知識庫內容與分類",
    userCount: 5,
    permissions: ["kb.read", "kb.write", "kb.delete", "kb.manage"],
  },
  {
    id: "3",
    name: "部門主管",
    description: "管理部門成員與檢視報表",
    userCount: 8,
    permissions: ["kb.read", "user.view", "report.view"],
  },
  {
    id: "4",
    name: "一般使用者",
    description: "基本知識庫存取權限",
    userCount: 45,
    permissions: ["kb.read", "chat.use"],
  },
];

const permissionCategories = [
  {
    category: "知識庫",
    permissions: [
      { id: "kb.read", name: "檢視知識庫", description: "可以瀏覽知識庫內容" },
      { id: "kb.write", name: "編輯知識庫", description: "可以新增與編輯知識條目" },
      { id: "kb.delete", name: "刪除知識", description: "可以刪除知識條目" },
      { id: "kb.manage", name: "管理知識庫", description: "可以管理分類與標籤" },
    ],
  },
  {
    category: "AI 對話",
    permissions: [
      { id: "chat.use", name: "使用 AI 對話", description: "可以使用 AI 問答功能" },
      { id: "chat.history", name: "檢視對話紀錄", description: "可以檢視歷史對話" },
      { id: "chat.export", name: "匯出對話", description: "可以匯出對話內容" },
    ],
  },
  {
    category: "使用者管理",
    permissions: [
      { id: "user.view", name: "檢視使用者", description: "可以檢視使用者列表" },
      { id: "user.create", name: "建立使用者", description: "可以新增使用者帳號" },
      { id: "user.edit", name: "編輯使用者", description: "可以修改使用者資料" },
      { id: "user.delete", name: "刪除使用者", description: "可以刪除使用者帳號" },
    ],
  },
  {
    category: "報表與分析",
    permissions: [
      { id: "report.view", name: "檢視報表", description: "可以檢視使用統計報表" },
      { id: "report.export", name: "匯出報表", description: "可以匯出報表資料" },
    ],
  },
  {
    category: "系統設定",
    permissions: [
      { id: "settings.view", name: "檢視設定", description: "可以檢視系統設定" },
      { id: "settings.edit", name: "修改設定", description: "可以修改系統設定" },
    ],
  },
];

const headers = [
  { key: "name", header: "角色名稱" },
  { key: "description", header: "描述" },
  { key: "userCount", header: "使用者數" },
  { key: "permissions", header: "權限" },
  { key: "actions", header: "操作" },
];

export default function PermissionsPage() {
  const [roles, setRoles] = useState<Role[]>(mockRoles);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<Role | null>(null);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);

  const handleAddRole = () => {
    setEditingRole(null);
    setSelectedPermissions([]);
    setIsModalOpen(true);
  };

  const handleEditRole = (role: Role) => {
    setEditingRole(role);
    setSelectedPermissions(role.permissions);
    setIsModalOpen(true);
  };

  const handleDeleteRole = (roleId: string) => {
    setRoles(roles.filter((r) => r.id !== roleId));
  };

  const togglePermission = (permId: string) => {
    setSelectedPermissions((prev) =>
      prev.includes(permId)
        ? prev.filter((p) => p !== permId)
        : [...prev, permId]
    );
  };

  return (
    <div className="min-h-screen bg-carbon-gray-10">
      <AppHeader />
      <div className="pt-12">
        <div className="max-w-7xl mx-auto p-6">
          <div className="flex items-center gap-3 mb-6">
            <Security size={32} className="text-carbon-blue-60" />
            <div>
              <h1 className="text-2xl font-semibold text-carbon-gray-100">
                權限管理
              </h1>
              <p className="text-carbon-gray-60">
                管理角色與權限設定
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Roles Table */}
            <div className="lg:col-span-2">
              <div className="bg-white rounded-lg border border-carbon-gray-20">
                <DataTable rows={roles} headers={headers}>
                  {({
                    rows,
                    headers,
                    getHeaderProps,
                    getRowProps,
                    getTableProps,
                    getToolbarProps,
                    getTableContainerProps,
                  }) => (
                    <TableContainer {...getTableContainerProps()}>
                      <TableToolbar {...getToolbarProps()}>
                        <TableToolbarContent>
                          <TableToolbarSearch
                            placeholder="搜尋角色..."
                            persistent
                          />
                          <Button
                            kind="primary"
                            renderIcon={Add}
                            onClick={handleAddRole}
                          >
                            新增角色
                          </Button>
                        </TableToolbarContent>
                      </TableToolbar>
                      <Table {...getTableProps()}>
                        <TableHead>
                          <TableRow>
                            {headers.map((header, index) => {
                              const headerProps = getHeaderProps({ header });
                              return (
                                <TableHeader
                                  {...headerProps}
                                  key={`header-${index}`}
                                >
                                  {header.header}
                                </TableHeader>
                              );
                            })}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {rows.map((row) => {
                            const role = roles.find((r) => r.id === row.id);
                            const rowProps = getRowProps({ row });
                            return (
                              <TableRow {...rowProps} key={row.id}>
                                <TableCell>
                                  <div className="flex items-center gap-2">
                                    <Locked size={16} />
                                    <span className="font-medium">
                                      {role?.name}
                                    </span>
                                  </div>
                                </TableCell>
                                <TableCell>{role?.description}</TableCell>
                                <TableCell>
                                  <Tag type="blue">{role?.userCount} 人</Tag>
                                </TableCell>
                                <TableCell>
                                  <div className="flex flex-wrap gap-1">
                                    {role?.permissions.includes("all") ? (
                                      <Tag type="purple">全部權限</Tag>
                                    ) : (
                                      <Tag type="gray">
                                        {role?.permissions.length} 項
                                      </Tag>
                                    )}
                                  </div>
                                </TableCell>
                                <TableCell>
                                  <OverflowMenu flipped>
                                    <OverflowMenuItem
                                      itemText="編輯"
                                      onClick={() =>
                                        role && handleEditRole(role)
                                      }
                                    />
                                    <OverflowMenuItem
                                      itemText="複製"
                                      onClick={() => {}}
                                    />
                                    <OverflowMenuItem
                                      itemText="刪除"
                                      isDelete
                                      onClick={() =>
                                        role && handleDeleteRole(role.id)
                                      }
                                    />
                                  </OverflowMenu>
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  )}
                </DataTable>
              </div>
            </div>

            {/* Permission Overview */}
            <div className="lg:col-span-1">
              <div className="bg-white rounded-lg border border-carbon-gray-20 p-4">
                <h3 className="text-lg font-medium mb-4">權限說明</h3>
                <Accordion>
                  {permissionCategories.map((cat) => (
                    <AccordionItem key={cat.category} title={cat.category}>
                      <div className="space-y-2">
                        {cat.permissions.map((perm) => (
                          <div
                            key={perm.id}
                            className="p-2 bg-carbon-gray-10 rounded"
                          >
                            <p className="font-medium text-sm">{perm.name}</p>
                            <p className="text-xs text-carbon-gray-60">
                              {perm.description}
                            </p>
                          </div>
                        ))}
                      </div>
                    </AccordionItem>
                  ))}
                </Accordion>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Add/Edit Role Modal */}
      <Modal
        open={isModalOpen}
        onRequestClose={() => setIsModalOpen(false)}
        modalHeading={editingRole ? "編輯角色" : "新增角色"}
        primaryButtonText={editingRole ? "儲存" : "新增"}
        secondaryButtonText="取消"
        onRequestSubmit={() => setIsModalOpen(false)}
        size="lg"
      >
        <Stack gap={5} className="mt-4">
          <TextInput
            id="roleName"
            labelText="角色名稱"
            placeholder="請輸入角色名稱"
            defaultValue={editingRole?.name}
          />
          <TextInput
            id="roleDescription"
            labelText="角色描述"
            placeholder="請輸入角色描述"
            defaultValue={editingRole?.description}
          />

          <div>
            <p className="text-sm font-medium mb-3">權限設定</p>
            {permissionCategories.map((cat) => (
              <div key={cat.category} className="mb-4">
                <p className="text-sm text-carbon-gray-70 mb-2">
                  {cat.category}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {cat.permissions.map((perm) => (
                    <Checkbox
                      key={perm.id}
                      id={perm.id}
                      labelText={perm.name}
                      checked={selectedPermissions.includes(perm.id)}
                      onChange={() => togglePermission(perm.id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Stack>
      </Modal>
    </div>
  );
}
