"use client";

export interface SelectOption {
  value: string;
  label: string;
  group?: string;
}

interface SelectProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
}

export default function Select({
  value,
  onChange,
  options,
  placeholder,
  disabled,
  ariaLabel,
  className = "",
}: SelectProps) {
  // Ordre de rendu = ordre d'apparition dans `options` : les entrées sans
  // `group` passent avant le premier groupe rencontré (Map en ordre d'insertion).
  const grouped = new Map<string | undefined, SelectOption[]>();
  for (const opt of options) {
    const bucket = grouped.get(opt.group);
    if (bucket) bucket.push(opt);
    else grouped.set(opt.group, [opt]);
  }

  return (
    <select
      value={value}
      disabled={disabled}
      aria-label={ariaLabel}
      onChange={(e) => onChange(e.target.value)}
      className={`rounded-control border border-border bg-surface-2 px-2.5 py-1.5 text-sm text-foreground disabled:opacity-50 ${className}`}
    >
      {placeholder && (
        // value="" jamais listée dans le menu déroulant (hidden) -- ne sert
        // qu'à afficher le placeholder tant qu'aucune vraie option n'est choisie,
        // même pattern qu'un <select> natif sans JS.
        <option value="" disabled hidden>
          {placeholder}
        </option>
      )}
      {[...grouped.entries()].map(([group, opts]) =>
        group ? (
          <optgroup key={group} label={group}>
            {opts.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </optgroup>
        ) : (
          opts.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))
        ),
      )}
    </select>
  );
}
