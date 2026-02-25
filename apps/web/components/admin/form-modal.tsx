import React, { type FormEvent, type PropsWithChildren } from "react";

import { Button } from "../ui/button";
import { Modal } from "../ui/modal";

interface FormModalProps extends PropsWithChildren {
  open: boolean;
  title: string;
  submitText: string;
  pending?: boolean;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function FormModal({ open, title, submitText, pending = false, onClose, onSubmit, children }: FormModalProps) {
  return (
    <Modal open={open} title={title} onClose={onClose}>
      <form className="space-y-4" onSubmit={onSubmit}>
        {children}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? "Saving..." : submitText}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
