import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "WhatsApp",
    initials: "WA",
    color: "#25D366",
    logoUrl: "https://www.whatsapp.com/favicon.ico",
    setup: {
      mode: "connect",
      command: "nanobot channels login whatsapp",
      manualFields: [
        { key: "channels.whatsapp.allowFrom" },
        { key: "channels.whatsapp.groupPolicy" },
      ],
    },
  },
} satisfies ChannelUiContribution;
