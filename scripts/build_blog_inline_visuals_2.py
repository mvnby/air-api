#!/usr/bin/env python3
"""Build the second deterministic MVN Climate Atlas inline-diagram set."""

from build_blog_inline_visuals import (
    AMBER,
    CORAL,
    DEEP,
    GRAPHITE,
    ICE,
    MIST,
    OUT,
    TEAL,
    arrow,
    indoor_unit,
    outdoor_unit,
    shell,
)


def multiline(x: int, y: int, lines: list[str], css_class: str = "note", gap: int = 27) -> str:
    spans = "".join(
        f'<tspan x="{x}" dy="{0 if index == 0 else gap}">{line}</tspan>'
        for index, line in enumerate(lines)
    )
    return f'<text x="{x}" y="{y}" text-anchor="middle" class="{css_class}">{spans}</text>'


def arrow_left(x1: int, y1: int, x2: int, y2: int, color: str, width: int = 5) -> str:
    return f'''<path d="M{x1} {y1} L{x2} {y2}" class="line" stroke="{color}" stroke-width="{width}"/>
      <path d="M{x2+16} {y2-12} L{x2} {y2} L{x2+16} {y2+12}" class="line" stroke="{color}" stroke-width="{width}"/>'''


def heating_transfer() -> str:
    ambient = "".join(
        arrow(90, 285 + offset, 225, 345 + offset // 3, TEAL, 5)
        for offset in (0, 55, 110)
    )
    warm_air = "".join(
        arrow(920 + offset, 365, 1050 + offset, 450, AMBER, 5)
        for offset in (0, 22, 44)
    )
    body = f'''<rect x="45" y="150" width="320" height="500" rx="32" fill="url(#panel)" stroke="{MIST}" stroke-width="3"/>
      <rect x="440" y="150" width="320" height="500" rx="32" fill="url(#panel)" stroke="{TEAL}" stroke-width="4"/>
      <rect x="835" y="150" width="320" height="500" rx="32" fill="url(#panel)" stroke="{AMBER}" stroke-width="4"/>
      <text x="205" y="205" text-anchor="middle" class="label">Улица</text>
      <text x="600" y="205" text-anchor="middle" class="label">Тепловой насос</text>
      <text x="995" y="205" text-anchor="middle" class="label">Комната</text>
      {ambient}{outdoor_unit(235, 315, 105)}
      {multiline(205, 560, ["Тепло есть даже", "в холодном воздухе"])}
      <path d="M500 390 H700" class="line" stroke="{DEEP}" stroke-width="9"/>
      <path d="M520 365 H680" class="line" stroke="{TEAL}" stroke-width="9"/>
      <circle cx="600" cy="377" r="54" fill="{ICE}" stroke="{TEAL}" stroke-width="5"/>
      <path d="M577 378 q23-35 46 0 q-23 35-46 0" fill="none" stroke="{DEEP}" stroke-width="6"/>
      <path d="M566 340 l-25-24 M634 414 l25 24" stroke="{AMBER}" stroke-width="6" stroke-linecap="round"/>
      {multiline(600, 560, ["Электричество", "двигает тепло"])}
      {indoor_unit(905, 295, 180)}{warm_air}
      {multiline(995, 560, ["Внутренний блок", "отдаёт тепло"])}
      {arrow(375, 390, 425, 390, DEEP, 5)}{arrow(770, 390, 820, 390, DEEP, 5)}'''
    return shell(
        "Кондиционер переносит тепло, а не создаёт его спиралью",
        body,
        "Электричество питает компрессор и вентиляторы",
    )


def multisplit_routes() -> str:
    unit_y = (235, 390, 545)
    route_colors = (TEAL, DEEP, "#4B9FA2")
    routes = []
    units = []
    for index, (y, color) in enumerate(zip(unit_y, route_colors), start=1):
        units.append(indoor_unit(895, y, 175))
        routes.append(
            f'<path d="M300 {350 + (index - 2) * 24} H{420 + index * 70} V{y + 28} H880" class="line" stroke="{color}" stroke-width="7"/>'
        )
        routes.append(f'<circle cx="300" cy="{350 + (index - 2) * 24}" r="7" fill="{color}"/>')
    body = f'''<rect x="45" y="150" width="350" height="500" rx="32" fill="url(#panel)" stroke="{TEAL}" stroke-width="4"/>
      <rect x="455" y="150" width="700" height="500" rx="32" fill="url(#panel)" stroke="{MIST}" stroke-width="3"/>
      <text x="220" y="205" text-anchor="middle" class="label">Один наружный блок</text>
      <text x="805" y="205" text-anchor="middle" class="label">Три отдельные трассы</text>
      {outdoor_unit(155, 300, 135)}
      {''.join(routes)}{''.join(units)}
      <path d="M470 300 H1130 M470 455 H1130" stroke="{MIST}" stroke-width="3" stroke-dasharray="10 10"/>
      {multiline(220, 555, ["У каждого порта", "своё подключение"])}
      <text x="610" y="245" class="small">Комната 1</text>
      <text x="610" y="400" class="small">Комната 2</text>
      <text x="610" y="555" class="small">Комната 3</text>
      <text x="805" y="625" text-anchor="middle" class="note">Длину и перепад высот считают для каждой трассы</text>'''
    return shell(
        "Как внутренние блоки подключаются к мультисплиту",
        body,
        "Общий наружный блок не означает одну общую трубу внутри квартиры",
    )


def filter_air_path() -> str:
    intake = "".join(arrow(250 + offset, 185, 250 + offset, 280, TEAL, 5) for offset in (0, 38, 76))
    outlet = "".join(arrow(750 + offset, 500, 900 + offset, 610, TEAL, 5) for offset in (0, 28, 56))
    body = f'''<rect x="80" y="150" width="1040" height="500" rx="38" fill="url(#panel)" stroke="{MIST}" stroke-width="3"/>
      {intake}
      <rect x="210" y="285" width="160" height="245" rx="18" fill="none" stroke="{DEEP}" stroke-width="6" stroke-dasharray="10 8"/>
      <path d="M435 285 l125 0 l-28 245 l-125 0 z" fill="{ICE}" stroke="{TEAL}" stroke-width="6"/>
      <circle cx="690" cy="410" r="94" fill="none" stroke="{DEEP}" stroke-width="8"/>
      <circle cx="690" cy="410" r="16" fill="{DEEP}"/>
      <path d="M690 328 q70 30 0 82 q-70 30 0 82 q70-30 0-82 q-70-30 0-82" fill="none" stroke="{DEEP}" stroke-width="7"/>
      {outlet}
      <text x="290" y="580" text-anchor="middle" class="small">1. Сетка</text>
      <text x="485" y="580" text-anchor="middle" class="small">2. Теплообменник</text>
      <text x="690" y="580" text-anchor="middle" class="small">3. Вентилятор</text>
      <text x="950" y="580" text-anchor="middle" class="small">4. Выход воздуха</text>
      <path d="M370 405 H395 M560 405 H580 M790 405 H900" class="line" stroke="{TEAL}" stroke-width="7"/>
      {arrow(370, 405, 395, 405, TEAL, 5)}{arrow(560, 405, 580, 405, TEAL, 5)}'''
    return shell(
        "Что проходит воздух внутри кондиционера",
        body,
        "Чистая сетка защищает теплообменник и сохраняет нормальный поток",
    )


def series_for_tasks() -> str:
    cards = [
        (55, "Тихая серия", ["Спальня", "низкий шум"], TEAL, "moon"),
        (425, "Зимняя серия", ["Обогрев", "в мороз"], AMBER, "snow"),
        (795, "Коммерческая", ["Офис", "долгая работа"], DEEP, "office"),
    ]
    parts = []
    for x, title, notes, color, icon in cards:
        if icon == "moon":
            mark = f'<path d="M{x+155} 365 q55 35 5 85 q-65-5-45-65 q8-17 40-20" fill="{ICE}" stroke="{color}" stroke-width="6"/>'
        elif icon == "snow":
            mark = f'<path d="M{x+160} 360 v95 M{x+118} 384 l84 47 M{x+202} 384 l-84 47" stroke="{color}" stroke-width="7" stroke-linecap="round"/>'
        else:
            mark = f'<rect x="{x+105}" y="355" width="110" height="100" rx="8" fill="{ICE}" stroke="{color}" stroke-width="6"/><path d="M{x+130} 385 h18 M{x+172} 385 h18 M{x+130} 420 h18 M{x+172} 420 h18" stroke="{color}" stroke-width="7"/>'
        parts.append(f'''<rect x="{x}" y="150" width="320" height="510" rx="32" fill="url(#panel)" stroke="{color}" stroke-width="4"/>
          <text x="{x+160}" y="205" text-anchor="middle" class="label">{title}</text>
          {indoor_unit(x+75, 255, 170)}{mark}
          {multiline(x+160, 550, notes)}''')
    return shell(
        "У одного бренда серии решают разные задачи",
        "".join(parts),
        "Сравнивают конструкцию и режим работы, а не только наклейку на корпусе",
    )


def btu_heat_gains() -> str:
    factors = [
        (90, 225, "Окна и солнце", AMBER, "sun"),
        (90, 485, "Люди", TEAL, "people"),
        (850, 225, "Техника", DEEP, "tech"),
        (850, 485, "Кухня", CORAL, "heat"),
    ]
    parts = []
    for x, y, label, color, icon in factors:
        parts.append(f'<rect x="{x}" y="{y}" width="260" height="150" rx="26" fill="url(#panel)" stroke="{color}" stroke-width="4"/>')
        parts.append(f'<text x="{x+130}" y="{y+52}" text-anchor="middle" class="label">{label}</text>')
        if icon == "sun":
            parts.append(f'<circle cx="{x+130}" cy="{y+103}" r="25" fill="none" stroke="{color}" stroke-width="6"/><path d="M{x+130} {y+68} v-15 M{x+95} {y+103} h-15 M{x+165} {y+103} h15" stroke="{color}" stroke-width="5"/>')
        elif icon == "people":
            parts.append(f'<circle cx="{x+110}" cy="{y+92}" r="16" fill="{color}"/><circle cx="{x+155}" cy="{y+92}" r="16" fill="{color}"/><path d="M{x+85} {y+135} q25-38 50 0 M{x+130} {y+135} q25-38 50 0" fill="none" stroke="{color}" stroke-width="6"/>')
        elif icon == "tech":
            parts.append(f'<rect x="{x+82}" y="{y+78}" width="96" height="58" rx="8" fill="none" stroke="{color}" stroke-width="6"/><path d="M{x+110} {y+140} h40" stroke="{color}" stroke-width="6"/>')
        else:
            parts.append(f'<path d="M{x+100} {y+135} q-20-30 5-55 q5 30 25 15 q25 24 5 50 M{x+160} {y+135} q-20-30 5-55 q5 30 25 15 q25 24 5 50" fill="none" stroke="{color}" stroke-width="6"/>')
    connectors = (
        arrow(365, 300, 465, 340, AMBER, 5)
        + arrow(365, 555, 465, 485, TEAL, 5)
        + arrow_left(835, 300, 735, 340, DEEP, 5)
        + arrow_left(835, 555, 735, 485, CORAL, 5)
    )
    center = f'''<rect x="475" y="245" width="250" height="340" rx="34" fill="{ICE}" stroke="{TEAL}" stroke-width="6"/>
      <text x="600" y="315" text-anchor="middle" class="label">Расчёт мощности</text>
      <rect x="525" y="355" width="150" height="100" rx="14" fill="#FFFFFF" stroke="{MIST}" stroke-width="4"/>
      <text x="600" y="415" text-anchor="middle" class="title">м²</text>
      {multiline(600, 505, ["Площадь + все", "дополнительные притоки"])}'''
    return shell(
        "Площадь — только начало расчёта",
        "".join(parts) + connectors + center,
        "Солнце, люди, техника и кухня добавляют реальную тепловую нагрузку",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "heating-energy-transfer.svg": heating_transfer(),
        "multisplit-route-topology.svg": multisplit_routes(),
        "filter-air-path.svg": filter_air_path(),
        "brand-series-for-tasks.svg": series_for_tasks(),
        "btu-heat-gains.svg": btu_heat_gains(),
    }
    for name, content in files.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
