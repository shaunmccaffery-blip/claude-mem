import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function POST(req: Request) {
  const body = await req.json();
  const email = body?.email as string | undefined;

  if (!email) {
    return NextResponse.json({ error: 'Email required' }, { status: 400 });
  }

  const user = await prisma.user.upsert({
    where: { email },
    update: {},
    create: {
      email,
      settings: {
        create: {}
      },
      subscriptions: {
        create: {}
      }
    }
  });

  return NextResponse.json({ id: user.id });
}
