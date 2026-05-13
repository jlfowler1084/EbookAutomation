"use client";

import { useRouter } from "next/navigation";
import UploadZone from "../components/UploadZone";

export default function UploadForm() {
  const router = useRouter();

  const handleJobStarted = (jobId: string) => {
    router.push(`/status/${jobId}`);
  };

  return <UploadZone onJobStarted={handleJobStarted} />;
}
