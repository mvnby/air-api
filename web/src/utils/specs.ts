export interface Dimensions {
    w: string;
    h: string;
    d: string;
}

export interface ProductDimensions {
    inner: Dimensions | null;
    outer: Dimensions | null;
    weightInner?: string;
    weightOuter?: string;
}

export interface ProductPerformance {
    powerCooling: string | null;
    powerHeating: string | null;
    noiseInner: string | null;
    noiseOuter: string | null;
    energyClass: string | null; // EER/COP or simply Class A++
    wifi: boolean;
    freon: string | null;
    year: string | null;
}

export function getDimensions(specs: Record<string, string>): ProductDimensions {
    const getVal = (keyPart: string) => {
        // Find key containing keyPart (case insensitive)
        const key = Object.keys(specs).find(k => k.toLowerCase().includes(keyPart.toLowerCase()));
        return key ? specs[key] : null;
    };

    // Inner
    const innerW = getVal("Ширина внутреннего");
    const innerH = getVal("Высота внутреннего");
    const innerD = getVal("Глубина внутреннего");
    const weightInner = getVal("Вес внутреннего");

    // Outer
    const outerW = getVal("Ширина наружного");
    const outerH = getVal("Высота наружного");
    const outerD = getVal("Глубина наружного");
    const weightOuter = getVal("Вес наружного");

    return {
        inner: innerW && innerH && innerD ? { w: innerW, h: innerH, d: innerD } : null,
        outer: outerW && outerH && outerD ? { w: outerW, h: outerH, d: outerD } : null,
        weightInner: weightInner || undefined,
        weightOuter: weightOuter || undefined
    };
}

export function getPerformance(specs: Record<string, string>): ProductPerformance {
    const getVal = (keyPart: string) => {
        const key = Object.keys(specs).find(k => k.toLowerCase().includes(keyPart.toLowerCase()));
        return key ? specs[key] : null;
    };

    const hasWifi = Object.keys(specs).some(k => k.toLowerCase().includes('wi-fi') && specs[k]?.toLowerCase().includes('да'));

    return {
        powerCooling: getVal("Мощность охлаждения"),
        powerHeating: getVal("Мощность обогрева"),
        noiseInner: getVal("Шум внутреннего"),
        noiseOuter: getVal("Шум наружного"),
        energyClass: getVal("Энергоэффективность при охлаждении (EER)") || getVal("Класс энергоэффективности"),
        wifi: hasWifi,
        freon: getVal("Фреон") || getVal("Хладагент"),
        year: getVal("Год") || getVal("Модельный год")
    };
}

export function getOtherSpecs(specs: Record<string, string>): Record<string, string> {
    const hiddenKeys = [
        "Ширина", "Высота", "Глубина", "Вес", "Мощность", "Шум", "Энерго", "Фреон", "Хладагент", "Год", "Wi-Fi"
    ];

    const other: Record<string, string> = {};
    for (const [k, v] of Object.entries(specs)) {
        if (!hiddenKeys.some(hidden => k.includes(hidden))) {
            other[k] = v;
        }
    }
    return other;
}
