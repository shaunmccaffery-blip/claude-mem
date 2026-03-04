import { NextResponse } from 'next/server';
import { getAuthSession } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { stripe } from '@/lib/stripe';

export async function POST() {
  const session = await getAuthSession();
  if (!session?.user?.id || !session.user.email) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const existing = await prisma.subscription.findFirst({ where: { userId: session.user.id } });

  let customerId = existing?.stripeCustomerId;
  if (!customerId) {
    const customer = await stripe.customers.create({ email: session.user.email });
    customerId = customer.id;
  }

  const checkout = await stripe.checkout.sessions.create({
    customer: customerId,
    mode: 'subscription',
    line_items: [
      {
        price: process.env.STRIPE_PRICE_ID,
        quantity: 1
      }
    ],
    success_url: `${process.env.NEXTAUTH_URL}/dashboard?billing=success`,
    cancel_url: `${process.env.NEXTAUTH_URL}/dashboard?billing=cancel`
  });

  await prisma.subscription.upsert({
    where: { userId: session.user.id },
    update: { stripeCustomerId: customerId },
    create: { userId: session.user.id, stripeCustomerId: customerId }
  });

  return NextResponse.redirect(checkout.url || `${process.env.NEXTAUTH_URL}/dashboard`);
}
