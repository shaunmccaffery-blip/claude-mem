'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';

export function NewDataSourceForm() {
  const router = useRouter();
  const [title, setTitle] = useState('');
  const [rawText, setRawText] = useState('');
  const [status, setStatus] = useState('');

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const res = await fetch('/api/data-sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, rawText })
    });

    if (!res.ok) {
      setStatus('Failed to save data source');
      return;
    }

    setStatus('Saved and report generated.');
    setTitle('');
    setRawText('');
    router.push('/dashboard');
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded border bg-white p-6">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Data source title"
        className="w-full rounded border px-3 py-2"
        required
      />
      <input
        type="file"
        accept=".txt,text/plain"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (file) {
            const content = await file.text();
            setRawText(content);
            if (!title) setTitle(file.name.replace(/\.txt$/i, ''));
          }
        }}
        className="w-full rounded border px-3 py-2 text-sm"
      />
      <textarea
        value={rawText}
        onChange={(e) => setRawText(e.target.value)}
        placeholder="Paste your text data here"
        className="h-56 w-full rounded border px-3 py-2"
        required
      />
      <button className="rounded bg-slate-900 px-4 py-2 text-white" type="submit">Create report</button>
      {status && <p className="text-sm text-slate-600">{status}</p>}
    </form>
  );
}
