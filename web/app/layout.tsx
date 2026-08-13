import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "YBIGTA Data Analysis Agent",
  description: "영화 리뷰 데이터를 MCP를 통해 조회/분석하는 Agent",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
