type DocumentRevision = {
  id: number;
  status: string;
  replaces_document_id?: number | null;
};

export const isHistoricalDocument = (document: Pick<DocumentRevision, 'status'>) => (
  document.status === 'replaced' || document.status === 'void'
);

/** Follow saved replacement links; unrelated cancellations stay in the order history. */
export const groupDocumentVersions = <T extends DocumentRevision>(documents: T[]) => {
  const byId = new Map(documents.map((document) => [document.id, document]));
  const current = documents.filter((document) => !isHistoricalDocument(document));
  const assigned = new Set<number>();
  const histories = new Map<number, T[]>();

  // A pending correction must not take the history away from its issued original.
  const owners = [...current].sort((left, right) => (
    Number(left.status === 'draft') - Number(right.status === 'draft')
  ));
  for (const document of owners) {
    const previousVersions: T[] = [];
    const visited = new Set([document.id]);
    let previousId = document.replaces_document_id;
    while (previousId && !visited.has(previousId)) {
      visited.add(previousId);
      const previous = byId.get(previousId);
      if (!previous || !isHistoricalDocument(previous) || assigned.has(previousId)) break;
      previousVersions.push(previous);
      assigned.add(previousId);
      previousId = previous.replaces_document_id;
    }
    histories.set(document.id, previousVersions);
  }

  return {
    current: current.map((document) => ({ document, previousVersions: histories.get(document.id) || [] })),
    archived: documents.filter((document) => isHistoricalDocument(document) && !assigned.has(document.id)),
  };
};
