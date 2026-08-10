import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "Telegram",
    initials: "TG",
    color: "#229ED9",
    logoUrl: "https://telegram.org/favicon.ico",
    setup: {
      mode: "credentials",
      fields: [
        { key: "channels.telegram.token" },
        { key: "channels.telegram.proxy" },
        { key: "channels.telegram.allowFrom" },
        { key: "channels.telegram.groupPolicy" },
      ],
    },
  },
} satisfies ChannelUiContribution;
