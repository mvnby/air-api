#!/usr/bin/env python3
"""Build deterministic MVN Climate Atlas inline diagrams for long blog articles."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "img" / "blog" / "v2" / "inline"

TEAL = "#11B8B2"
DEEP = "#075E63"
ICE = "#EAF7F6"
WARM = "#F7F5F0"
GRAPHITE = "#24343A"
MIST = "#C9D5D5"
AMBER = "#F2A93B"
CORAL = "#E56A5D"


def shell(title: str, body: str, subtitle: str = "") -> str:
    subtitle_markup = (
        f'<text x="600" y="96" text-anchor="middle" class="subtitle">{subtitle}</text>'
        if subtitle
        else ""
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760" role="img" aria-labelledby="title desc">
  <title id="title">{title}</title>
  <desc id="desc">{subtitle or title}</desc>
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#24343A" flood-opacity=".10"/></filter>
    <linearGradient id="panel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EAF7F6"/></linearGradient>
    <style>
      .title{{font:700 34px Inter,Arial,sans-serif;fill:{GRAPHITE}}}
      .subtitle{{font:400 20px Inter,Arial,sans-serif;fill:#607277}}
      .label{{font:700 25px Inter,Arial,sans-serif;fill:{GRAPHITE}}}
      .note{{font:500 18px Inter,Arial,sans-serif;fill:#607277}}
      .small{{font:600 16px Inter,Arial,sans-serif;fill:{GRAPHITE}}}
      .line{{fill:none;stroke-linecap:round;stroke-linejoin:round}}
    </style>
  </defs>
  <rect width="1200" height="760" rx="40" fill="{WARM}"/>
  <text x="600" y="58" text-anchor="middle" class="title">{title}</text>
  {subtitle_markup}
  {body}
</svg>'''


def indoor_unit(x: int, y: int, width: int = 180, color: str = "#FFFFFF") -> str:
    height = round(width * .34)
    return f'''<g filter="url(#shadow)">
      <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="22" fill="{color}" stroke="{MIST}" stroke-width="3"/>
      <path d="M{x+18} {y+height-15} H{x+width-18}" stroke="{GRAPHITE}" stroke-width="7" stroke-linecap="round"/>
    </g>'''


def outdoor_unit(x: int, y: int, size: int = 125, muted: bool = False) -> str:
    opacity = ".45" if muted else "1"
    return f'''<g opacity="{opacity}" filter="url(#shadow)">
      <rect x="{x}" y="{y}" width="{size}" height="{size}" rx="18" fill="#F2F4F3" stroke="{MIST}" stroke-width="3"/>
      <circle cx="{x+size/2}" cy="{y+size/2}" r="{size*.31}" fill="none" stroke="{DEEP}" stroke-width="7"/>
      <circle cx="{x+size/2}" cy="{y+size/2}" r="8" fill="{DEEP}"/>
      <path d="M{x+size/2} {y+size*.23} Q{x+size*.72} {y+size*.42} {x+size/2} {y+size/2} Q{x+size*.28} {y+size*.58} {x+size/2} {y+size*.77}" fill="none" stroke="{DEEP}" stroke-width="5"/>
    </g>'''


def arrow(x1: int, y1: int, x2: int, y2: int, color: str = TEAL, width: int = 7, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="15 13"' if dashed else ""
    return f'''<path d="M{x1} {y1} L{x2} {y2}" class="line" stroke="{color}" stroke-width="{width}"{dash}/>
      <path d="M{x2-16} {y2-12} L{x2} {y2} L{x2-16} {y2+12}" class="line" stroke="{color}" stroke-width="{width}"/>'''


def defrost_cycle() -> str:
    cards = []
    data = [
        (55, "1. Обогрев", TEAL, "Наружный блок забирает тепло", False),
        (425, "2. Иней", AMBER, "Теплообменник постепенно обмерзает", False),
        (795, "3. Оттайка", CORAL, "Система временно растапливает лёд", True),
    ]
    for x, label, color, note, muted in data:
        drops = "" if not muted else f'''<path d="M{x+170} 460 q-14 22 0 34 q14-12 0-34 M{x+215} 470 q-12 19 0 30 q12-11 0-30" fill="{TEAL}" opacity=".7"/>'''
        frost = "" if label != "2. Иней" else "".join(
            f'<circle cx="{x+120+i*34}" cy="{410+(i%2)*24}" r="8" fill="{ICE}" stroke="{DEEP}" stroke-width="3"/>'
            for i in range(5)
        )
        cards.append(f'''<g>
          <rect x="{x}" y="145" width="320" height="500" rx="32" fill="url(#panel)" stroke="{color}" stroke-width="4" filter="url(#shadow)"/>
          <text x="{x+160}" y="200" text-anchor="middle" class="label">{label}</text>
          {outdoor_unit(x+98, 270, 125, muted)}
          {frost}{drops}
          <text x="{x+160}" y="560" text-anchor="middle" class="note"><tspan x="{x+160}" dy="0">{note.split(' ', 3)[0]} {note.split(' ', 3)[1]}</tspan><tspan x="{x+160}" dy="28">{' '.join(note.split(' ', 3)[2:])}</tspan></text>
        </g>''')
    body = "".join(cards) + arrow(365, 390, 410, 390, DEEP, 5) + arrow(735, 390, 780, 390, DEEP, 5)
    return shell("Как проходит оттайка наружного блока", body, "Короткая пауза в подаче тепла — нормальная часть зимней работы")


def multisplit_failure() -> str:
    left_units = "".join(indoor_unit(305, 230 + index * 135, 160, "#F6E0DC") for index in range(3))
    left_lines = "".join(f'<path d="M240 405 H270 V{255+index*135} H305" class="line" stroke="{CORAL}" stroke-width="6"/>' for index in range(3))
    right_rows = []
    for index in range(3):
        y = 230 + index * 135
        failed = index == 1
        color = CORAL if failed else TEAL
        right_rows.append(outdoor_unit(705, y-18, 95, failed) + indoor_unit(920, y, 160, "#F6E0DC" if failed else "#FFFFFF") + arrow(805, y+30, 910, y+30, color, 5))
        if failed:
            right_rows.append(f'<path d="M730 {y+8} l50 50 M780 {y+8} l-50 50" stroke="{CORAL}" stroke-width="9" stroke-linecap="round"/>')
    body = f'''<rect x="55" y="145" width="510" height="520" rx="32" fill="url(#panel)" stroke="{CORAL}" stroke-width="4"/>
      <rect x="635" y="145" width="510" height="520" rx="32" fill="url(#panel)" stroke="{TEAL}" stroke-width="4"/>
      <text x="310" y="195" text-anchor="middle" class="label">Мультисплит</text>
      <text x="890" y="195" text-anchor="middle" class="label">Отдельные сплиты</text>
      {outdoor_unit(115, 340, 125, True)}{left_units}{left_lines}
      <path d="M140 365 l75 75 M215 365 l-75 75" stroke="{CORAL}" stroke-width="12" stroke-linecap="round"/>
      <text x="310" y="620" text-anchor="middle" class="note">Остановятся все комнаты</text>
      {''.join(right_rows)}
      <text x="890" y="620" text-anchor="middle" class="note">Остальные комнаты работают</text>'''
    return shell("Что происходит при одной неисправности", body, "Общая точка отказа — главный эксплуатационный риск мультисплита")


def filter_care() -> str:
    steps = [
        (70, "1. Снять", "Открыть крышку и вынуть сетку"),
        (350, "2. Промыть", "Прохладная вода без жёсткой щётки"),
        (630, "3. Высушить", "Без фена и прямого солнца"),
        (910, "4. Вернуть", "Только полностью сухой фильтр"),
    ]
    cards = []
    for index, (x, label, note) in enumerate(steps):
        if index == 0:
            icon = indoor_unit(x+35, 285, 150) + f'<rect x="{x+65}" y="390" width="90" height="120" rx="10" fill="none" stroke="{DEEP}" stroke-width="5" stroke-dasharray="8 6"/>'
        elif index == 1:
            icon = f'<rect x="{x+70}" y="300" width="90" height="130" rx="10" fill="none" stroke="{DEEP}" stroke-width="5"/><path d="M{x+65} 270 q15 25 0 45 q-15-20 0-45 M{x+125} 260 q15 25 0 45 q-15-20 0-45 M{x+185} 275 q15 25 0 45 q-15-20 0-45" fill="{TEAL}"/>'
        elif index == 2:
            icon = f'<rect x="{x+70}" y="320" width="90" height="130" rx="10" fill="none" stroke="{DEEP}" stroke-width="5"/><circle cx="{x+115}" cy="280" r="27" fill="none" stroke="{AMBER}" stroke-width="5"/><path d="M{x+115} 235 v-18 M{x+115} 343 v-18 M{x+70} 280 h-18 M{x+178} 280 h-18" stroke="{AMBER}" stroke-width="5"/>'
        else:
            icon = indoor_unit(x+35, 320, 150) + f'<path d="M{x+110} 510 V455" stroke="{TEAL}" stroke-width="7"/><path d="M{x+94} 472 l16-17 l16 17" fill="none" stroke="{TEAL}" stroke-width="7"/>'
        cards.append(f'''<g><rect x="{x}" y="160" width="220" height="500" rx="28" fill="url(#panel)" stroke="{MIST}" stroke-width="3"/>
          <text x="{x+110}" y="215" text-anchor="middle" class="label">{label}</text>{icon}
          <text x="{x+110}" y="570" text-anchor="middle" class="note"><tspan x="{x+110}" dy="0">{note.split(' ', 3)[0]} {note.split(' ', 3)[1]}</tspan><tspan x="{x+110}" dy="27">{' '.join(note.split(' ', 3)[2:])}</tspan></text></g>''')
    body = "".join(cards) + arrow(300, 410, 330, 410, DEEP, 4) + arrow(580, 410, 610, 410, DEEP, 4) + arrow(860, 410, 890, 410, DEEP, 4)
    return shell("Как ухаживать за сетчатым фильтром", body, "Регулярная простая чистка важнее количества рекламных вставок")


def brand_chain() -> str:
    stages = [
        (65, "Бренд", "Общий уровень и репутация", MIST),
        (345, "Серия", "Конструкция и рабочий диапазон", TEAL),
        (625, "Модель", "Мощность, шум и функции", TEAL),
        (905, "Сервис", "Монтаж, гарантия и запчасти", AMBER),
    ]
    cards = []
    for index, (x, label, note, color) in enumerate(stages):
        icon = (
            f'<circle cx="{x+110}" cy="330" r="52" fill="{ICE}" stroke="{color}" stroke-width="5"/><text x="{x+110}" y="345" text-anchor="middle" class="label">{index+1}</text>'
        )
        cards.append(f'''<rect x="{x}" y="170" width="220" height="440" rx="30" fill="url(#panel)" stroke="{color}" stroke-width="4"/>
          <text x="{x+110}" y="230" text-anchor="middle" class="label">{label}</text>{icon}
          <text x="{x+110}" y="460" text-anchor="middle" class="note"><tspan x="{x+110}" dy="0">{note.split(' ', 3)[0]} {note.split(' ', 3)[1]}</tspan><tspan x="{x+110}" dy="28">{' '.join(note.split(' ', 3)[2:])}</tspan></text>''')
    body = "".join(cards) + arrow(300, 390, 330, 390, DEEP, 4) + arrow(580, 390, 610, 390, DEEP, 4) + arrow(860, 390, 890, 390, DEEP, 4)
    return shell("Выбирают не наклейку, а конкретное решение", body, "Название бренда — только начало проверки")


def btu_sizing() -> str:
    data = [
        (55, "Мощности мало", "Не выходит на режим", CORAL, 125),
        (425, "По расчёту", "Ровно держит температуру", TEAL, 175),
        (795, "Слишком мощный", "Короткие циклы и сквозняк", AMBER, 225),
    ]
    cards = []
    for x, label, note, color, unit_width in data:
        unit_x = round(x + (320 - unit_width) / 2)
        air = "".join(
            arrow(unit_x + 35 + offset, 350, x + 115 + offset, 470, color, 5)
            for offset in (0, 22, 44)
        )
        cards.append(f'''<rect x="{x}" y="150" width="320" height="510" rx="32" fill="url(#panel)" stroke="{color}" stroke-width="4"/>
          <text x="{x+160}" y="205" text-anchor="middle" class="label">{label}</text>
          {indoor_unit(unit_x, 275, unit_width)}{air}
          <rect x="{x+80}" y="500" width="160" height="75" rx="14" fill="{ICE}" stroke="{MIST}" stroke-width="3"/>
          <text x="{x+160}" y="615" text-anchor="middle" class="note">{note}</text>''')
    return shell("Почему нельзя выбирать только «с запасом»", "".join(cards), "Слабая и избыточная модель дают разные, но реальные проблемы")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "obogrev-defrost-cycle.svg": defrost_cycle(),
        "multisplit-common-failure.svg": multisplit_failure(),
        "filters-maintenance-cycle.svg": filter_care(),
        "brand-series-selection-chain.svg": brand_chain(),
        "btu-sizing-balance.svg": btu_sizing(),
    }
    for name, content in files.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
