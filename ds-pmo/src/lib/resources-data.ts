import {
  GraduationCap,
  ClipboardList,
  BarChart3,
  Shield,
  FileText,
  type LucideIcon,
} from "lucide-react";

// ─── Presentation metadata for Resources-page category tabs ─────────────────
// Resource *data* now lives in the database (src/lib/db/resources.ts, admin-
// editable from the Resources page) — this file only maps a category's title
// string to how its tab looks. Categories are otherwise freeform: an admin
// can type any category name when adding a resource, and it gets the
// DEFAULT_CATEGORY_STYLE below until a dedicated entry is added here.

export interface CategoryStyle {
  icon: LucideIcon;
  accent: string;
  iconBg: string;
  tabColors: { bg: string; border: string; text: string; hoverBg: string; countBg: string; countText: string };
}

export const DEFAULT_CATEGORY_STYLE: CategoryStyle = {
  icon: FileText,
  accent: "text-gray-600 dark:text-gray-400",
  iconBg: "bg-gray-100 dark:bg-gray-500/10",
  tabColors: { bg: "bg-gray-100 dark:bg-gray-500/10", border: "border-gray-400 dark:border-gray-500", text: "text-gray-700 dark:text-gray-300", hoverBg: "hover:bg-gray-50 dark:hover:bg-gray-500/5", countBg: "bg-gray-200 dark:bg-gray-500/15", countText: "text-gray-600 dark:text-gray-400" },
};

export const CATEGORY_STYLES: Record<string, CategoryStyle> = {
  "PM Governance & Communication Plan": {
    icon: Shield,
    accent: "text-blue-600 dark:text-blue-400",
    iconBg: "bg-blue-50 dark:bg-blue-500/10",
    tabColors: { bg: "bg-blue-50 dark:bg-blue-500/10", border: "border-blue-500 dark:border-blue-400", text: "text-blue-700 dark:text-blue-300", hoverBg: "hover:bg-blue-50/60 dark:hover:bg-blue-500/5", countBg: "bg-blue-100 dark:bg-blue-500/15", countText: "text-blue-600 dark:text-blue-400" },
  },
  "Project Lifecycle": {
    icon: BarChart3,
    accent: "text-emerald-600 dark:text-emerald-400",
    iconBg: "bg-emerald-50 dark:bg-emerald-500/10",
    tabColors: { bg: "bg-emerald-50 dark:bg-emerald-500/10", border: "border-emerald-500 dark:border-emerald-400", text: "text-emerald-700 dark:text-emerald-300", hoverBg: "hover:bg-emerald-50/60 dark:hover:bg-emerald-500/5", countBg: "bg-emerald-100 dark:bg-emerald-500/15", countText: "text-emerald-600 dark:text-emerald-400" },
  },
  "Training: Masterclass": {
    icon: GraduationCap,
    accent: "text-violet-600 dark:text-violet-400",
    iconBg: "bg-violet-50 dark:bg-violet-500/10",
    tabColors: { bg: "bg-violet-50 dark:bg-violet-500/10", border: "border-violet-500 dark:border-violet-400", text: "text-violet-700 dark:text-violet-300", hoverBg: "hover:bg-violet-50/60 dark:hover:bg-violet-500/5", countBg: "bg-violet-100 dark:bg-violet-500/15", countText: "text-violet-600 dark:text-violet-400" },
  },
  "Templates": {
    icon: ClipboardList,
    accent: "text-etex-orange dark:text-etex-orange-light",
    iconBg: "bg-etex-orange-50 dark:bg-etex-orange/10",
    tabColors: { bg: "bg-etex-orange-50 dark:bg-etex-orange/10", border: "border-etex-orange dark:border-etex-orange-light", text: "text-etex-orange-dark dark:text-etex-orange-light", hoverBg: "hover:bg-etex-orange-50/60 dark:hover:bg-etex-orange/5", countBg: "bg-etex-orange-100 dark:bg-etex-orange/15", countText: "text-etex-orange dark:text-etex-orange-light" },
  },
};

export function getCategoryStyle(title: string): CategoryStyle {
  return CATEGORY_STYLES[title] ?? DEFAULT_CATEGORY_STYLE;
}
