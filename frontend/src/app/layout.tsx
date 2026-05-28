import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Harness Engineering RAG",
  description:
    "Agentic retrieval-augmented generation over the harness engineering corpus",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider>
      <html lang="en" className={`${inter.variable} dark h-full`}>
        <body className="h-full bg-[#0A0A0F] text-zinc-100 antialiased">
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
