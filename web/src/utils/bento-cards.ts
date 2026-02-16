import { formatSpec } from './spec-dictionary';

export interface BentoItem {
    label: string;
    value: string;
}

export interface BentoCard {
    id: string;
    layout: 'wide' | 'normal' | 'small';
    priority: number;
    title: string;
    subtitle?: string;
    items?: BentoItem[];
    badges?: string[];
    icon?: string;
    style_hint?: 'teal' | 'orange' | 'blue' | 'default';
    explain?: string;
}

export function generateBentoCards(product: any): BentoCard[] {
    const specs = product.specs || {};
    const cards: BentoCard[] = [];

    // --- Helpers ---
    // Use formatSpec for safe formatting
    const fmt = (key: string, val: any) => {
        const res = formatSpec(key, val);
        return res ? res.value : null;
    };

    const hasTag = (tag: string) => (product.tags || []).some((t: any) => t.slug === tag || t.slug?.includes(tag));
    const compressorNorm = String(specs.compressor_type_norm || '').toLowerCase();

    // --- Priority 1: Area ---
    // REMOVED per user feedback
    /*
    const areaVal = fmt('area_m2', specs.area_m2 || product.area);
    if (areaVal) {
        cards.push({ id: 'area', ... });
    }
    */

    // --- Priority 1: Noise ---
    const noiseVal = fmt('noise_indoor', specs.noise_indoor);
    if (noiseVal) {
        // Humanize noise level
        let explain = 'Стандартный уровень шума';
        // Extract number for logic (simplistic)
        const paramStr = String(specs.noise_indoor);
        const minNoise = parseInt(paramStr.split(/[-–]/)[0] || paramStr);

        if (minNoise < 22) explain = 'Очень тихий';
        else if (minNoise < 26) explain = 'Тихая работа';

        cards.push({
            id: 'noise',
            layout: 'normal',
            priority: 1,
            title: 'Тишина',
            subtitle: 'Уровень шума внутреннего блока',
            items: [{ label: 'Диапазон', value: noiseVal }],
            icon: 'volume_off',
            style_hint: 'default',
            explain
        });
    }

    // --- Priority 1: Cooling (Wide) ---
    const capCool = fmt('capacity_cooling_kw', specs.capacity_cooling_kw);
    if (capCool) {
        const items = [
            { label: 'Выдаёт', value: capCool }
        ];

        const powCool = fmt('power_cons_cooling_kw', specs.power_cons_cooling_kw);
        if (powCool) {
            items.push({ label: 'Потребляет', value: powCool });
        }
        if (specs.seer) {
            items.push({ label: 'SEER', value: String(specs.seer) });
        }
        if (specs.eer) {
            items.push({ label: 'EER', value: String(specs.eer) });
        }

        const badges: string[] = [];
        if (compressorNorm === 'full_dc') badges.push('Full DC Inverter');
        else if (compressorNorm === 'inverter' || specs.is_inverter || product.is_inverter) badges.push('Инвертор');
        else if (compressorNorm === 'on_off') badges.push('On/Off');
        if (specs.energy_class_cool) badges.push(`A${specs.energy_class_cool.replace('A', '')}`);

        cards.push({
            id: 'cooling',
            layout: 'wide',
            priority: 1,
            title: 'Охлаждение',
            subtitle: 'Эффективность в режиме охлаждения',
            items,
            badges,
            icon: 'ac_unit', // snowflake substitute
            style_hint: 'blue'
        });
    }

    // --- Priority 1: Heating (Wide) ---
    const capHeat = fmt('capacity_heating_kw', specs.capacity_heating_kw);
    if (capHeat) {
        const items = [
            { label: 'Выдаёт', value: capHeat }
        ];

        const powHeat = fmt('power_cons_heating_kw', specs.power_cons_heating_kw);
        if (powHeat) {
            items.push({ label: 'Потребляет', value: powHeat });
        }
        if (specs.scop) {
            items.push({ label: 'SCOP', value: String(specs.scop) });
        }
        if (specs.cop) {
            items.push({ label: 'COP', value: String(specs.cop) });
        }

        const badges: string[] = [];
        let minTemp = null;
        if (specs.temp_range_heat) {
            // Try to extract min temp like -15, -20, -30
            const match = String(specs.temp_range_heat).match(/-(\d+)/);
            if (match) minTemp = `-${match[1]}`;
        }
        // Check tags if explicit temp not found or to confirm
        if (!minTemp) {
            if (hasTag('winter-30')) minTemp = '-30';
            else if (hasTag('winter-25')) minTemp = '-25';
            else if (hasTag('winter-20')) minTemp = '-20';
            else if (hasTag('winter-15')) minTemp = '-15';
        }

        if (minTemp) badges.push(`до ${minTemp}°C`);

        let explain = minTemp ? 'Можно греться зимой' : 'Идеально для межсезонья';

        // Refining explain logic based on temp and merging into a single banner text
        if (minTemp) {
            const t = parseInt(minTemp); // e.g. -25
            if (t <= -20) explain = `Можно использовать даже в мороз до ${minTemp}°C`;
            else if (t <= -15) explain = `Межсезонье и легкие морозы до ${minTemp}°C`;
            else explain = `Межсезонье (до ${minTemp}°C)`;

            // Clear badges as we moved info to explain
            badges.length = 0;
        }

        cards.push({
            id: 'heating',
            layout: 'wide',
            priority: 1,
            title: 'Обогрев',
            subtitle: 'Работа в режиме теплового насоса',
            items,
            badges, // Badges will still hold the specific temp like "to -25°C"
            icon: 'wb_sunny',
            style_hint: 'orange',
            explain
        });
    }

    // --- Priority 2: WiFi ---
    const isWifi =
        specs.wifi_ready === true ||
        specs.wifi_ready === 'true' ||
        specs.wifi_ready === 'Да' ||
        specs['wifi-ready'] === true ||
        specs['wifi-ready'] === 'true' ||
        specs['wifi-builtin'] === true ||
        specs['wifi-builtin'] === 'true';
    if (isWifi) {
        cards.push({
            id: 'wifi',
            layout: 'normal',
            priority: 2,
            title: 'Wi-Fi',
            subtitle: 'Удаленное управление',
            badges: [],
            icon: 'wifi',
            style_hint: 'blue',
            explain: 'Удобно управлять с телефона'
        });
    }

    // --- Priority 2: Airflow ---
    const airflow = fmt('airflow_max', specs.airflow_max);
    if (airflow) {
        cards.push({
            id: 'airflow',
            layout: 'normal',
            priority: 2,
            title: 'Поток воздуха',
            items: [{ label: 'Объем', value: airflow }], // Simplified
            icon: 'air',
            style_hint: 'default'
        });
    }

    // --- Priority 3: Small Cards (Freon, etc) ---
    if (specs.freon_type) {
        cards.push({
            id: 'freon',
            layout: 'small',
            priority: 3,
            title: 'Фреон',
            items: [{ label: 'Тип', value: specs.freon_type }],
            icon: 'science', // or propane if available, but science is generic enough
            style_hint: 'default'
        });
    }

    return cards.sort((a, b) => a.priority - b.priority);
}
