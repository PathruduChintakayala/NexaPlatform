import React from "react";

import { Button } from "../ui/button";
import { Modal } from "../ui/modal";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmText?: string;
  pending?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmText = "Confirm",
  pending = false,
  onClose,
  onConfirm
}: ConfirmDialogProps) {
  return (
    <Modal open={open} title={title} onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm text-slate-700">{description}</p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={pending}>
            {pending ? "Working..." : confirmText}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
