import type { ChannelUiContribution } from "@/channel-plugins/types";

import { FeishuAssistantsPanel } from "./FeishuAssistantsPanel";

export default {
  Panel: FeishuAssistantsPanel,
  aliases: {
    lark: {
      displayName: "Lark",
      initials: "LK",
      logoUrl: "https://www.larksuite.com/favicon.ico",
    },
  },
  presentation: {
    displayName: "Feishu",
    initials: "FS",
    color: "#3370FF",
    logoUrl: "https://www.feishu.cn/favicon.ico",
    setup: {
      mode: "connect",
      command: "nanobot channels login feishu",
      manualFields: [
        { key: "channels.feishu.appId" },
        { key: "channels.feishu.appSecret" },
        { key: "channels.feishu.domain" },
        { key: "channels.feishu.groupPolicy" },
        { key: "channels.feishu.allowFrom" },
      ],
    },
  },
} satisfies ChannelUiContribution;
