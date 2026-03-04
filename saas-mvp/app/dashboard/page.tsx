import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getAuthSession } from '@/lib/auth';
import { prisma } from '@/lib/prisma';

export default async function DashboardPage() {
  const session = await getAuthSession();

  if (!session?.user?.id) {
    redirect('/auth/login');
  }

  const [reports, subscription] = await Promise.all([
    prisma.report.findMany({
      where: { userId: session.user.id },
      orderBy: { createdAt: 'desc' }
    }),
    prisma.subscription.findFirst({ where: { userId: session.user.id } })
  ]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <Link href="/new-report" className="rounded bg-slate-900 px-4 py-2 text-white">New report</Link>
      </div>

      <div className="rounded border bg-white p-4">
        <p className="font-medium">Subscription: {subscription?.status || 'TRIAL'}</p>
        <form action="/api/billing/checkout" method="post" className="mt-3">
          <button className="rounded border px-3 py-1.5 text-sm" type="submit">Upgrade to paid plan</button>
        </form>
      </div>

      <section className="space-y-3">
        {reports.length === 0 ? (
          <p className="text-slate-600">No reports yet. Add your first data source.</p>
        ) : (
          reports.map((report) => (
            <article key={report.id} className="rounded border bg-white p-4">
              <h2 className="font-semibold">{report.title}</h2>
              <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{report.content}</p>
              <p className="mt-3 text-xs text-slate-500">
                {new Date(report.createdAt).toLocaleString()} · {report.reportType}
              </p>
            </article>
          ))
        )}
      </section>
    </div>
  );
}
