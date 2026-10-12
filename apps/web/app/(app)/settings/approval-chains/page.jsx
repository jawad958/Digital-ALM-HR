import { ComingSoon } from "@/components/ComingSoon";

export const metadata = { title: "Approval chains" };

export default function ApprovalChainsSettingsPage() {
  return (
    <ComingSoon
      crumb="Settings · Approval chains"
      title="Approval chains"
      sub="Edit chains per request type (hiring, offer, leave, comp change, asset). The engine already supports this; the UI ships in Week 2."
      week="Week 2"
    />
  );
}
