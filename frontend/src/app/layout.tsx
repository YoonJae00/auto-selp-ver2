import '@/styles/globals.css';
import '@/styles/tokens.css';
import AuthProvider from '@/components/AuthProvider';
import TaskPollingProvider from '@/components/TaskPollingProvider';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ko">
      <body>
        <AuthProvider>
          <TaskPollingProvider>
            {children}
          </TaskPollingProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
