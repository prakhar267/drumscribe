import type { Metadata } from "next";
import { Brand } from "@/components/brand";
import { JobProgress } from "@/components/job-progress";

export const metadata: Metadata = { title: "Building your drum chart", robots: { index: false, follow: false } };

export default async function JobPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  return (
    <div>
      <div style={{ position: "absolute", top: 24, left: 28, zIndex: 2 }}><Brand /></div>
      <JobProgress jobId={jobId} />
    </div>
  );
}
