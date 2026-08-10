import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "Discord",
    initials: "DC",
    color: "#5865F2",
    logoUrl: "https://discord.com/favicon.ico",
    setup: {
      mode: "credentials",
      fields: [
        { key: "channels.discord.token" },
        { key: "channels.discord.allowChannels" },
        { key: "channels.discord.groupPolicy" },
      ],
    },
  },
} satisfies ChannelUiContribution;
