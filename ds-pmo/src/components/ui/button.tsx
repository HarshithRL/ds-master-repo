import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-sm text-sm font-medium ring-offset-white transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-etex-orange focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 dark:ring-offset-gray-950 dark:focus-visible:ring-etex-orange",
  {
    variants: {
      variant: {
        default: "bg-etex-orange text-white hover:bg-etex-orange-dark hover:shadow-md active:shadow-sm",
        destructive:
          "bg-red-600 text-white hover:bg-red-700 hover:shadow-md dark:bg-red-600 dark:hover:bg-red-700",
        outline:
          "border border-gray-200 bg-white hover:bg-gray-50 hover:border-gray-300 text-gray-700 dark:border-[#333842] dark:bg-[#21252B] dark:text-gray-300 dark:hover:bg-[#282C34] dark:hover:border-[#3D4350]",
        secondary:
          "bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-[#282C34] dark:text-gray-300 dark:hover:bg-[#333842]",
        ghost: "hover:bg-gray-100 text-gray-700 dark:text-gray-300 dark:hover:bg-white/5",
        link: "text-etex-orange underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
