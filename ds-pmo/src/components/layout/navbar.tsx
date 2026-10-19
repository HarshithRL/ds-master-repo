"use client";

import { useState, useEffect, useRef } from "react";
import {
  LayoutDashboard,
  FolderKanban,
  BookOpen,
  Settings,
  Sun,
  Moon,
  ChevronDown,
  User,
  type LucideIcon,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface NavbarUser {
  name: string | null;
  email: string;
  permissions: string[];
  globalRole: string;
  image: string | null;
}

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

// ─── Nav registry ─────────────────────────────────────────────────────────────

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Projects", href: "/projects", icon: FolderKanban },
  { label: "Governance", href: "/resources", icon: BookOpen },
];

const ADMIN_ITEM: NavItem = { label: "Administration", href: "/admin", icon: Settings };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isActive(href: string, pathname: string) {
  return href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(href);
}

function UserAvatar({ initials, image }: { initials: string; image: string | null }) {
  const ring =
    "ring-1 ring-etex-orange/20 hover:ring-etex-orange/40 transition-[box-shadow,transform] duration-200 group-hover:scale-[1.03]";
  if (image) {
    return (
      <img
        src={image}
        alt="User"
        className={cn("w-7 h-7 rounded-sm object-cover shrink-0 shadow-sm", ring)}
      />
    );
  }
  return (
    <div
      className={cn(
        "relative w-7 h-7 rounded-sm flex items-center justify-center text-[11px] font-bold text-white shrink-0 shadow-sm",
        "bg-linear-to-br from-etex-orange via-etex-orange to-etex-orange-dark",
        ring,
      )}
    >
      {initials}
    </div>
  );
}

// ─── Theme Toggle ─────────────────────────────────────────────────────────────

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return <div className="w-9 h-9" />;
  }

  const isDark = theme === "dark";

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="relative w-9 h-9 flex items-center justify-center rounded-sm text-gray-500 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/6 active:scale-95 transition-all duration-200"
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      <Sun
        className={cn(
          "w-4 h-4 absolute transition-all duration-300",
          isDark ? "rotate-0 scale-100 opacity-100" : "rotate-90 scale-0 opacity-0"
        )}
      />
      <Moon
        className={cn(
          "w-4 h-4 absolute transition-all duration-300",
          isDark ? "-rotate-90 scale-0 opacity-0" : "rotate-0 scale-100 opacity-100"
        )}
      />
    </button>
  );
}

// ─── Desktop Nav Link — pill-style active state ───────────────────────────────

function DesktopNavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      className={cn(
        "group relative inline-flex items-center gap-2 h-9 px-3 rounded-sm text-sm select-none",
        "transition-all duration-200 ease-out",
        active
          ? "text-etex-orange font-medium bg-etex-orange/8 dark:bg-etex-orange/12"
          : "text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100/70 dark:hover:bg-white/5",
      )}
    >
      <item.icon
        className={cn(
          "w-4 h-4 shrink-0 transition-transform duration-200",
          active ? "text-etex-orange" : "group-hover:scale-105",
        )}
      />
      <span className="tracking-tight">{item.label}</span>
      {active && (
        <span
          aria-hidden
          className="absolute -bottom-px left-3 right-3 h-0.5 bg-etex-orange shadow-[0_0_8px_rgba(232,113,58,0.5)]"
        />
      )}
    </Link>
  );
}

// ─── Mobile Bottom Nav Link ───────────────────────────────────────────────────

function MobileNavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      className={cn(
        "flex flex-col items-center justify-center gap-0.5 flex-1 py-2 transition-all duration-150",
        active
          ? "text-etex-orange"
          : "text-gray-400 dark:text-gray-500"
      )}
    >
      <item.icon
        className={cn(
          "w-5 h-5 transition-transform duration-150",
          active && "scale-110"
        )}
      />
      <span className="text-[10px] font-medium leading-tight">{item.label}</span>
    </Link>
  );
}

// ─── Navbar ───────────────────────────────────────────────────────────────────

