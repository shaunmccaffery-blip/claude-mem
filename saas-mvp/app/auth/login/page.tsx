import { EmailAuthForm } from '@/components/forms/email-auth-form';

export default function LoginPage() {
  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-semibold">Log in</h1>
      <EmailAuthForm mode="login" />
    </div>
  );
}
