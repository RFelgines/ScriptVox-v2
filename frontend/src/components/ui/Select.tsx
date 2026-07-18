type SelectOption = { value: string; label: string };

type SelectProps = {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
};

export default function Select({
  value,
  onChange,
  options,
  placeholder,
  ariaLabel,
  disabled = false,
  className = "",
}: SelectProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={ariaLabel}
      disabled={disabled}
      className={`rounded-control border border-border bg-surface-2 px-2 py-1 text-xs text-foreground transition-colors hover:bg-surface-2/70 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      {placeholder !== undefined && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
