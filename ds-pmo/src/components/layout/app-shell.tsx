"use client";

import { Navbar } from "./navbar";
import { WelcomeToast } from "./welcome-toast";
import { SessionExpiryWarning } from "./session-expiry-warning";
import { SessionUserProvider, type SessionUser } from "./session-context";

interface AppShellProps {
  children: React.ReactNode;
  user: SessionUser;
}

export function AppShell({ children, user }: AppShellProps) {
  return (
    <SessionUserProvider value={user}>
      <div className="flex flex-col h-screen overflow-hidden bg-linear-to-br from-white via-gray-50/30 to-gray-50 dark:from-[#1A1D23] dark:via-[#1A1D23] dark:to-[#1E2128]">
        <Navbar user={user} />
        <WelcomeToast userName={user.name} />
        <SessionExpiryWarning />
        <main className="flex-1 min-h-0 overflow-y-auto flex flex-col p-3 sm:p-4 lg:p-6 pb-20 lg:pb-6">
          <div className="animate-page-enter flex-1 min-h-0 flex flex-col">
            {children}
          </div>
        </main>
      </div>
    </SessionUserProvider>
  );
}
