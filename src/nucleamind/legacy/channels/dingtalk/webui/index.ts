import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "DingTalk",
    initials: "DT",
    color: "#1677FF",
    logoUrl:
      "https://img.alicdn.com/imgextra/i3/O1CN01WMvMRG1ks3Ixc9x1v_!!6000000004738-55-tps-32-32.svg",
    setup: {
      mode: "credentials",
      fields: [
        { key: "channels.dingtalk.clientId" },
        { key: "channels.dingtalk.clientSecret" },
        { key: "channels.dingtalk.allowFrom" },
      ],
    },
  },
} satisfies ChannelUiContribution;
