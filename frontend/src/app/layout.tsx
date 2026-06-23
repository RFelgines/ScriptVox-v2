import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";
import PlayerProvider from "@/components/player/PlayerProvider";
import PlayerBar from "@/components/player/PlayerBar";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ScriptVox",
  description: "EPUB → audiobook multi-voix",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${outfit.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col pb-24 bg-gray-950 text-gray-100 font-sans">
          <Nav />
          <PlayerProvider>
            {children}
            <PlayerBar />
          </PlayerProvider>
        </body>
    </html>
  );
}
