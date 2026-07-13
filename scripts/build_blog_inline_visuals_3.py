#!/usr/bin/env python3
"""Build the third deterministic MVN Climate Atlas inline-diagram set."""

from build_blog_inline_visuals import (
    AMBER,
    CORAL,
    DEEP,
    GRAPHITE,
    ICE,
    MIST,
    OUT,
    TEAL,
    indoor_unit,
    shell,
)


def inverter_temperature() -> str:
    grid = "".join(
        f'<path d="M120 {y} H1080" stroke="{MIST}" stroke-width="2" stroke-dasharray="8 10"/>'
        for y in (260, 350, 440, 530)
    )
    body = f'''<rect x="75" y="145" width="1050" height="500" rx="34" fill="url(#panel)" stroke="{MIST}" stroke-width="3"/>
      {grid}
      <path d="M120 570 V210 M120 570 H1080" stroke="{GRAPHITE}" stroke-width="4" stroke-linecap="round"/>
      <path d="M120 395 H1080" stroke="{DEEP}" stroke-width="4" stroke-dasharray="14 12" opacity=".55"/>
      <text x="135" y="380" class="small">Заданная температура</text>
      <path d="M150 245 C210 245 220 530 300 530 S390 260 470 260 S560 520 640 520 S730 275 810 275 S900 505 980 505 S1040 300 1070 300" fill="none" stroke="{CORAL}" stroke-width="8" stroke-linecap="round"/>
      <path d="M150 245 C260 250 285 390 390 405 C520 423 610 390 730 397 C850 403 930 394 1070 396" fill="none" stroke="{TEAL}" stroke-width="8" stroke-linecap="round"/>
      <circle cx="290" cy="610" r="7" fill="{CORAL}"/><text x="310" y="617" class="note">On/Off: заметные циклы включения и остановки</text>
      <circle cx="725" cy="610" r="7" fill="{TEAL}"/><text x="745" y="617" class="note">Инвертор: плавное удержание</text>
      <text x="1060" y="555" text-anchor="end" class="small">Время →</text>'''
    return shell(
        "Как меняется температура после выхода на режим",
        body,
        "Инвертор снижает мощность, а On/Off продолжает работать циклами",
    )


def installation_connection_node() -> str:
    unit = indoor_unit(720, 225, 310)
    body = f'''<rect x="70" y="145" width="1060" height="520" rx="34" fill="url(#panel)" stroke="{MIST}" stroke-width="3"/>
      <path d="M100 185 H1100" stroke="{GRAPHITE}" stroke-width="5"/>
      <text x="105" y="175" class="small">Потолок</text>
      <path d="M1045 185 V225 M1032 185 H1058 M1032 225 H1058" stroke="{DEEP}" stroke-width="4"/>
      <text x="1070" y="211" class="small">10–15 см</text>
      {unit}
      <circle cx="720" cy="315" r="12" fill="{TEAL}" stroke="#FFFFFF" stroke-width="4"/>
      <text x="740" y="355" class="small">Нижний левый ввод блока</text>
      <path d="M235 610 V300 H720" fill="none" stroke="{MIST}" stroke-width="58" stroke-linejoin="round" opacity=".45"/>
      <path d="M220 610 V292 H720" fill="none" stroke="{DEEP}" stroke-width="9" stroke-linejoin="round"/>
      <path d="M245 610 V315 H720" fill="none" stroke="{TEAL}" stroke-width="9" stroke-linejoin="round"/>
      <path d="M270 610 V338 L720 315" fill="none" stroke="{AMBER}" stroke-width="8" stroke-linejoin="round"/>
      <path d="M290 610 V355 L720 330" fill="none" stroke="{GRAPHITE}" stroke-width="5" stroke-linejoin="round" stroke-dasharray="14 10"/>
      <path d="M500 326 l18-12 M500 326 l19 10" stroke="{AMBER}" stroke-width="5" stroke-linecap="round"/>
      <text x="325" y="275" class="small">Поворот трассы на 90° к блоку</text>
      <text x="305" y="390" class="small">Дренаж идёт от блока с уклоном</text>
      <circle cx="420" cy="500" r="7" fill="{DEEP}"/><text x="440" y="507" class="note">медные трубы</text>
      <circle cx="420" cy="540" r="7" fill="{AMBER}"/><text x="440" y="547" class="note">дренаж: поток от блока</text>
      <circle cx="420" cy="580" r="7" fill="{GRAPHITE}"/><text x="440" y="587" class="note">кабель</text>'''
    return shell(
        "Как трасса подходит к внутреннему блоку",
        body,
        "Точка выхода привязана к корпусу, а дренажу нужен постоянный уклон",
    )


