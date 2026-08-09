import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "울산컬처",
  description: "좋은 체험, 신청일을 놓치지 마세요.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}

