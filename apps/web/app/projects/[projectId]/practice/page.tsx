import type { Metadata } from "next";
import { PracticeClient } from "@/components/practice-client";

export const metadata: Metadata = { title: "Practice", robots: { index: false, follow: false } };

export default async function PracticePage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <PracticeClient projectId={projectId} />;
}
