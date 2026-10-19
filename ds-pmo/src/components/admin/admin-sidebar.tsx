"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Users,
  Building2,
  Tag,
  ShieldCheck,
  Camera,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Permission } from "@/lib/permissions";

interface SidebarItem {
  label: string;
  href: string;
  icon: LucideIcon;
  // null = always visible to anyone reaching /admin
  // "ADMIN" = visible only to ADMIN globalRole
  // Permission = visible if user holds that admin-module permission
  requires: Permission | "ADMIN" | null;
}

const SIDEBAR_ITEMS: SidebarItem[] = [
  { label: "Users", href: "/admin", icon: Users, requires: "MANAGE_USERS" },
  { label: "Factories", href: "/admin/factories", icon: Building2, requires: "MANAGE_FACTORIES" },
  { label: "Categories", href: "/admin/categories", icon: Tag, requires: "MANAGE_CATEGORIES" },
  { label: "Snapshots", href: "/admin/snapshots", icon: Camera, requires: "ADMIN" },
  { label: "Audit Log", href: "/admin/audit", icon: ShieldCheck, requires: "VIEW_AUDIT_LOGS" },
];

function isActive(href: string, pathname: string) {
  if (href === "/admin") return pathname === "/admin";
  return pathname.startsWith(href);
}

export function AdminSidebar({
  permissions,
  isAdmin,
}: {
  permissions: string[];
  isAdmin: boolean;
}) {
  const pathname = usePathname();

  const visibleItems = SIDEBAR_ITEMS.filter((item) => {
    if (item.requires === null) return true;
    if (item.requires === "ADMIN") return isAdmin;
    return isAdmin || permissions.includes(item.requires);
  });

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:block w-48 shrink-0">
        <nav className="space-y-0.5" aria-label="Admin sections">
          {visibleItems.map((item) => {
            const active = isActive(item.href, pathname);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2 text-sm rounded-sm transition-all duration-100 text-left border-l-2",
                  active
                    ? "border-etex-orange bg-orange-50 dark:bg-etex-orange/10 text-etex-orange font-medium"
                    : "border-transparent text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 hover:text-gray-900 dark:hover:text-gray-200"
                )}
              >
                <item.icon className={cn("w-4 h-4 shrink-0", active ? "text-etex-orange" : "text-gray-400 dark:text-gray-500")} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Mobile horizontal tabs */}
      <div className="lg:hidden w-full overflow-x-auto -mx-1 px-1">
        <div className="flex gap-1.5 pb-1 min-w-max">
          {visibleItems.map((item) => {
            const active = isActive(item.href, pathname);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-all border",
                  active
                    ? "bg-etex-orange text-white border-etex-orange shadow-sm"
                    : "bg-card text-muted-foreground border-border hover:bg-muted hover:text-foreground"
                )}
              >
                <item.icon className="w-3.5 h-3.5" />
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
    </>
  );
}
