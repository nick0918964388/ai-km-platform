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
  Select,
  SelectItem,
  Tag,
  OverflowMenu,
  OverflowMenuItem,
  Pagination,
  Stack,
} from "@carbon/react";
import { Add, UserAvatar } from "@carbon/icons-react";

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
  department: string;
  status: "active" | "inactive";
  lastLogin: string;
}

const mockUsers: User[] = [
  {
    id: "1",
    username: "admin",
    email: "admin@company.com",
    role: "系統管理員",
    department: "IT部門",
    status: "active",
    lastLogin: "2024-01-15 14:30",
  },
  {
    id: "2",
    username: "john.doe",
    email: "john.doe@company.com",
    role: "一般使用者",
    department: "研發部",
    status: "active",
    lastLogin: "2024-01-15 10:20",
  },
  {
    id: "3",
    username: "jane.smith",
    email: "jane.smith@company.com",
    role: "知識管理員",
    department: "人資部",
    status: "active",
    lastLogin: "2024-01-14 16:45",
  },
  {
    id: "4",
    username: "bob.wilson",
    email: "bob.wilson@company.com",
    role: "一般使用者",
    department: "業務部",
    status: "inactive",
    lastLogin: "2024-01-10 09:00",
  },
  {
    id: "5",
    username: "alice.chen",
    email: "alice.chen@company.com",
    role: "部門主管",
    department: "財務部",
    status: "active",
    lastLogin: "2024-01-15 11:30",
  },
];

const headers = [
  { key: "username", header: "使用者名稱" },
  { key: "email", header: "電子郵件" },
  { key: "role", header: "角色" },
  { key: "department", header: "部門" },
  { key: "status", header: "狀態" },
  { key: "lastLogin", header: "最後登入" },
  { key: "actions", header: "操作" },
];

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>(mockUsers);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const handleAddUser = () => {
    setEditingUser(null);
    setIsModalOpen(true);
  };

  const handleEditUser = (user: User) => {
    setEditingUser(user);
    setIsModalOpen(true);
  };

  const handleDeleteUser = (userId: string) => {
    setUsers(users.filter((u) => u.id !== userId));
  };

  return (
    <div className="min-h-screen bg-carbon-gray-10">
      <AppHeader />
      <div className="pt-12">
        <div className="max-w-7xl mx-auto p-6">
          <div className="flex items-center gap-3 mb-6">
            <UserAvatar size={32} className="text-carbon-blue-60" />
            <div>
              <h1 className="text-2xl font-semibold text-carbon-gray-100">
                帳號管理
              </h1>
              <p className="text-carbon-gray-60">
                管理系統使用者帳號與權限
              </p>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-carbon-gray-20">
            <DataTable rows={users} headers={headers}>
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
                        placeholder="搜尋使用者..."
                        persistent
                      />
                      <Button
                        kind="primary"
                        renderIcon={Add}
                        onClick={handleAddUser}
                      >
                        新增使用者
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
                        const user = users.find((u) => u.id === row.id);
                        const rowProps = getRowProps({ row });
                        return (
                          <TableRow {...rowProps} key={row.id}>
                            <TableCell>
                              <div className="flex items-center gap-2">
                                <UserAvatar size={20} />
                                {user?.username}
                              </div>
                            </TableCell>
                            <TableCell>{user?.email}</TableCell>
                            <TableCell>{user?.role}</TableCell>
                            <TableCell>{user?.department}</TableCell>
                            <TableCell>
                              <Tag
                                type={
                                  user?.status === "active" ? "green" : "gray"
                                }
                              >
                                {user?.status === "active" ? "啟用" : "停用"}
                              </Tag>
                            </TableCell>
                            <TableCell>{user?.lastLogin}</TableCell>
                            <TableCell>
                              <OverflowMenu flipped>
                                <OverflowMenuItem
                                  itemText="編輯"
                                  onClick={() => user && handleEditUser(user)}
                                />
                                <OverflowMenuItem
                                  itemText="重設密碼"
                                  onClick={() => {}}
                                />
                                <OverflowMenuItem
                                  itemText="刪除"
                                  isDelete
                                  onClick={() =>
                                    user && handleDeleteUser(user.id)
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
            <Pagination
              totalItems={users.length}
              pageSize={pageSize}
              pageSizes={[10, 20, 50]}
              page={currentPage}
              onChange={({ page, pageSize }) => {
                setCurrentPage(page);
                setPageSize(pageSize);
              }}
            />
          </div>
        </div>
      </div>

      {/* Add/Edit User Modal */}
      <Modal
        open={isModalOpen}
        onRequestClose={() => setIsModalOpen(false)}
        modalHeading={editingUser ? "編輯使用者" : "新增使用者"}
        primaryButtonText={editingUser ? "儲存" : "新增"}
        secondaryButtonText="取消"
        onRequestSubmit={() => setIsModalOpen(false)}
      >
        <Stack gap={5} className="mt-4">
          <TextInput
            id="username"
            labelText="使用者名稱"
            placeholder="請輸入使用者名稱"
            defaultValue={editingUser?.username}
          />
          <TextInput
            id="email"
            labelText="電子郵件"
            placeholder="請輸入電子郵件"
            defaultValue={editingUser?.email}
          />
          <Select id="role" labelText="角色" defaultValue={editingUser?.role}>
            <SelectItem value="" text="選擇角色" />
            <SelectItem value="系統管理員" text="系統管理員" />
            <SelectItem value="知識管理員" text="知識管理員" />
            <SelectItem value="部門主管" text="部門主管" />
            <SelectItem value="一般使用者" text="一般使用者" />
          </Select>
          <Select
            id="department"
            labelText="部門"
            defaultValue={editingUser?.department}
          >
            <SelectItem value="" text="選擇部門" />
            <SelectItem value="IT部門" text="IT部門" />
            <SelectItem value="研發部" text="研發部" />
            <SelectItem value="人資部" text="人資部" />
            <SelectItem value="業務部" text="業務部" />
            <SelectItem value="財務部" text="財務部" />
          </Select>
          {!editingUser && (
            <TextInput
              id="password"
              type="password"
              labelText="初始密碼"
              placeholder="請輸入初始密碼"
            />
          )}
        </Stack>
      </Modal>
    </div>
  );
}
