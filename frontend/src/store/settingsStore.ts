import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface SettingsState {
  llmProvider: string;
  kiprisEnabled: boolean;
  columnMapping: {
    original_name: string;
    refined_name: string;
    keywords: string;
    naver_category: string;
    coupang_category: string;
  };
  setLlmProvider: (provider: string) => void;
  setKiprisEnabled: (enabled: boolean) => void;
  setColumnMapping: (mapping: Partial<SettingsState['columnMapping']>) => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      llmProvider: 'gemini',
      kiprisEnabled: true,
      columnMapping: {
        original_name: '',
        refined_name: '정제상품명',
        keywords: '키워드',
        naver_category: '네이버카테고리',
        coupang_category: '쿠팡카테고리',
      },
      setLlmProvider: (provider) => set({ llmProvider: provider }),
      setKiprisEnabled: (enabled) => set({ kiprisEnabled: enabled }),
      setColumnMapping: (mapping) => 
        set((state) => ({ columnMapping: { ...state.columnMapping, ...mapping } })),
    }),
    {
      name: 'settings-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
);
