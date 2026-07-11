#!/usr/bin/env python3
"""Build deterministic MVN Climate Atlas diagrams for long service pages."""

from build_blog_inline_visuals import AMBER, CORAL, DEEP, GRAPHITE, ICE, MIST, OUT, TEAL, indoor_unit, outdoor_unit, shell


def vrf_architecture() -> str:
    floors = "".join(f'<path d="M420 {y} H1120" stroke="{MIST}" stroke-width="3" stroke-dasharray="10 10"/>' for y in (300, 455))
    units = "".join(indoor_unit(x, y, 135) for x, y in ((610, 220), (890, 220), (610, 375), (890, 375), (610, 530), (890, 530)))
    branches = "".join(
        f'<path d="M385 400 H{500 + index*22} V{y+22} H{x-15}" fill="none" stroke="{TEAL if index % 2 == 0 else DEEP}" stroke-width="6" stroke-linejoin="round"/>'
        for index, (x, y) in enumerate(((610, 220), (890, 220), (610, 375), (890, 375), (610, 530), (890, 530)))
    )
    body = f'''<rect x="55" y="150" width="330" height="500" rx="32" fill="url(#panel)" stroke="{TEAL}" stroke-width="4"/>
      <rect x="420" y="150" width="725" height="500" rx="32" fill="url(#panel)" stroke="{MIST}" stroke-width="3"/>
      <text x="220" y="205" text-anchor="middle" class="label">Наружный модуль</text>
      <text x="780" y="205" text-anchor="middle" class="label">Зоны здания</text>
      {outdoor_unit(145, 285, 150)}{floors}{branches}{units}
      <rect x="105" y="500" width="230" height="72" rx="18" fill="{ICE}" stroke="{DEEP}" stroke-width="4"/>
      <text x="220" y="545" text-anchor="middle" class="small">Центральное управление</text>
      <path d="M335 536 H395 V580 H570" fill="none" stroke="{AMBER}" stroke-width="5" stroke-dasharray="12 10"/>
      <text x="780" y="625" text-anchor="middle" class="note">Длинные трассы, перепады высот и независимое управление зонами</text>'''
    return shell("Архитектура VRF для многозонального объекта", body, "Одна проектная система связывает много внутренних блоков и управление")


def server_reserve() -> str:
    rack = f'''<rect x="500" y="240" width="200" height="330" rx="22" fill="{ICE}" stroke="{DEEP}" stroke-width="7"/>
      <path d="M535 300 H665 M535 355 H665 M535 410 H665 M535 465 H665" stroke="{DEEP}" stroke-width="6"/>
      <circle cx="650" cy="300" r="7" fill="{TEAL}"/><circle cx="650" cy="355" r="7" fill="{TEAL}"/><circle cx="650" cy="410" r="7" fill="{TEAL}"/>'''
    body = f'''<rect x="55" y="150" width="1090" height="500" rx="34" fill="url(#panel)" stroke="{MIST}" stroke-width="3"/>
      {indoor_unit(125, 245, 200)}{indoor_unit(875, 245, 200)}{rack}
      <text x="225" y="220" text-anchor="middle" class="label">Основной</text>
      <text x="975" y="220" text-anchor="middle" class="label">Резервный</text>
      <text x="600" y="610" text-anchor="middle" class="label">Серверная стойка</text>
      <path d="M330 315 C410 330 420 390 485 405" fill="none" stroke="{TEAL}" stroke-width="8" stroke-linecap="round"/>
      <path d="M870 315 C790 330 780 390 715 405" fill="none" stroke="{AMBER}" stroke-width="8" stroke-linecap="round" stroke-dasharray="15 12"/>
      <circle cx="600" cy="185" r="42" fill="{ICE}" stroke="{TEAL}" stroke-width="5"/>
      <text x="600" y="195" text-anchor="middle" class="label">°C</text>
      <path d="M600 227 V240 M558 185 H370 V280 M642 185 H830 V280" fill="none" stroke="{DEEP}" stroke-width="5"/>
      <rect x="470" y="455" width="260" height="75" rx="18" fill="#FFFFFF" stroke="{CORAL}" stroke-width="4"/>
      <text x="600" y="485" text-anchor="middle" class="small">Контроллер: ротация</text>
      <text x="600" y="510" text-anchor="middle" class="small">и аварийное включение</text>'''
    return shell("Охлаждение серверной строят с резервом", body, "Независимый датчик контролирует температуру и переключает блоки")


