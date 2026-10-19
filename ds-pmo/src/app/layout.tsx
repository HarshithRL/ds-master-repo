import type { Metadata } from "next";
import NextTopLoader from "nextjs-toploader";
import { Toaster } from "sonner";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "ETEX PMO Tracker",
  description: "ETEX Global PMO Project Portfolio Management",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased min-h-screen">
        <NextTopLoader color="#E8713A" showSpinner={false} height={2} shadow={false} />
        <ThemeProvider>
          {children}
          <Toaster
            position="bottom-right"
            richColors
            closeButton
            theme="system"
            toastOptions={{
              classNames: {
                toast: "etex-toast",
              },
            }}
          />
        </ThemeProvider>
      </body>
    </html>
  );
}
