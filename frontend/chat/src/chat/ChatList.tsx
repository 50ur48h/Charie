import { useState } from "react";
import { useNavigate } from "react-router";
import { Ellipsis, Pencil, Trash2 } from "lucide-react";
import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
  Field,
  IconButton,
  Input,
  Menu,
  MenuContent,
  MenuItem,
  MenuTrigger,
  RouterLink,
  chatGroupClass,
  chatItemClass,
  chatRoutes,
  useDeleteChat,
  useRenameChat,
  type ChatGroup,
} from "@charie/shared";

function RenameDialog({
  title,
  saving,
  serverError,
  onSave,
  onClose,
}: {
  title: string;
  saving: boolean;
  serverError: string | null;
  onSave: (title: string) => void;
  onClose: () => void;
}) {
  const [value, setValue] = useState(title);
  const [blank, setBlank] = useState(false);
  const error = blank ? "Give the chat a title." : serverError;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent aria-label="Rename chat">
        <DialogTitle>Rename chat</DialogTitle>
        <DialogDescription>Give this chat a short, clear title.</DialogDescription>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (value.trim() === "") {
              setBlank(true);
              return;
            }
            onSave(value.trim());
          }}
        >
          <Field label="Title" htmlFor="chat-rename" error={error ?? undefined}>
            <Input
              id="chat-rename"
              value={value}
              maxLength={120}
              onChange={(event) => {
                setValue(event.target.value);
                setBlank(false);
              }}
              aria-invalid={error ? true : undefined}
            />
          </Field>
          <DialogFooter>
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ChatList({
  groups,
  activeChatId,
}: {
  groups: ChatGroup[];
  activeChatId?: number;
}) {
  const navigate = useNavigate();
  const rename = useRenameChat();
  const remove = useDeleteChat();
  const [renaming, setRenaming] = useState<{ id: number; title: string } | null>(null);
  const [deleting, setDeleting] = useState<{ id: number; title: string } | null>(null);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  return (
    <div className="grid gap-2">
      {groups.map((group, gi) => (
        <div key={group.label ?? `group-${gi}`}>
          {group.label && <div className={chatGroupClass}>{group.label}</div>}
          <div className="grid gap-px">
            {group.chats.map((chat) => {
              const isActive = chat.id === activeChatId;
              return (
                <div key={chat.id} className="group relative">
                  <RouterLink
                    to={chatRoutes.chat(chat.id)}
                    className={chatItemClass(isActive)}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <span className="block truncate pr-7">{chat.title}</span>
                  </RouterLink>
                  <Menu>
                    <MenuTrigger asChild>
                      <IconButton
                        label={`Chat actions for ${chat.title}`}
                        title={`Chat actions for ${chat.title}`}
                        className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 focus-visible:opacity-100 group-hover:opacity-100"
                      >
                        <Ellipsis aria-hidden="true" />
                      </IconButton>
                    </MenuTrigger>
                    <MenuContent aria-label={`Chat actions for ${chat.title}`}>
                      <MenuItem
                        icon={Pencil}
                        onSelect={() => {
                          setRenameError(null);
                          setRenaming({ id: chat.id, title: chat.title });
                        }}
                      >
                        Rename
                      </MenuItem>
                      <MenuItem
                        icon={Trash2}
                        tone="danger"
                        onSelect={() => {
                          setDeleteError(null);
                          setDeleting({ id: chat.id, title: chat.title });
                        }}
                      >
                        Delete
                      </MenuItem>
                    </MenuContent>
                  </Menu>
                </div>
              );
            })}
          </div>
        </div>
      ))}
      {deleteError && (
        <p role="alert" className="px-3 text-[13px] text-bad-ink">
          {deleteError}
        </p>
      )}
      {renaming && (
        <RenameDialog
          title={renaming.title}
          saving={rename.isPending}
          serverError={renameError}
          onClose={() => {
            setRenaming(null);
            setRenameError(null);
          }}
          onSave={(title) => {
            setRenameError(null);
            rename.mutate(
              { chatId: renaming.id, title },
              {
                onSuccess: () => setRenaming(null),
                onError: () =>
                  setRenameError("Couldn't save that title. Try again."),
              },
            );
          }}
        />
      )}
      {deleting && (
        <ConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open) {
              setDeleting(null);
              setDeleteError(null);
            }
          }}
          title="Delete this chat?"
          body={`“${deleting.title}” leaves your list for good. This can't be undone.`}
          confirmLabel={remove.isPending ? "Deleting…" : "Delete"}
          onConfirm={() => {
            const target = deleting;
            remove.mutate(target.id, {
              onSuccess: () => {
                setDeleting(null);
                if (target.id === activeChatId) navigate(chatRoutes.home);
              },
              onError: (error) => {
                // A running chat refuses deletion: say so and keep it.
                setDeleteError(
                  error instanceof Error && /running/i.test(error.message)
                    ? "That answer is still running. Wait for it to finish, then delete."
                    : "Couldn't delete that chat. Try again.",
                );
              },
            });
          }}
        />
      )}
    </div>
  );
}
