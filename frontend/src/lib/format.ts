const fullDateFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
});

const shortDateFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
});

export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "No date";
  }
  return fullDateFormatter.format(new Date(value));
}

export function formatDate(value: string | null | undefined) {
  if (!value) {
    return "No due date";
  }
  return shortDateFormatter.format(new Date(value));
}

export function formatEnumLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function initials(firstName: string, lastName: string) {
  return `${firstName[0] ?? ""}${lastName[0] ?? ""}`.toUpperCase() || "CF";
}
