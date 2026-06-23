"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Tab = { href: string; label: string };

const TABS: Tab[] = [
  { href: "/", label: "Bibliothèque" },
  { href: "/casting", label: "Casting" },
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
    <header className="sticky top-0 z-30 border-b border-gray-800 bg-gray-900/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight text-gray-100">
          Script<span className="text-amber-500">Vox</span>
        </Link>
        <nav className="flex items-center gap-1">
          {TABS.map((tab) => {
            const active = isActive(pathname, tab.href);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-gray-800 text-amber-400"
                    : "text-gray-400 hover:bg-gray-800/60 hover:text-gray-100"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
