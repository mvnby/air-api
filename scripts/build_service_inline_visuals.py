#!/usr/bin/env python3
"""Build deterministic MVN Climate Atlas diagrams for long service pages."""

from build_blog_inline_visuals import AMBER, CORAL, DEEP, ICE, MIST, OUT, TEAL, indoor_unit, outdoor_unit, shell


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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in {
        "vrf-system-architecture.svg": vrf_architecture(),
        "server-redundancy-monitoring.svg": server_reserve(),
    }.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
