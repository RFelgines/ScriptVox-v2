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
    <div className={`rounded-control border border-red-500/30 bg-red-500/10 p-4 ${className}`}>
      {title && <p className="font-semibold text-red-500">{title}</p>}
      {children}
    </div>
  );
}
