import { formatEnumLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

type BadgeProps = {
  value: string;
  tone?: BadgeTone;
  className?: string;
};

const toneClasses: Record<BadgeTone, string> = {
  neutral: "bg-slate-100 text-slate-700",
  success: "bg-emerald-50 text-emerald-800",
  warning: "bg-amber-50 text-amber-900",
  danger: "bg-red-50 text-red-800",
  info: "bg-accent-wash text-accent-ink",
};

export function Badge({ value, tone = "neutral", className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex whitespace-nowrap rounded-[3px] px-1.5 py-px text-xs font-medium",
        toneClasses[tone],
        className,
      )}
    >
      {formatEnumLabel(value)}
    </span>
  );
}

export const statusTone: Record<string, BadgeTone> = {
  approved: "success",
  ready: "success",
  in_review: "info",
  waiting_for_documents: "warning",
  processing: "info",
  rejected: "danger",
  failed: "danger",
  archived: "neutral",
  queued: "neutral",
};

export const priorityTone: Record<string, BadgeTone> = {
  urgent: "danger",
  high: "warning",
};
