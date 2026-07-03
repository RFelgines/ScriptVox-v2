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
    <div className={`rounded-control border border-danger/30 bg-danger/10 p-4 ${className}`}>
      {title && <p className="font-semibold text-danger">{title}</p>}
      {children}
    </div>
  );
}
