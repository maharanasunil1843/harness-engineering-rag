import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0A0A0F]">
      <SignUp appearance={{ baseTheme: undefined }} />
    </div>
  );
}
