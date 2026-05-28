import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0A0A0F]">
      <SignIn appearance={{ baseTheme: undefined }} />
    </div>
  );
}
