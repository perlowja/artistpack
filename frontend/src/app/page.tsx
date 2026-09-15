"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";

/**
 * Landing page is intentionally minimal: an authenticated session
 * redirects to the packs list, otherwise to the login page. Everything
 * real lives under those routes.
 */
export default function HomePage() {
  const router = useRouter();
  const session = useSession();

  useEffect(() => {
    if (session) {
      router.replace("/packs");
    } else {
      router.replace("/login");
    }
  }, [session, router]);

  return (
    <p className="loading" data-testid="home-loading">
      Loading…
    </p>
  );
}