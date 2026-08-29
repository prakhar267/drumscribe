import type { Metadata } from "next";
import { AppTopbar } from "@/components/app-topbar";
import { ProjectsDashboard } from "@/components/projects-dashboard";

export const metadata: Metadata = { title: "Projects", robots: { index: false, follow: false } };

export default function ProjectsPage() {
  return <div className="app-shell"><AppTopbar /><ProjectsDashboard /></div>;
}
