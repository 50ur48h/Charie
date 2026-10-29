import {
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  toast,
  useDatabaseSource,
} from "@charie/shared";
import { DatabaseForm } from "./DatabaseForm";

// The Sources Edit dialog (P04.4). P04.2's DatabaseForm does the work; Save
// sends PUT, closes the dialog and toasts. Errors stay in the form's red box.
export function EditDatabaseDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const source = useDatabaseSource();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Database connection</DialogTitle>
        {source.isPending ? (
          <p className="mt-4 text-[14px] text-muted" role="status">
            Loading the saved connection…
          </p>
        ) : source.isError || !source.data ? (
          <p className="mt-4 text-[14px] text-muted" role="alert">
            Couldn&rsquo;t load the saved connection.{" "}
            <button
              type="button"
              className="font-medium text-accent-ink underline-offset-2 hover:underline"
              onClick={() => void source.refetch()}
            >
              Try again
            </button>
          </p>
        ) : (
          <div className="mt-4">
            <DatabaseForm
              key={source.data.source ? "saved" : "empty"}
              initial={source.data.source}
              submitLabel="Save"
              onSubmitted={() => {
                toast("Connection saved.");
                onOpenChange(false);
              }}
              cancel={
                <Button variant="ghost" onClick={() => onOpenChange(false)}>
                  Cancel
                </Button>
              }
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
