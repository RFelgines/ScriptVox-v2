"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "./ThemeToggle";

type Tab = { href: string; label: string };

const TABS: Tab[] = [
  { href: "/", label: "Bibliothèque" },
  { href: "/voix", label: "Voix" },
  { href: "/generation", label: "Génération" },
  { href: "/parametres", label: "Paramètres" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    // La Bibliothèque couvre l'accueil et le détail d'un livre (/books/...).
    return pathname === "/" || pathname.startsWith("/books");
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function Nav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-2 px-3 py-3 sm:gap-6 sm:px-6">
        <Link href="/" className="shrink-0 text-lg font-bold tracking-tight text-foreground">
          <span className="sm:hidden">SV</span>
          <span className="hidden sm:inline">ScriptVox</span>
        </Link>
        <nav className="flex flex-1 items-center gap-0.5 overflow-x-auto sm:gap-1">
          {TABS.map((tab) => {
            const active = isActive(pathname, tab.href);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={`shrink-0 rounded-control px-2 py-1.5 text-sm font-medium whitespace-nowrap transition-colors sm:px-3 ${
                  active
                    ? "bg-surface-2 text-foreground"
                    : "text-muted hover:bg-surface-2/60 hover:text-foreground"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
        <ThemeToggle />
      </div>
    </header>
  );
}
