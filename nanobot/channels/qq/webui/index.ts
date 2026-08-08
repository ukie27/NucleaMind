import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "QQ",
    initials: "QQ",
    color: "#12B7F5",
    logoUrl: "https://im.qq.com/favicon.ico",
    setup: {
      mode: "credentials",
      fields: [
        { key: "channels.qq.appId" },
        { key: "channels.qq.secret" },
        { key: "channels.qq.allowFrom" },
        { key: "channels.qq.msgFormat" },
      ],
    },
  },
} satisfies ChannelUiContribution;
