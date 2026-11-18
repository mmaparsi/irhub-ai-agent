"use client";

import { useAuth } from "@/components/AuthProvider";
import { roleLabel } from "@/lib/labels";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

const links = [
  { href: "/dashboard", label: "داشبورد" },
  { href: "/chat", label: "گفتگو" },
  { href: "/agents", label: "عامل‌ها" },
  { href: "/approvals", label: "تأییدها" },
  { href: "/leads", label: "سرنخ‌ها" },
  { href: "/knowledge", label: "پایگاه دانش" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, router, user]);

  if (!ready || !user) {
    return <main className="grid min-h-screen place-items-center text-sm text-stone-500">در حال بارگذاری…</main>;
  }

  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-stone-800 bg-[#1f1a17] text-stone-100 md:sticky md:top-0 md:flex md:h-screen md:w-64 md:shrink-0 md:flex-col md:border-b-0">
        <div className="px-5 py-5">
          <p className="text-lg font-bold">ایرهاب</p>
          <p className="text-xs text-stone-400">عامل‌های کسب‌وکار</p>
        </div>
        <nav className="flex gap-2 overflow-x-auto px-3 pb-3 md:block md:flex-1 md:space-y-1 md:overflow-visible">
          {links.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`block whitespace-nowrap rounded-xl px-3 py-2 text-sm ${active ? "bg-teal-800 text-white" : "text-stone-300 hover:bg-white/5"}`}
              >
                {link.label}
              </Link>
            );
          })}
          {user.role === "admin" ? (
            <Link
              href="/users"
              className={`block whitespace-nowrap rounded-xl px-3 py-2 text-sm ${pathname.startsWith("/users") ? "bg-teal-800 text-white" : "text-stone-300 hover:bg-white/5"}`}
            >
              کاربران
            </Link>
          ) : null}
        </nav>
        <div className="flex items-center justify-between gap-3 border-t border-white/10 px-4 py-4 text-sm">
          <div>
            <p className="font-medium">{user.full_name}</p>
            <p className="text-xs text-stone-400">{roleLabel[user.role] || user.role}</p>
          </div>
          <button
            className="rounded-lg px-2 py-1 text-xs text-stone-300 hover:bg-white/10"
            onClick={() => {
              logout();
              router.replace("/login");
            }}
          >
            خروج
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-8">{children}</main>
    </div>
  );
}
