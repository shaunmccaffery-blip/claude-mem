import { NextResponse } from 'next/server';
import { getAuthSession } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { generateReportForDataSource } from '@/services/report-generator';

export async function POST(req: Request) {
  const session = await getAuthSession();
  if (!session?.user?.id) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const body = await req.json();
  const title = body?.title as string | undefined;
  const rawText = body?.rawText as string | undefined;

  if (!title || !rawText) {
    return NextResponse.json({ error: 'title and rawText are required' }, { status: 400 });
  }

  const dataSource = await prisma.dataSource.create({
    data: {
      userId: session.user.id,
      title,
      rawText
    }
  });

  const report = await generateReportForDataSource(dataSource.id);

  return NextResponse.json({ dataSourceId: dataSource.id, reportId: report.id });
}
