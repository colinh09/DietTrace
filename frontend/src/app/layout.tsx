import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DietTrace",
  description: "A nutrition agent — describe a meal, see the macros.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
