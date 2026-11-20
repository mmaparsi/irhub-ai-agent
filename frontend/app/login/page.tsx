"use client";

import { errorText, useAuth } from "@/components/AuthProvider";
import { Button, ErrorNote, Field, inputClass } from "@/components/ui";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function LoginPage() {
  const { user, ready, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace("/dashboard");
  }, [ready, router, user]);

  return (
    <main className="grid min-h-screen place-items-center px-4">
      <form
        className="w-full max-w-md space-y-4 rounded-3xl border border-[#e6dfd2] bg-[#fffcf7] p-8 shadow-sm"
        onSubmit={async (event) => {
          event.preventDefault();
          setPending(true);
          setError("");
          try {
            await login(email, password);
            router.replace("/dashboard");
          } catch (err) {
            setError(errorText(err));
          } finally {
            setPending(false);
          }
        }}
      >
        <div>
          <p className="text-sm text-teal-800">ایرهاب</p>
          <h1 className="mt-1 text-2xl font-bold">ورود کارشناسان</h1>
          <p className="mt-2 text-sm text-stone-600">
            محیط توسعه: admin@example.com و گذرواژه admin123. پیش از استفادهٔ مشترک این مقادیر را عوض کنید.
          </p>
        </div>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <Field label="ایمیل">
          <input dir="ltr" className={inputClass} type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </Field>
        <Field label="گذرواژه">
          <input dir="ltr" className={inputClass} type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </Field>
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "در حال ورود…" : "ورود"}
        </Button>
      </form>
    </main>
  );
}
