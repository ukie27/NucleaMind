import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "Mattermost",
    initials: "MM",
    color: "#1C58D9",
    logoUrl: "https://mattermost.com/favicon.ico",
    setup: {
      mode: "credentials",
      fields: [
        { key: "channels.mattermost.serverUrl" },
        { key: "channels.mattermost.token" },
        { key: "channels.mattermost.teamId" },
        { key: "channels.mattermost.groupPolicy" },
        { key: "channels.mattermost.groupPolicyInThread" },
      ],
    },
  },
} satisfies ChannelUiContribution;
