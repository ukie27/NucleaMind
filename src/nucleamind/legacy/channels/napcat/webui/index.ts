import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "NapCat",
    initials: "NC",
    color: "#F97316",
    logoUrl: "https://napneko.github.io/favicon.ico",
    setup: {
      mode: "credentials",
      fields: [
        { key: "channels.napcat.wsUrl" },
        { key: "channels.napcat.accessToken" },
        { key: "channels.napcat.groupPolicy" },
        { key: "channels.napcat.allowFrom" },
      ],
    },
  },
} satisfies ChannelUiContribution;
