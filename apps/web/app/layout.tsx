import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { TransportProvider } from "@/components/transport-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "DrumScribe — Turn songs into editable drum charts", template: "%s · DrumScribe" },
  description: "Upload a recording, generate an editable drum chart, fix the details, and practise in sync.",
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  colorScheme: "dark",
  themeColor: "#0a0c10",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <a className="skip-link" href="#main-content">Skip to content</a>
        <TransportProvider>{children}</TransportProvider>
      </body>
    </html>
  );
}