def maintenance_zones() -> str:
    body = f'''<rect x="70" y="150" width="1060" height="500" rx="34" fill="url(#panel)" stroke="{MIST}" stroke-width="3"/>
      <rect x="125" y="245" width="150" height="235" rx="18" fill="none" stroke="{DEEP}" stroke-width="6" stroke-dasharray="10 8"/>
      <path d="M340 245 l150 0 l-30 235 l-150 0 z" fill="{ICE}" stroke="{TEAL}" stroke-width="6"/>
      <circle cx="620" cy="360" r="90" fill="none" stroke="{DEEP}" stroke-width="8"/><circle cx="620" cy="360" r="15" fill="{DEEP}"/>
      <path d="M620 285 q65 28 0 75 q-65 28 0 75 q65-28 0-75 q-65-28 0-75" fill="none" stroke="{DEEP}" stroke-width="7"/>
      <path d="M770 430 H1015 L985 485 H800 z" fill="{ICE}" stroke="{AMBER}" stroke-width="6"/>
      <path d="M985 485 q20 35 45 55" fill="none" stroke="{TEAL}" stroke-width="7" stroke-linecap="round"/>
      <text x="200" y="550" text-anchor="middle" class="label">Фильтры</text>
      <text x="400" y="550" text-anchor="middle" class="label">Теплообменник</text>
      <text x="620" y="550" text-anchor="middle" class="label">Крыльчатка</text>
      <text x="900" y="550" text-anchor="middle" class="label">Поддон и дренаж</text>
      <path d="M275 360 H300 M490 360 H515 M710 360 H765" stroke="{TEAL}" stroke-width="6" stroke-linecap="round"/>
      <circle cx="200" cy="220" r="10" fill="{CORAL}"/><circle cx="400" cy="220" r="10" fill="{CORAL}"/><circle cx="620" cy="220" r="10" fill="{CORAL}"/><circle cx="900" cy="220" r="10" fill="{CORAL}"/>
      <text x="600" y="615" text-anchor="middle" class="note">Запах и слабый поток часто остаются, если очистить только сетку</text>'''
    return shell("Какие зоны очищают при полноценном обслуживании", body, "Чистка внутреннего блока — это не только промывка фильтров")


def dismantling_sequence() -> str:
    steps = [
        (55, "1. Осмотр", "Доступ и состояние", MIST),
        (335, "2. Хладагент", "Сохраняют в контуре", TEAL),
        (615, "3. Соединения", "Отключают и закрывают", AMBER),
        (895, "4. Блоки", "Снимают и упаковывают", DEEP),
    ]
    parts = []
    for index, (x, title, note, color) in enumerate(steps):
        icon = f'<circle cx="{x+110}" cy="360" r="58" fill="{ICE}" stroke="{color}" stroke-width="6"/><text x="{x+110}" y="374" text-anchor="middle" class="label">{index+1}</text>'
        parts.append(f'''<rect x="{x}" y="155" width="220" height="490" rx="30" fill="url(#panel)" stroke="{color}" stroke-width="4"/>
          <text x="{x+110}" y="215" text-anchor="middle" class="label">{title}</text>{icon}
          <text x="{x+110}" y="525" text-anchor="middle" class="note">{note}</text>''')
        if index < 3:
            parts.append(f'<path d="M{x+230} 400 H{x+265}" stroke="{GRAPHITE}" stroke-width="5"/><path d="M{x+250} 388 L{x+265} 400 L{x+250} 412" fill="none" stroke="{GRAPHITE}" stroke-width="5"/>')
    return shell("Безопасный демонтаж — это последовательность", "".join(parts), "Цель — сохранить оборудование и подготовить его к перевозке или повторному монтажу")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in {
        "vrf-system-architecture.svg": vrf_architecture(),
        "server-redundancy-monitoring.svg": server_reserve(),
        "maintenance-cleaning-zones.svg": maintenance_zones(),
        "dismantling-safe-sequence.svg": dismantling_sequence(),
    }.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
