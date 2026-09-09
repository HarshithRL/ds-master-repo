import { Library, Paperclip, Plus } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function ChatAttachMenu({ onAddFile, disabled = false }) {
  const fileAttachDisabled = disabled || !onAddFile;

  function handleFileAttach() {
    if (fileAttachDisabled) {
      return;
    }
    onAddFile();
  }

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger
        type="button"
        className="ws-chat-attach"
        aria-label="Add"
        aria-haspopup="menu"
      >
        <Plus aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side="top"
        align="start"
        sideOffset={8}
        className="ws-chat-attach-menu w-auto min-w-[220px]"
      >
        <DropdownMenuGroup>
          <DropdownMenuItem
            disabled={fileAttachDisabled}
            onClick={handleFileAttach}
          >
            <Paperclip data-icon="inline-start" aria-hidden="true" />
            file attach
          </DropdownMenuItem>
          <DropdownMenuItem>
            <Library data-icon="inline-start" aria-hidden="true" />
            index
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default ChatAttachMenu;
