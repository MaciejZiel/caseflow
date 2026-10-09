import { formatEnumLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

type BadgeProps = {
  value: string;
  tone?: "neutral" | "success" | "warning" | "danger";
  className?: string;
};

const toneClasses = {
  neutral: "border border-slate-300/70 bg-white/70 text-slate-700",
  success: "border border-teal-200 bg-teal-50 text-teal-800",
  warning: "border border-orange-200 bg-orange-50 text-orange-900",
  danger: "border border-rose-200 bg-rose-50 text-rose-800",
};

export function Badge({ value, tone = "neutral", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]",
        toneClasses[tone],
        className,
      )}
    >
      {formatEnumLabel(value)}
    </span>
  );
}
