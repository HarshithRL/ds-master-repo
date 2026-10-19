import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-sm border px-2 py-0.5 text-[11px] font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-etex-orange focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-etex-charcoal text-white dark:bg-gray-200 dark:text-gray-900",
        secondary:
          "border-transparent bg-gray-100 text-gray-700 dark:bg-[#282C34] dark:text-gray-300",
        destructive:
          "border-transparent bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400",
        outline: "border-gray-200 text-gray-700 dark:border-[#333842] dark:text-gray-300",
        success:
          "border-transparent bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400",
        warning:
          "border-transparent bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
