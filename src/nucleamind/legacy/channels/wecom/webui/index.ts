import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "WeCom",
    initials: "WC",
    color: "#2F7DFF",
    logoUrl: "https://work.weixin.qq.com/favicon.ico",
    setup: {
      mode: "credentials",
      fields: [
        { key: "channels.wecom.botId" },
        { key: "channels.wecom.secret" },
        { key: "channels.wecom.allowFrom" },
      ],
    },
  },
} satisfies ChannelUiContribution;
