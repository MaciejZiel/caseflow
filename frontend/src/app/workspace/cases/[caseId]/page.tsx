import { CaseDetailWorkbench } from "@/components/app/case-detail-workbench";

type CaseDetailPageProps = {
  params: Promise<{
    caseId: string;
  }>;
};

export default async function CaseDetailPage({ params }: CaseDetailPageProps) {
  const { caseId } = await params;
  return <CaseDetailWorkbench caseId={caseId} />;
}
