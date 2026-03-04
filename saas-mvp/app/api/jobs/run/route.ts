import { NextResponse } from 'next/server';
import { runDueReportsJob } from '@/jobs/run-due-reports';

export async function POST(req: Request) {
  const secret = req.headers.get('x-job-secret');
  if (!process.env.JOB_SECRET || secret !== process.env.JOB_SECRET) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const results = await runDueReportsJob();

  return NextResponse.json({ ok: true, processed: results.length, results });
}
