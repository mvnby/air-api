export const brandConfig: Record<string, { logo?: string, color?: string }> = {
    'haier': { logo: '/img/logos/haier.svg', color: 'text-blue-600' },
    'tcl': { logo: '/img/logos/tcl.svg', color: 'text-red-500' },
    'mdv': { logo: '/img/logos/mdv.svg', color: 'text-blue-800' },
    'chigo': { logo: '/img/logos/chigo.svg', color: 'text-orange-500' },
    'hisense': { logo: '/img/logos/hisense.svg', color: 'text-teal-600' },
    'aux': { logo: '/img/logos/aux.svg', color: 'text-red-600' },
    'lg': { logo: '/img/logos/lg.svg', color: 'text-blue-600' },
    'mitsubishi': { logo: '/img/logos/mitsubishi.svg', color: 'text-red-600' },
    'daikin': { logo: '/img/logos/daikin.svg', color: 'text-blue-600' },
    'gree': { logo: '/img/logos/gree.svg', color: 'text-green-600' },
    'electrolux': { logo: '/img/logos/electrolux.svg', color: 'text-blue-600' },
    'ballu': { logo: '/img/logos/ballu.svg', color: 'text-red-600' },
};

export const getBrandConfig = (slug: string) => {
    return brandConfig[slug.toLowerCase()] || {};
};

export const formatBrandProductCount = (count: number): string => {
    const normalized = Number.isFinite(count) ? Math.max(0, Math.trunc(count)) : 0;
    const lastDigit = normalized % 10;
    const lastTwoDigits = normalized % 100;
    const noun =
        lastDigit === 1 && lastTwoDigits !== 11
            ? "модель"
            : lastDigit >= 2 && lastDigit <= 4 && (lastTwoDigits < 12 || lastTwoDigits > 14)
              ? "модели"
              : "моделей";

    return `${normalized} ${noun}`;
};
