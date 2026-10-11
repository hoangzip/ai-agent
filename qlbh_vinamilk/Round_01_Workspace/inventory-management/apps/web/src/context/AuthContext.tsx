import React, { createContext, useContext, useState, useEffect } from "react";
import { User } from "@inventory/shared";
import { api } from "../api/client";

interface AuthContextType {
  currentUser: User | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<{ success: boolean; error?: string }>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refreshUser = async () => {
    try {
      const res = await api.getMe();
      if (res.success && res.data) {
        setCurrentUser(res.data);
      } else {
        setCurrentUser(null);
      }
    } catch {
      setCurrentUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshUser();
  }, []);

  const login = async (username: string, password: string) => {
    try {
      const res = await api.login({ username, password });
      if (res.success && res.data?.user) {
        if (res.data.token) {
          localStorage.setItem("vinamilk_auth_token", res.data.token);
        }
        setCurrentUser(res.data.user);
        return { success: true };
      }
      return {
        success: false,
        error: res.error?.message || "Đăng nhập không thành công"
      };
    } catch (err: any) {
      return {
        success: false,
        error: err?.message || "Lỗi kết nối máy chủ"
      };
    }
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch (err) {
      console.warn("Lỗi khi đăng xuất:", err);
    } finally {
      localStorage.removeItem("vinamilk_auth_token");
      setCurrentUser(null);
    }
  };

  const changePassword = async (currentPassword: string, newPassword: string) => {
    try {
      const res = await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword
      });
      if (res.success) {
        if (currentUser) {
          setCurrentUser({
            ...currentUser,
            must_change_password: false
          });
        }
        return { success: true };
      }
      return {
        success: false,
        error: res.error?.message || "Đổi mật khẩu thất bại"
      };
    } catch (err: any) {
      return {
        success: false,
        error: err?.message || "Lỗi kết nối máy chủ"
      };
    }
  };

  return (
    <AuthContext.Provider
      value={{
        currentUser,
        isLoading,
        login,
        logout,
        changePassword,
        refreshUser
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth phải được sử dụng bên trong AuthProvider");
  }
  return context;
};
