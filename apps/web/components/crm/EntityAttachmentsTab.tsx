"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createAttachment, getErrorMessage, getErrorToastMessage, listAttachments } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Spinner } from "../ui/spinner";
import { Table, Td, Th } from "../ui/table";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";

const schema = z.object({ file_id: z.string().uuid("file_id must be a UUID") });

type FormValues = z.infer<typeof schema>;

export function EntityAttachmentsTab({ entityType, entityId }: { entityType: string; entityId: string }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<ToastMessageValue>(null);

  const listQuery = useQuery({
    queryKey: queryKeys.attachments(entityType, entityId),
    queryFn: () => listAttachments(entityType, entityId)
  });

  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { file_id: "" } });

  const mutation = useMutation({
    mutationFn: (values: FormValues) => createAttachment(entityType, entityId, values),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.attachments(entityType, entityId) });
      form.reset();
      setMessage("Attachment linked.");
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold">Attachments</h3>
      <Toast message={message} tone={toastText(message).toLowerCase().includes("linked") ? "success" : "error"} />
      <form className="flex items-end gap-2" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
        <div className="flex-1">
          <label className="mb-1 block text-xs font-medium text-slate-600">file_id</label>
          <Input {...form.register("file_id")} placeholder="UUID" />
        </div>
        <Button type="submit" disabled={mutation.isPending}>
          Add Link
        </Button>
      </form>

      {listQuery.isLoading ? (
        <Spinner />
      ) : listQuery.isError ? (
        <p className="text-sm text-red-600">{getErrorMessage(listQuery.error)}</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>file_id</Th>
              <Th>Created</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {listQuery.data?.map((item) => (
              <tr key={item.id}>
                <Td>{item.file_id}</Td>
                <Td>{new Date(item.created_at).toLocaleString()}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
