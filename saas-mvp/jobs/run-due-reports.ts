import { prisma } from '@/lib/prisma';
import { generateReportForDataSource } from '@/services/report-generator';

export async function runDueReportsJob() {
  const settings = await prisma.userSettings.findMany({
    include: {
      user: {
        include: {
          dataSources: {
            orderBy: {
              createdAt: 'desc'
            },
            take: 1
          }
        }
      }
    }
  });

  const results: Array<{ userId: string; status: string; reportId?: string }> = [];

  for (const item of settings) {
    const now = Date.now();
    const last = item.lastGeneratedAt?.getTime() ?? 0;
    const due = now - last >= item.reportFrequencyHours * 60 * 60 * 1000;
    const latestDataSource = item.user.dataSources[0];

    if (!due || !latestDataSource) {
      continue;
    }

    try {
      const report = await generateReportForDataSource(latestDataSource.id);
      await prisma.userSettings.update({
        where: { id: item.id },
        data: { lastGeneratedAt: new Date() }
      });
      results.push({ userId: item.userId, status: 'generated', reportId: report.id });
    } catch {
      results.push({ userId: item.userId, status: 'failed' });
    }
  }

  return results;
}
