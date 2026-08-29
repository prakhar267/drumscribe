import type { Metadata } from "next";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { AppTopbar } from "@/components/app-topbar";
import { ProjectSettings } from "@/components/project-settings";

export const metadata: Metadata = { title: "Project settings", robots: { index: false, follow: false } };

export default async function ProjectSettingsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <div className="app-shell"><AppTopbar /><main className="page-shell" id="main-content"><div className="page-heading"><div><p className="eyebrow">Project settings</p><h1>Project details</h1></div><Link className="button button-small" href={`/projects/${projectId}`}><ChevronLeft size={15} /> Back to editor</Link></div><ProjectSettings projectId={projectId} /></main></div>;
}