export function Navbar({ user }: { user: NavbarUser }) {
  const pathname = usePathname();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const initials = (user.name || user.email).charAt(0).toUpperCase();
  // Admin link visible to ADMIN globalRole (implicit all-perms) OR anyone
  // with at least one explicit admin-module permission. Previously checked
  // only the permissions array — bug for ADMINs without explicit perms.
  const hasAdminAccess = user.globalRole === "ADMIN" || user.permissions.length > 0;
  const navItems = hasAdminAccess ? [...NAV_ITEMS, ADMIN_ITEM] : NAV_ITEMS;

  useEffect(() => {
    function handleOutsideClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    if (dropdownOpen) document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [dropdownOpen]);

  return (
    <>
      {/* ── Top Navbar — premium layered glass with subtle gradient accent ── */}
      <header className="sticky top-0 z-40 h-14 shrink-0 border-b border-(--border) bg-white/75 dark:bg-[#1A1D23]/75 backdrop-blur-xl supports-backdrop-filter:bg-white/60 dark:supports-backdrop-filter:bg-[#1A1D23]/60">
        {/* Decorative gradient line at the very top — subtle brand accent */}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent via-etex-orange/40 to-transparent"
        />
        {/* Soft ambient glow on the right — adds depth without distraction */}
        <span
          aria-hidden
          className="pointer-events-none absolute -top-12 right-0 h-32 w-72 bg-linear-to-bl from-etex-orange/8 via-transparent to-transparent blur-2xl"
        />

        <div className="relative flex items-center h-full px-4 lg:px-6 gap-1">
          {/* Logo */}
          <Link
            href="/dashboard"
            className="flex items-center gap-3 shrink-0 group mr-1 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-etex-orange/40"
          >
            <Image
              src="/etex-logo.png"
              alt="Etex"
              width={120}
              height={26}
              priority
              className="block object-contain transition-all duration-300 group-hover:scale-[1.04] dark:brightness-0 dark:invert"
            />
            <span className="hidden lg:flex items-center gap-1.5 text-sm font-semibold tracking-tight text-gray-800 dark:text-gray-200">
              <span className="h-3 w-px bg-gray-300 dark:bg-gray-700" aria-hidden />
              PMO Tracker
            </span>
          </Link>

          {/* Desktop nav */}
          <nav
            className="hidden lg:flex items-center h-full gap-1 ml-4"
            aria-label="Main navigation"
          >
            {navItems.map((item) => (
              <DesktopNavLink key={item.href} item={item} active={isActive(item.href, pathname)} />
            ))}
          </nav>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Actions */}
          <div className="flex items-center gap-1 shrink-0">
            <ThemeToggle />

            {/* Divider */}
            <div className="hidden sm:block w-px h-5 bg-gray-200 dark:bg-gray-700/60 mx-1.5" aria-hidden />

            {/* User menu */}
            <div className="relative" ref={dropdownRef}>
              <button
                onClick={() => setDropdownOpen((v) => !v)}
                className={cn(
                  "group flex items-center gap-2 pl-1 pr-2 py-1 rounded-sm transition-all duration-200",
                  "hover:bg-gray-100/70 dark:hover:bg-white/5 active:scale-[0.98]",
                  dropdownOpen && "bg-gray-100/70 dark:bg-white/5",
                )}
              >
                <UserAvatar initials={initials} image={user.image} />
                <span className="hidden sm:block text-sm font-medium text-gray-800 dark:text-gray-200 max-w-28 truncate">
                  {user.name || user.email.split("@")[0]}
                </span>
                <ChevronDown
                  className={cn(
                    "w-3.5 h-3.5 text-gray-400 transition-transform duration-200",
                    dropdownOpen && "rotate-180 text-etex-orange",
                  )}
                />
              </button>

              {dropdownOpen && (
                <div className="absolute right-0 mt-2 w-64 bg-white/95 dark:bg-[#21252B]/95 backdrop-blur-xl border border-(--border) shadow-xl shadow-black/8 dark:shadow-black/40 z-50 overflow-hidden rounded-sm animate-in fade-in slide-in-from-top-2 duration-200">
                  {/* Profile section with gradient accent strip */}
                  <div className="relative px-4 py-3.5 border-b border-(--border-subtle)">
                    <span
                      aria-hidden
                      className="absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent via-etex-orange/50 to-transparent"
                    />
                    <div className="flex items-start gap-3">
                      <UserAvatar initials={initials} image={user.image} />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate leading-tight">
                          {user.name || "User"}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                          {user.email}
                        </p>
                        <span className="inline-flex items-center gap-1 mt-2 px-1.5 py-0.5 rounded-sm text-[9px] font-bold uppercase tracking-wider bg-etex-orange/10 text-etex-orange">
                          <span className="w-1 h-1 rounded-full bg-etex-orange" />
                          {hasAdminAccess ? "Admin" : "Member"}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="py-1">
                    <Link
                      href="/profile"
                      onClick={() => setDropdownOpen(false)}
                      className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/4 transition-colors text-left"
                    >
                      <User className="w-4 h-4 shrink-0 text-gray-400" />
                      Profile
                    </Link>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* ── Mobile Bottom Nav ──────────────────────────────────────── */}
      <nav
        className="fixed bottom-0 inset-x-0 z-40 lg:hidden border-t border-gray-200 dark:border-[#333842] backdrop-blur-lg bg-white/80 dark:bg-[#1A1D23]/80 pb-[env(safe-area-inset-bottom)]"
        aria-label="Mobile navigation"
      >
        <div className="flex items-center h-14">
          {navItems.map((item) => (
            <MobileNavLink key={item.href} item={item} active={isActive(item.href, pathname)} />
          ))}
        </div>
      </nav>
    </>
  );
}
