import { create } from 'zustand';
import { User, AuthState } from './authTypes';
import { api } from '@/lib/api';

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  setAuth: (user) => set({ user, isAuthenticated: true, isLoading: false }),
  logout: async () => {
    try {
      await api.post('/api/auth/logout', {});
    } catch (error) {
      console.error('Logout failed', error);
    } finally {
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },
  checkAuth: async () => {
    // If we already have a user, no need to set isLoading to true again
    const current = useAuthStore.getState();
    if (current.user && current.isAuthenticated) {
      set({ isLoading: false });
      return;
    }

    set({ isLoading: true });
    try {
      const user = await api.get<User>('/api/auth/me');
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (error) {
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },
}));

