import React from "react";

import type { CustomFieldDefinitionRead } from "../../../lib/types";
import { Table, Td, Th } from "../../ui/table";
import { Button } from "../../ui/button";

interface CustomFieldDefinitionsTableProps {
  definitions: CustomFieldDefinitionRead[];
  canManage: boolean;
  onEdit: (definition: CustomFieldDefinitionRead) => void;
}

export function CustomFieldDefinitionsTable({ definitions, canManage, onEdit }: CustomFieldDefinitionsTableProps) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Label</Th>
          <Th>Key</Th>
          <Th>Type</Th>
          <Th>Required</Th>
          <Th>Allowed values</Th>
          <Th>Active</Th>
          <Th>Scope</Th>
          <Th>Actions</Th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {definitions.map((definition) => (
          <tr key={definition.id}>
            <Td>{definition.label}</Td>
            <Td>{definition.field_key}</Td>
            <Td>{definition.data_type}</Td>
            <Td>{definition.is_required ? "Yes" : "No"}</Td>
            <Td>{definition.allowed_values?.join(", ") || "-"}</Td>
            <Td>{definition.is_active ? "Yes" : "No"}</Td>
            <Td>{definition.legal_entity_id ? `LE:${definition.legal_entity_id}` : "Global"}</Td>
            <Td>
              {canManage ? (
                <Button variant="secondary" onClick={() => onEdit(definition)}>
                  Edit
                </Button>
              ) : (
                <span className="text-slate-400">-</span>
              )}
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
