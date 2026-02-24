"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createNote, getErrorMessage, getErrorToastMessage, listNotes } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import { Button } from "../ui/button";
import { Spinner } from "../ui/spinner";
import { Table, Td, Th } from "../ui/table";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";
import { useState } from "react";

const schema = z.object({ content: z.string().min(1, "Content is required") });

type FormValues = z.infer<typeof schema>;

export function EntityNotesTab({ entityType, entityId }: { entityType: string; entityId: string }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<ToastMessageValue>(null);

  const listQuery = useQuery({
    queryKey: queryKeys.notes(entityType, entityId),
    queryFn: () => listNotes(entityType, entityId)
  });

  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { content: "" } });

  const createMutation = useMutation({
    mutationFn: (values: FormValues) => createNote(entityType, entityId, { content: values.content, content_format: "markdown" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.notes(entityType, entityId) });
      form.reset();
      setMessage("Note added.");
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold">Notes</h3>
      <Toast message={message} tone={toastText(message).toLowerCase().includes("added") ? "success" : "error"} />
      <form
        className="space-y-2 rounded-lg border border-slate-200 bg-white p-3"
        onSubmit={form.handleSubmit((values) => createMutation.mutate(values))}
      >
        <label className="block text-xs font-medium text-slate-600">Add note</label>
        <textarea
          className="min-h-24 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          {...form.register("content")}
        />
        <Button type="submit" disabled={createMutation.isPending}>
          {createMutation.isPending ? "Saving..." : "Add Note"}
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
              <Th>Content</Th>
              <Th>Format</Th>
              <Th>Updated</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {listQuery.data?.map((note) => (
              <tr key={note.id}>
                <Td>{note.content}</Td>
                <Td>{note.content_format}</Td>
                <Td>{new Date(note.updated_at).toLocaleString()}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
