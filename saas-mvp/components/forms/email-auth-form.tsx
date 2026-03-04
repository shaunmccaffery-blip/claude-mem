'use client';

import { FormEvent, useState } from 'react';
import { signIn } from 'next-auth/react';

export function EmailAuthForm({ mode }: { mode: 'login' | 'signup' }) {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');

  async function onSubmit(e: FormEvent) {
    e.preventDefault();

    if (mode === 'signup') {
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      if (!res.ok) {
        setMessage('Could not create account.');
        return;
      }
    }

    await signIn('email', { email, callbackUrl: '/dashboard' });
    setMessage('Check your email for the login link.');
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded border bg-white p-6">
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.com"
        className="w-full rounded border px-3 py-2"
      />
      <button type="submit" className="w-full rounded bg-slate-900 px-3 py-2 text-white">
        {mode === 'signup' ? 'Create account' : 'Send login link'}
      </button>
      {message && <p className="text-sm text-slate-600">{message}</p>}
    </form>
  );
}
