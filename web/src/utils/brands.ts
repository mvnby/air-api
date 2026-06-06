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

const escapeHtml = (value: string): string =>
    value
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");

const isSafeMarkdownUrl = (value: string): boolean => {
    const url = value.trim();
    if (!url || /[\u0000-\u001F\s]/.test(url)) return false;
    if (url.startsWith("/")) return !url.startsWith("//");
    if (url.startsWith("#")) return true;

    try {
        const parsed = new URL(url);
        return ["http:", "https:", "mailto:", "tel:"].includes(parsed.protocol);
    } catch {
        return false;
    }
};

const renderInlineMarkdown = (value: string): string => {
    let html = escapeHtml(value);

    html = html.replace(/\[([^\]]+)]\(([^)]+)\)/g, (match, label: string, url: string) => {
        const trimmedUrl = url.trim();
        if (!isSafeMarkdownUrl(trimmedUrl)) return label;
        return `<a href="${escapeHtml(trimmedUrl)}" rel="noopener noreferrer">${label}</a>`;
    });
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");

    return html;
};

export const renderBrandIntroMarkdown = (markdown: string): string => {
    const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
    const blocks: string[] = [];
    let paragraph: string[] = [];
    let listItems: string[] = [];

    const flushParagraph = () => {
        if (!paragraph.length) return;
        blocks.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
        paragraph = [];
    };
    const flushList = () => {
        if (!listItems.length) return;
        blocks.push(`<ul>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ul>`);
        listItems = [];
    };

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
            flushParagraph();
            flushList();
            continue;
        }

        const listMatch = /^[-*]\s+(.+)$/.exec(trimmed);
        if (listMatch) {
            flushParagraph();
            listItems.push(listMatch[1]);
            continue;
        }

        flushList();
        paragraph.push(trimmed);
    }

    flushParagraph();
    flushList();

    return blocks.join("");
};

export const getBrandIntroPlainText = (markdown: string): string =>
    String(markdown || "")
        .replace(/\[([^\]]+)]\(([^)]+)\)/g, "$1")
        .replace(/\*\*([^*]+)\*\*/g, "$1")
        .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1$2")
        .replace(/^[-*]\s+/gm, "")
        .replace(/\s+/g, " ")
        .trim();

export const getBrandIntro = (title: string, description?: string | null): string => {
    const ownDescription = String(description || "").trim();
    if (ownDescription) return ownDescription;

    const brandTitle = String(title || "").trim() || "бренда";
    return `Подбор кондиционеров ${brandTitle} в Витебске: поможем выбрать модель под площадь помещения, условия монтажа и бюджет. Перед заказом уточним наличие и параметры установки.`;
};
