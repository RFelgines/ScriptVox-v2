import type { Metadata } from "next";
import { Outfit, Geist_Mono } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";
import PlayerProvider from "@/components/player/PlayerProvider";
import PlayerBar from "@/components/player/PlayerBar";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ScriptVox",
  description: "EPUB → audiobook multi-voix",
};

// Lu avant le premier paint (cf. doc Next "preventing-flash-before-hydration") :
// applique data-theme="light" si stocké (sombre = défaut implicite de :root,
// cf. globals.css). Le JSX ne pose jamais data-theme lui-même -- mais même
// sans littéral à réconcilier, un MutationObserver confirme (diagnostiqué en
// conditions réelles, reproduit même en build de production) qu'un mécanisme
// interne de l'App Router retire l'attribut ~0-500ms après l'event "load"
// (probable résolution tardive d'une frontière Suspense touchant <html>).
// D'où l'auto-réparation permanente ci-dessous : la SEULE source de vérité
// est localStorage : si l'attribut DOM dévie, on le restaure aussitôt. Sans
// boucle infinie -- une fois corrigé, la mutation suivante est un no-op.
const THEME_INIT_SCRIPT = `(function(){function correct(){try{var wanted=localStorage.getItem("theme")==="light"?"light":null;var current=document.documentElement.getAttribute("data-theme");if(wanted&&current!==wanted)document.documentElement.setAttribute("data-theme",wanted);else if(!wanted&&current)document.documentElement.removeAttribute("data-theme")}catch(e){}}correct();new MutationObserver(correct).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]})})()`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="fr"
      suppressHydrationWarning
      className={`${outfit.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col pb-24 bg-background text-foreground font-sans">
        {/* type différencié serveur/client + suppressHydrationWarning : évite
            l'avertissement dev "script tag while rendering" (cf. doc Next,
            section "Extracting a reusable component"). Placé en tout premier
            enfant de <body> plutôt que dans <head> -- diagnostic en cours sur
            ce projet : le script ne semblait pas s'exécuter une fois placé
            dans <head> (data-theme jamais appliqué malgré localStorage
            correctement renseigné, reproduit même en build de production). */}
        <script
          type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
          suppressHydrationWarning
          dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }}
        />
        <Nav />
        <PlayerProvider>
          {children}
          <PlayerBar />
        </PlayerProvider>
      </body>
    </html>
  );
}
