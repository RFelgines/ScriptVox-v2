import { ReactNode } from "react";

export default function Alert({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded border border-red-700 bg-red-900/40 p-4 ${className}`}>
      {title && <p className="font-semibold text-red-300">{title}</p>}
      {children}
    </div>
  );
}
