"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { completeActivity, createActivity, getErrorMessage, getErrorToastMessage, listActivities } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Modal } from "../ui/modal";
import { Select } from "../ui/select";
import { Spinner } from "../ui/spinner";
import { Table, Td, Th } from "../ui/table";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";

const schema = z
  .object({
    activity_type: z.string().min(1),
    subject: z.string().optional(),
    body: z.string().optional(),
    assigned_to_user_id: z.string().optional(),
    due_at: z.string().optional()
  })
  .superRefine((value, ctx) => {
    if (value.activity_type === "Task") {
      if (!value.assigned_to_user_id) {
        ctx.addIssue({ code: "custom", message: "Assigned user is required for tasks", path: ["assigned_to_user_id"] });
      }
      if (!value.due_at) {
        ctx.addIssue({ code: "custom", message: "Due date is required for tasks", path: ["due_at"] });
      }
    }
  });

type FormValues = z.infer<typeof schema>;

export function EntityActivitiesTab({ entityType, entityId }: { entityType: string; entityId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<ToastMessageValue>(null);

  const listQuery = useQuery({
    queryKey: queryKeys.activities(entityType, entityId),
    queryFn: () => listActivities(entityType, entityId)
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { activity_type: "Call", subject: "", body: "", assigned_to_user_id: "", due_at: "" }
  });

  const addMutation = useMutation({
    mutationFn: (values: FormValues) =>
      createActivity(entityType, entityId, {
        activity_type: values.activity_type,
        subject: values.subject || null,
        body: values.body || null,
        assigned_to_user_id: values.activity_type === "Task" ? values.assigned_to_user_id || null : null,
        due_at: values.activity_type === "Task" ? values.due_at || null : null
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.activities(entityType, entityId) });
      form.reset();
      setOpen(false);
      setMessage("Activity added.");
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  const completeMutation = useMutation({
    mutationFn: ({ activityId, rowVersion }: { activityId: string; rowVersion: number }) => completeActivity(activityId, rowVersion),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.activities(entityType, entityId) });
      setMessage("Task completed.");
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Activities</h3>
        <Button onClick={() => setOpen(true)}>Add Activity</Button>
      </div>
      <Toast message={message} tone={toastText(message).toLowerCase().includes("added") || toastText(message).toLowerCase().includes("completed") ? "success" : "error"} />
      {listQuery.isLoading ? (
        <Spinner />
      ) : listQuery.isError ? (
        <p className="text-sm text-red-600">{getErrorMessage(listQuery.error)}</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Type</Th>
              <Th>Subject</Th>
              <Th>Status</Th>
              <Th>Due</Th>
              <Th>Assigned</Th>
              <Th>Action</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {listQuery.data?.map((row) => (
              <tr key={row.id}>
                <Td>{row.activity_type}</Td>
                <Td>{row.subject ?? "-"}</Td>
                <Td>{row.status}</Td>
                <Td>{row.due_at ? new Date(row.due_at).toLocaleString() : "-"}</Td>
                <Td>{row.assigned_to_user_id ?? "-"}</Td>
                <Td>
                  {row.activity_type === "Task" && row.status !== "Completed" ? (
                    <Button
                      variant="secondary"
                      disabled={completeMutation.isPending}
                      onClick={() => completeMutation.mutate({ activityId: row.id, rowVersion: row.row_version })}
                    >
                      Complete
                    </Button>
                  ) : (
                    "-"
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <Modal open={open} title="Add Activity" onClose={() => setOpen(false)}>
        <form className="space-y-3" onSubmit={form.handleSubmit((values) => addMutation.mutate(values))}>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Type</label>
            <Select {...form.register("activity_type")}>
              <option value="Call">Call</option>
              <option value="Email">Email</option>
              <option value="Meeting">Meeting</option>
              <option value="Task">Task</option>
              <option value="Other">Other</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Subject</label>
            <Input {...form.register("subject")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Body</label>
            <Input {...form.register("body")} />
          </div>
          {form.watch("activity_type") === "Task" ? (
            <>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600">Assigned user ID</label>
                <Input {...form.register("assigned_to_user_id")} />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600">Due date</label>
                <Input type="datetime-local" {...form.register("due_at")} />
              </div>
            </>
          ) : null}
          <Button type="submit" disabled={addMutation.isPending}>
            {addMutation.isPending ? "Saving..." : "Save"}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
