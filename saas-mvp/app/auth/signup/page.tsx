import { EmailAuthForm } from '@/components/forms/email-auth-form';

export default function SignupPage() {
  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-semibold">Sign up</h1>
      <EmailAuthForm mode="signup" />
    </div>
  );
}
