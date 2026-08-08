import { Network } from "lucide-react";

import type { ChannelUiContribution } from "@/channel-plugins/types";

export default {
  presentation: {
    displayName: "WebSocket",
    initials: "WS",
    color: "#111827",
    icon: Network,
    setup: {
      mode: "webui",
    },
  },
} satisfies ChannelUiContribution;