def bedroom_placement() -> str:
    good_air = "".join(
        f'<path d="M245 {320+offset} C420 {280+offset} 565 {285+offset} 700 {330+offset}" fill="none" stroke="{TEAL}" stroke-width="7" stroke-linecap="round"/>'
        for offset in (0, 22, 44)
    )
    bad_air = "".join(
        f'<path d="M865 {235+offset} C850 {300+offset} 850 {355+offset} 845 {420+offset}" fill="none" stroke="{CORAL}" stroke-width="7" stroke-linecap="round"/>'
        for offset in (0, 22, 44)
    )
    body = f'''<rect x="90" y="145" width="1020" height="520" rx="32" fill="url(#panel)" stroke="{MIST}" stroke-width="5"/>
      <rect x="735" y="390" width="275" height="225" rx="18" fill="#F2ECE3" stroke="{MIST}" stroke-width="4"/>
      <rect x="755" y="415" width="110" height="58" rx="16" fill="#FFFFFF" stroke="{MIST}" stroke-width="3"/>
      <rect x="880" y="415" width="110" height="58" rx="16" fill="#FFFFFF" stroke="{MIST}" stroke-width="3"/>
      <path d="M735 485 H1010" stroke="{MIST}" stroke-width="3"/>
      <text x="872" y="585" text-anchor="middle" class="label">Кровать</text>
      <g transform="translate(165 275) rotate(-90)">{indoor_unit(0, 0, 175)}</g>
      <text x="175" y="515" text-anchor="middle" class="small" fill="{TEAL}">Лучше: поток вдоль комнаты</text>
      {good_air}
      {indoor_unit(790, 165, 185, "#F6E0DC")}
      <path d="M815 185 l135 62 M950 185 l-135 62" stroke="{CORAL}" stroke-width="8" stroke-linecap="round" opacity=".85"/>
      {bad_air}
      <circle cx="810" cy="445" r="18" fill="{CORAL}" opacity=".75"/>
      <text x="920" y="335" text-anchor="middle" class="small" fill="{CORAL}">Плохо: поток направлен к подушке</text>'''
    return shell(
        "Размещение проверяют относительно человека",
        body,
        "Свободная стена не подходит, если поток попадает прямо в зону сна",
    )


def industrial_types() -> str:
    cards = [
        (45, "Канальный", "Скрытый потолок", TEAL, "duct"),
        (330, "Кассетный", "Открытый зал", TEAL, "cassette"),
        (615, "Напольно-", "Вытянутое помещение", AMBER, "floor"),
        (900, "Колонный", "Большой объём", DEEP, "column"),
    ]
    parts = []
    for x, title, note, color, kind in cards:
        if kind == "duct":
            icon = f'<rect x="{x+62}" y="315" width="135" height="72" rx="12" fill="{ICE}" stroke="{color}" stroke-width="6"/><path d="M{x+197} 338 h42 v-45 h36 M{x+197} 365 h42 v45 h36" fill="none" stroke="{color}" stroke-width="6"/>'
        elif kind == "cassette":
            icon = f'<rect x="{x+75}" y="300" width="120" height="120" rx="16" fill="{ICE}" stroke="{color}" stroke-width="6"/><circle cx="{x+135}" cy="360" r="30" fill="none" stroke="{color}" stroke-width="6"/><path d="M{x+135} 285 v-35 M{x+135} 435 v35 M{x+60} 360 h-35 M{x+210} 360 h35" stroke="{color}" stroke-width="6"/>'
        elif kind == "floor":
            icon = f'<rect x="{x+75}" y="330" width="145" height="75" rx="18" fill="#FFFFFF" stroke="{color}" stroke-width="6"/><path d="M{x+105} 315 q45-55 90 0" fill="none" stroke="{color}" stroke-width="7"/>'
        else:
            icon = f'<rect x="{x+100}" y="280" width="90" height="180" rx="18" fill="#FFFFFF" stroke="{color}" stroke-width="6"/><path d="M{x+118} 315 h54 M{x+118} 340 h54" stroke="{GRAPHITE}" stroke-width="6"/><path d="M{x+120} 270 q25-45 50 0" fill="none" stroke="{color}" stroke-width="7"/>'
        parts.append(f'''<rect x="{x}" y="150" width="255" height="510" rx="30" fill="url(#panel)" stroke="{color}" stroke-width="4"/>
          <text x="{x+127}" y="205" text-anchor="middle" class="label">{title}</text>
          {icon}<text x="{x+127}" y="555" text-anchor="middle" class="note">{note}</text>''')
    parts.append('<text x="742" y="235" text-anchor="middle" class="label">потолочный</text>')
    return shell(
        "Тип внутреннего блока выбирают по помещению",
        "".join(parts),
        "Монтажные ограничения и направление воздуха важнее привычной формы корпуса",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "inverter-temperature-curve.svg": inverter_temperature(),
        "installation-connection-node.svg": installation_connection_node(),
        "bedroom-placement-map.svg": bedroom_placement(),
        "industrial-unit-types.svg": industrial_types(),
    }
    for name, content in files.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
