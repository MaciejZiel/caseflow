import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  fullWidth?: boolean;
};

export function Button({
  className,
  variant = "primary",
  fullWidth = false,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "button",
        "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-orange-200",
        variant === "primary" && "button-primary",
        variant === "secondary" && "button-secondary",
        variant === "ghost" && "button-ghost",
        fullWidth && "w-full",
        className,
      )}
      {...props}
    />
  );
}
