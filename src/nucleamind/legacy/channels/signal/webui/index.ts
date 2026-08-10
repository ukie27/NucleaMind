import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "Signal",
    initials: "SG",
    color: "#3A76F0",
    logoUrl: "https://signal.org/favicon.ico",
    setup: {
      mode: "credentials",
      fields: [
        { key: "channels.signal.phoneNumber" },
        { key: "channels.signal.daemonHost" },
        { key: "channels.signal.daemonPort" },
        { key: "channels.signal.dm.allowFrom" },
        { key: "channels.signal.group.allowFrom" },
      ],
    },
  },
} satisfies ChannelUiContribution;
