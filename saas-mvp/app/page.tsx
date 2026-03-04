import Link from 'next/link';

export default function HomePage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Minimal SaaS MVP</h1>
      <p className="text-slate-600">
        Upload text, generate automated reports, receive email notifications, and manage billing.
      </p>
      <div className="flex gap-3">
        <Link href="/auth/signup" className="rounded bg-slate-900 px-4 py-2 text-white">Get started</Link>
        <Link href="/dashboard" className="rounded border px-4 py-2">Open dashboard</Link>
      </div>
    </div>
  );
}
