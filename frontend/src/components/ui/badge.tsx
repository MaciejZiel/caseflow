import { formatEnumLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

type BadgeProps = {
  value: string;
  tone?: "neutral" | "success" | "warning" | "danger";
  className?: string;
};

const toneClasses = {
  neutral: "bg-slate-200/80 text-slate-700",
  success: "bg-emerald-100 text-emerald-800",
  warning: "bg-amber-100 text-amber-900",
  danger: "bg-rose-100 text-rose-800",
};

export function Badge({ value, tone = "neutral", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em]",
        toneClasses[tone],
        className,
      )}
    >
      {formatEnumLabel(value)}
    </span>
  );
}
