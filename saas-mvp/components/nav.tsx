import Link from 'next/link';
import { getAuthSession } from '@/lib/auth';

export async function Nav() {
  const session = await getAuthSession();

  return (
    <nav className="border-b bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link href="/" className="font-semibold">SaaS MVP</Link>
        <div className="flex items-center gap-3 text-sm">
          {session?.user ? (
            <>
              <Link href="/dashboard" className="hover:underline">Dashboard</Link>
              <Link href="/api/auth/signout" className="rounded bg-slate-900 px-3 py-1.5 text-white">Sign out</Link>
            </>
          ) : (
            <Link href="/auth/login" className="rounded bg-slate-900 px-3 py-1.5 text-white">Sign in</Link>
          )}
        </div>
      </div>
    </nav>
  );
}
