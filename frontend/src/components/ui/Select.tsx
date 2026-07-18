export type SelectOption = {
  value: string;
  label: string;
  group?: string;
};

export default function Select({
  value,
  onChange,
  options,
  ariaLabel,
  className = "",
  disabled = false,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  ariaLabel?: string;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
}) {
  const ungrouped = options.filter((o) => !o.group);
  const groups = new Map<string, SelectOption[]>();
  for (const o of options) {
    if (!o.group) continue;
    if (!groups.has(o.group)) groups.set(o.group, []);
    groups.get(o.group)!.push(o);
  }

  return (
    <select
      value={value}
      disabled={disabled}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
      className={`rounded-control border border-border bg-surface-2 px-2 py-1 text-sm text-foreground transition-colors hover:bg-surface-2/70 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      {placeholder && <option value="">{placeholder}</option>}
      {ungrouped.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
      {[...groups.entries()].map(([group, opts]) => (
        <optgroup key={group} label={group}>
          {opts.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
