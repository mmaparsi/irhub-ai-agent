"use client";

import { useAuth } from "@/components/AuthProvider";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function HomePage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    router.replace(user ? "/dashboard" : "/login");
  }, [ready, router, user]);
  return <main className="grid min-h-screen place-items-center text-sm text-stone-500">در حال انتقال…</main>;
}
