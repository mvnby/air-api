export const brandConfig: Record<string, { logo?: string, color?: string }> = {
    'haier': { logo: '/img/logos/haier.svg', color: 'text-blue-600' },
    'tcl': { logo: '/img/logos/tcl.svg', color: 'text-red-500' },
    'mdv': { logo: '/img/logos/mdv.svg', color: 'text-blue-800' },
    'chigo': { logo: '/img/logos/chigo.svg', color: 'text-orange-500' },
    'hisense': { logo: '/img/logos/hisense.svg', color: 'text-teal-600' },
    'aux': { logo: '/img/logos/aux.svg', color: 'text-red-600' },
};

export const getBrandConfig = (slug: string) => {
    return brandConfig[slug.toLowerCase()] || {};
};
