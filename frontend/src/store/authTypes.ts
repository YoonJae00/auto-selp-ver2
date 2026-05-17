export interface User {
  username: string;
  is_admin: boolean;
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setAuth: (user: User) => void;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}
