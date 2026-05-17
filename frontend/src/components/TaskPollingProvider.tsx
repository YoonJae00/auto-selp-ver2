'use client';

import { useTaskPolling } from '@/hooks/useTaskPolling';

export default function TaskPollingProvider({ children }: { children: React.ReactNode }) {
  useTaskPolling();
  return <>{children}</>;
}
