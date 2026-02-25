import { AccessDeniedPanel } from "../../components/access-denied-panel";

export default function AccessDeniedPage({ searchParams }: { searchParams?: { code?: string } }) {
  const raw = searchParams?.code;
  const statusCode: 401 | 403 = raw === "401" ? 401 : 403;
  return <AccessDeniedPanel statusCode={statusCode} />;
}
