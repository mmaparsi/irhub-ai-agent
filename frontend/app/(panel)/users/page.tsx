"use client";

import { errorText, useAuth } from "@/components/AuthProvider";
import { Badge, Button, Card, ErrorNote, Field, PageHeader, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import { roleLabel } from "@/lib/labels";
import type { Role, User } from "@/lib/types";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function UsersPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("expert");
  const [error, setError] = useState("");

  useEffect(() => {
    if (ready && user && user.role !== "admin") router.replace("/dashboard");
  }, [ready, router, user]);

  function load() {
    return api<User[]>("/api/users").then(setUsers);
  }

  useEffect(() => {
    if (user?.role === "admin") load().catch((err) => setError(errorText(err)));
  }, [user]);

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader title="کاربران" description="مدیر می‌تواند کارشناس، بیننده یا مدیر جدید بسازد." />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      <Card>
        <form
          className="grid gap-3 md:grid-cols-2"
          onSubmit={async (event) => {
            event.preventDefault();
            setError("");
            try {
              await api("/api/users", {
                method: "POST",
                body: JSON.stringify({ email, password, full_name: fullName, role }),
              });
              setEmail("");
              setFullName("");
              setPassword("");
              await load();
            } catch (err) {
              setError(errorText(err));
            }
          }}
        >
          <Field label="نام">
            <input className={inputClass} value={fullName} onChange={(event) => setFullName(event.target.value)} required />
          </Field>
          <Field label="ایمیل">
            <input dir="ltr" type="email" className={inputClass} value={email} onChange={(event) => setEmail(event.target.value)} required />
          </Field>
          <Field label="گذرواژه">
            <input dir="ltr" type="password" className={inputClass} value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} />
          </Field>
          <Field label="نقش">
            <select className={inputClass} value={role} onChange={(event) => setRole(event.target.value as Role)}>
              <option value="expert">کارشناس</option>
              <option value="viewer">بیننده</option>
              <option value="admin">مدیر</option>
            </select>
          </Field>
          <div className="md:col-span-2">
            <Button type="submit">افزودن کاربر</Button>
          </div>
        </form>
      </Card>
      <div className="space-y-2">
        {users.map((item) => (
          <Card key={item.id} className="flex items-center justify-between gap-3">
            <div>
              <p className="font-medium">{item.full_name}</p>
              <p dir="ltr" className="text-left text-xs text-stone-500">{item.email}</p>
            </div>
            <Badge tone={item.is_active ? "teal" : "stone"}>{roleLabel[item.role] || item.role}</Badge>
          </Card>
        ))}
      </div>
    </div>
  );
}
