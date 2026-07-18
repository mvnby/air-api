export const pluralRu = (count: number, one: string, few: string, many: string) => {
  const absolute = Math.abs(count);
  const lastTwo = absolute % 100;
  const last = absolute % 10;
  if (last === 1 && lastTwo !== 11) return one;
  if (last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14)) return few;
  return many;
};

export const countLabel = (count: number, one: string, few: string, many: string) =>
  `${new Intl.NumberFormat('ru-RU').format(count)} ${pluralRu(count, one, few, many)}`;
