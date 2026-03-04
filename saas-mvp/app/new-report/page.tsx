import { redirect } from 'next/navigation';
import { NewDataSourceForm } from '@/components/forms/new-data-source-form';
import { getAuthSession } from '@/lib/auth';

export default async function NewReportPage() {
  const session = await getAuthSession();
  if (!session?.user?.id) {
    redirect('/auth/login');
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">New report data</h1>
      <NewDataSourceForm />
    </div>
  );
}
