export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">{title}</h1>
        {description ? <p className="mt-1 text-sm text-stone-600">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-[#e6dfd2] bg-[#fffcf7] p-5 shadow-sm ${className}`}>
      {children}
    </section>
  );
}

export function Button({
  children,
  tone = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "ghost" | "danger" }) {
  const tones = {
    primary: "bg-teal-800 text-white hover:bg-teal-900",
    ghost: "border border-[#e6dfd2] bg-white text-stone-800 hover:bg-stone-50",
    danger: "bg-rose-800 text-white hover:bg-rose-900",
  };
  return (
    <button
      {...props}
      className={`rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 ${tones[tone]} ${props.className || ""}`}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="font-medium text-stone-700">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "w-full rounded-xl border border-[#e6dfd2] bg-white px-3 py-2 text-sm outline-none focus:border-teal-700";

export function Badge({ children, tone = "stone" }: { children: React.ReactNode; tone?: "stone" | "teal" | "amber" | "rose" }) {
  const tones = {
    stone: "bg-stone-100 text-stone-700",
    teal: "bg-teal-100 text-teal-900",
    amber: "bg-amber-100 text-amber-950",
    rose: "bg-rose-100 text-rose-900",
  };
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-2xl border border-dashed border-[#e6dfd2] px-4 py-8 text-center text-sm text-stone-500">{children}</p>;
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  return <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-800">{children}</p>;
}
