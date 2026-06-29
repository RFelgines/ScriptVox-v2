import { ButtonHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "warning" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  // Neutre, pas d'accent de marque : la couleur vit dans les orbes de voix,
  // pas dans le chrome (décision DA, voir ui_modernization_plan).
  primary: "bg-primary text-primary-foreground hover:opacity-90",
  secondary: "border border-border bg-surface-2 text-foreground hover:bg-surface-2/70",
  warning: "bg-amber-600 hover:bg-amber-500 text-white",
  danger: "bg-red-700 hover:bg-red-600 text-white",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "px-2 py-1 text-xs",
  md: "px-3 py-1.5 text-sm",
  lg: "px-4 py-2 text-sm",
};

type ButtonProps = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
} & ButtonHTMLAttributes<HTMLButtonElement>;

export default function Button({
  variant = "secondary",
  size = "md",
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`rounded-control font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    />
  );
}
