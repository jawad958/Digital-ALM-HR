import { ComingSoon } from "@/components/ComingSoon";

export const metadata = { title: "Templates" };

export default function TemplatesSettingsPage() {
  return (
    <ComingSoon
      crumb="Settings · Templates"
      title="Templates"
      sub="Email, WhatsApp and offer letter templates. Edit without a deploy."
      week="Week 7"
    />
  );
}
