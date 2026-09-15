"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clearSession, useSession } from "@/lib/session";
import { cx } from "@/lib/cx";

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function TopNav() {
  const pathname = usePathname() ?? "/";
  const session = useSession();

  function signOut() {
    clearSession();
    if (typeof window !== "undefined") {
      window.location.assign("/");
    }
  }

  return (
    <header className="topnav" role="banner">
      <div className="topnav-brand">
        <Link href="/">ArtistPack</Link>
      </div>
      <nav className="topnav-links" aria-label="Primary">
        {session ? (
          <>
            <Link
              href="/me"
              className={cx("topnav-link", isActive(pathname, "/me") && "active")}
              aria-current={isActive(pathname, "/me") ? "page" : undefined}
            >
              Profile
            </Link>
            <Link
              href="/packs"
              className={cx("topnav-link", isActive(pathname, "/packs") && "active")}
              aria-current={isActive(pathname, "/packs") ? "page" : undefined}
            >
              Packs
            </Link>
            <span className="topnav-user">
              {session.displayName ? session.displayName : "Signed in"}
            </span>
            <button
              type="button"
              className="btn-secondary"
              onClick={signOut}
              data-testid="signout"
            >
              Sign out
            </button>
          </>
        ) : (
          <Link
            href="/login"
            className={cx("topnav-link", isActive(pathname, "/login") && "active")}
            aria-current={isActive(pathname, "/login") ? "page" : undefined}
          >
            Sign in
          </Link>
        )}
      </nav>
    </header>
  );
}