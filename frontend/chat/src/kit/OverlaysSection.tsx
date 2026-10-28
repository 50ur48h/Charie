import { useState } from "react";
import {
  Button,
  ConfirmDialog,
  IconButton,
  Menu,
  MenuContent,
  MenuItem,
  MenuSeparator,
  MenuTrigger,
  Progress,
  Skeleton,
  Spinner,
  Toaster,
  Tooltip,
  TooltipProvider,
  toast,
} from "@charie/shared";
import { Download, Ellipsis, FileDown, Pencil, Trash2 } from "lucide-react";
import KitSection from "./KitSection";

export default function OverlaysSection() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  return (
    <KitSection id="overlays" title="Building blocks 2">
      <TooltipProvider>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setConfirmOpen(true)}>Forget everything</Button>
          <Menu>
            <MenuTrigger asChild>
              <IconButton label="Chat actions">
                <Ellipsis />
              </IconButton>
            </MenuTrigger>
            <MenuContent>
              <MenuItem icon={Pencil}>Rename</MenuItem>
              <MenuItem icon={FileDown}>Download as PDF</MenuItem>
              <MenuSeparator />
              <MenuItem icon={Trash2} tone="danger">
                Delete
              </MenuItem>
            </MenuContent>
          </Menu>
          <Tooltip content="Download as image">
            <IconButton label="Download as image">
              <Download />
            </IconButton>
          </Tooltip>
          <Button variant="soft" onClick={() => toast("Saved. Charie is re-checking what this affects.")}>
            Show a toast
          </Button>
        </div>
        <ConfirmDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Forget everything?"
          body="Charie forgets every preference you told it. This can't be undone."
          confirmLabel="Forget everything"
          tone="danger"
          onConfirm={() => toast("Forgot everything.")}
        />
        <div className="mt-4 grid max-w-[420px] gap-2">
          <Skeleton className="h-3 w-2/5" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-full" />
        </div>
        <div className="mt-4 grid max-w-[420px] gap-3">
          <Progress label="Learning" value={62} />
          <Progress label="Checking" value={27.5} thin />
        </div>
        <div className="mt-4">
          <Spinner label="Loading" />
        </div>
        <Toaster />
      </TooltipProvider>
    </KitSection>
  );
}
