import type { Metadata } from "next";
import { EditorClient } from "@/components/editor/editor-client";

export const metadata: Metadata = { title: "Editor", robots: { index: false, follow: false } };

export default async function EditorPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <main id="main-content"><EditorClient projectId={projectId} /></main>;
}
