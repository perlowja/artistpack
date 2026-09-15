import type { Metadata } from "next";
import "./globals.css";
import { TopNav } from "@/components/TopNav";

export const metadata: Metadata = {
  title: "ArtistPack Dashboard",
  description: "ArtistPack artist dashboard (Task 8).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <TopNav />
        <main className="app-main">{children}</main>
      </body>
    </html>
  );
}