import { ReportType } from '@prisma/client';
import OpenAI from 'openai';
import { prisma } from '@/lib/prisma';
import { resend } from '@/lib/resend';

function buildTemplateSummary(text: string) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  const sentences = text.split(/[.!?]+/).filter(Boolean);
  const preview = text.slice(0, 220);

  return [
    'Automated Template Report',
    '',
    `- Word count: ${words.length}`,
    `- Estimated sentences: ${sentences.length}`,
    `- Preview: ${preview}${text.length > 220 ? '...' : ''}`,
    '',
    'Recommendation: review this text and define one measurable next action.'
  ].join('\n');
}

async function maybeGenerateAISummary(text: string) {
  if (!process.env.OPENAI_API_KEY) return null;

  const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const completion = await openai.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [
      {
        role: 'system',
        content: 'You write concise business reports.'
      },
      {
        role: 'user',
        content: `Summarize the following text as a short report with highlights and one action item:\n\n${text}`
      }
    ]
  });

  return completion.choices[0]?.message?.content || null;
}

export async function generateReportForDataSource(dataSourceId: string) {
  const dataSource = await prisma.dataSource.findUnique({
    where: { id: dataSourceId },
    include: {
      user: {
        include: {
          settings: true
        }
      }
    }
  });

  if (!dataSource) {
    throw new Error(`Data source ${dataSourceId} not found`);
  }

  const aiSummary = await maybeGenerateAISummary(dataSource.rawText);
  const content = aiSummary ?? buildTemplateSummary(dataSource.rawText);
  const reportType = aiSummary ? ReportType.AI : ReportType.TEMPLATE;

  const report = await prisma.report.create({
    data: {
      userId: dataSource.userId,
      dataSourceId: dataSource.id,
      title: `${dataSource.title} Report`,
      content,
      reportType
    }
  });

  if (resend && dataSource.user.settings?.notificationsEnabled !== false && dataSource.user.email) {
    await resend.emails.send({
      from: process.env.EMAIL_FROM || 'noreply@example.com',
      to: dataSource.user.email,
      subject: `Your new report is ready: ${report.title}`,
      text: `A new report was generated.\n\n${report.content}`
    });
  }

  return report;
}
