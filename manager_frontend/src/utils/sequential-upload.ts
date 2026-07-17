export type SequentialUploadProgress = {
  completed: number;
  total: number;
};

export const uploadSequentially = async <Item, Result>(
  items: readonly Item[],
  upload: (item: Item) => Promise<Result>,
  onCompleted?: (result: Result, progress: SequentialUploadProgress) => void,
): Promise<Result[]> => {
  const results: Result[] = [];

  for (const item of items) {
    const result = await upload(item);
    results.push(result);
    onCompleted?.(result, { completed: results.length, total: items.length });
  }

  return results;
};
