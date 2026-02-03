// src/utils/specs.ts
import { formatSpec } from "./spec-dictionary";

// Функция очистки для габаритов (тут нам нужны чистые цифры для SVG)
function cleanVal(val: any): string {
    if (!val) return "";
    return String(val)
        .replace(" мм", "")
        .replace(" кг", "")
        .replace(",", ".") // На всякий случай меняем запятую на точку для SVG
        .trim();
}

/**
 * Получаем габариты для SVG-схем
 */
export function getDimensions(specs: any) {
    // Ищем хоть какие-то признаки внутреннего блока
    const hasInner = specs.width_indoor || specs.height_indoor || specs.depth_indoor;
    
    const inner = hasInner ? {
        w: cleanVal(specs.width_indoor),
        h: cleanVal(specs.height_indoor),
        d: cleanVal(specs.depth_indoor),
    } : null;

    // Ищем признаки внешнего блока
    const hasOuter = specs.width_outdoor || specs.height_outdoor || specs.depth_outdoor;

    const outer = hasOuter ? {
        w: cleanVal(specs.width_outdoor),
        h: cleanVal(specs.height_outdoor),
        d: cleanVal(specs.depth_outdoor),
    } : null;

    // Вес форматируем через умную функцию, чтобы получить "кг" только один раз
    const weightInnerSpec = formatSpec("weight_indoor", specs.weight_indoor);
    const weightOuterSpec = formatSpec("weight_outdoor", specs.weight_outdoor);

    return {
        inner,
        outer,
        weightInner: weightInnerSpec ? weightInnerSpec.value : null,
        weightOuter: weightOuterSpec ? weightOuterSpec.value : null
    };
}

/**
 * Получаем данные для Бенто-карточки (производительность)
 */
export function getPerformance(specs: any) {
    // Используем умный форматтер для основных цифр
    // Он сам проверит, есть ли "кВт", и добавит только если нет.
    
    const coolingSpec = formatSpec("capacity_cooling_kw", specs.capacity_cooling_kw);
    const heatingSpec = formatSpec("capacity_heating_kw", specs.capacity_heating_kw);
    
    // Для классов энергоэффективности у нас нет юнитов, берем как есть или "A"
    const energyClass = specs.energy_class_cool || specs.energy_class_heat || "A";

    // Фреон
    const freonSpec = formatSpec("freon_type", specs.freon_type);

    return {
        // Значения для карточки (берем .value из результата formatSpec)
        powerCooling: coolingSpec ? coolingSpec.value : null,
        powerHeating: heatingSpec ? heatingSpec.value : null,
        energyClass: energyClass,
        
        // Дополнительные поля
        freon: freonSpec ? freonSpec.value : null,
        
        // Wifi нужен boolean для иконки
        wifi: specs.wifi_ready === true || specs.wifi_ready === "true" || specs.wifi_ready === "да", 
        
        year: specs.release_year || null,
        
        // Для логики "Зимний комплект" (ищем -25 или -30 в строке температур)
        minTempHeat: specs.temp_range_heat || null
    };
}

export function getOtherSpecs(specs: any) {
    return specs;
}