"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createContact, getErrorToastMessage, listContacts } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Modal } from "../ui/modal";
import { Spinner } from "../ui/spinner";
import { Table, Td, Th } from "../ui/table";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";

const formSchema = z.object({
  first_name: z.string().min(1, "First name is required"),
  last_name: z.string().min(1, "Last name is required"),
  email: z.string().email("Invalid email").optional().or(z.literal("")),
  is_primary: z.boolean().default(false)
});

type ContactForm = z.infer<typeof formSchema>;

export function AccountContactsTab({ accountId }: { accountId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<ToastMessageValue>(null);

  const contactsQuery = useQuery({
    queryKey: queryKeys.contacts(accountId, {}),
    queryFn: () => listContacts(accountId, {})
  });

  const form = useForm<ContactForm>({
    resolver: zodResolver(formSchema),
    defaultValues: { first_name: "", last_name: "", email: "", is_primary: false }
  });

  const createMutation = useMutation({
    mutationFn: async (values: ContactForm) =>
      createContact(accountId, {
        account_id: accountId,
        first_name: values.first_name,
        last_name: values.last_name,
        email: values.email || null,
        is_primary: values.is_primary
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.contacts(accountId, {}) });
      setOpen(false);
      form.reset();
      setMessage("Contact added.");
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Contacts</h3>
        <Button onClick={() => setOpen(true)}>Add Contact</Button>
      </div>
      <Toast message={message} tone={toastText(message).toLowerCase().includes("added") ? "success" : "error"} />
      {contactsQuery.isLoading ? (
        <Spinner />
      ) : contactsQuery.isError ? (
        <p className="text-sm text-red-600">{getErrorMessage(contactsQuery.error)}</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Email</Th>
              <Th>Primary</Th>
              <Th>Updated</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {contactsQuery.data?.map((contact) => (
              <tr key={contact.id}>
                <Td>{`${contact.first_name} ${contact.last_name}`}</Td>
                <Td>{contact.email ?? "-"}</Td>
                <Td>{contact.is_primary ? "Yes" : "No"}</Td>
                <Td>{new Date(contact.updated_at).toLocaleString()}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <Modal open={open} title="Add Contact" onClose={() => setOpen(false)}>
        <form className="space-y-3" onSubmit={form.handleSubmit((values) => createMutation.mutate(values))}>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">First name</label>
            <Input {...form.register("first_name")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Last name</label>
            <Input {...form.register("last_name")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Email</label>
            <Input {...form.register("email")} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...form.register("is_primary")} />
            Primary contact
          </label>
          <Button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? "Saving..." : "Save"}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
