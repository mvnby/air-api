#!/usr/bin/env python3
"""Build the compact MVN Climate Atlas visual set for the services landing page."""

from pathlib import Path

from build_blog_inline_visuals import (
    AMBER,
    CORAL,
    DEEP,
    GRAPHITE,
    ICE,
    MIST,
    TEAL,
    indoor_unit,
    outdoor_unit,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "img" / "services" / "v2"
WARM = "#F7F5F0"


def canvas(title: str, description: str, body: str, accent: str = TEAL) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760" role="img" aria-labelledby="title desc">
  <title id="title">{title}</title>
  <desc id="desc">{description}</desc>
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="{GRAPHITE}" flood-opacity=".12"/></filter>
    <linearGradient id="surface" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="{ICE}"/></linearGradient>
    <marker id="flow-teal" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M2 1 L10 6 L2 11" fill="none" stroke="{TEAL}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></marker>
    <marker id="flow-amber" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M2 1 L10 6 L2 11" fill="none" stroke="{AMBER}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></marker>
  </defs>
  <rect width="1200" height="760" rx="48" fill="{WARM}"/>
  <rect x="42" y="42" width="1116" height="676" rx="40" fill="url(#surface)" stroke="{MIST}" stroke-width="4"/>
  <path d="M88 132 V88 H132 M1068 672 H1112 V628" fill="none" stroke="{accent}" stroke-width="8" stroke-linecap="round"/>
  <circle cx="1108" cy="92" r="13" fill="{accent}"/>
  {body}
</svg>'''


def airflow(x1: int, y1: int, x2: int, y2: int, color: str = TEAL) -> str:
    marker = "flow-teal" if color == TEAL else "flow-amber"
    return "".join(
        f'<path d="M{x1} {y1+offset} C{(x1+x2)//2} {y1+offset-20} {(x1+x2)//2} {y2+offset+20} {x2} {y2+offset}" fill="none" stroke="{color}" stroke-width="10" stroke-linecap="round" opacity=".82" marker-end="url(#{marker})"/>'
        for offset in (0, 30, 60)
    )


def installation() -> str:
    body = f'''{outdoor_unit(165, 395, 210)}
      {indoor_unit(610, 205, 330)}
      <path d="M375 500 H485 V335 H610" fill="none" stroke="{DEEP}" stroke-width="16" stroke-linejoin="round"/>
      <path d="M375 535 H520 V365 H610" fill="none" stroke="{TEAL}" stroke-width="16" stroke-linejoin="round"/>
      {airflow(760, 345, 1000, 470)}'''
    return canvas("Монтаж кондиционера", "Внутренний и наружный блок соединены аккуратной трассой", body)


def maintenance() -> str:
    ribs = "".join(
        f'<path d="M{x} 426 q-18 48 0 96" fill="none" stroke="{DEEP}" stroke-width="5" opacity=".72"/>'
        for x in range(500, 860, 34)
    )
    body = f'''<rect x="175" y="150" width="850" height="470" rx="46" fill="#FFFFFF" stroke="{MIST}" stroke-width="6" filter="url(#shadow)"/>
      <rect x="230" y="215" width="235" height="200" rx="24" fill="none" stroke="{DEEP}" stroke-width="10" stroke-dasharray="18 14"/>
      <path d="M510 205 H900 L865 380 H485 Z" fill="{ICE}" stroke="{TEAL}" stroke-width="10"/>
      <rect x="455" y="420" width="455" height="108" rx="54" fill="{ICE}" stroke="{DEEP}" stroke-width="11"/>
      {ribs}
      <circle cx="475" cy="474" r="18" fill="#FFFFFF" stroke="{DEEP}" stroke-width="7"/><circle cx="890" cy="474" r="18" fill="#FFFFFF" stroke="{DEEP}" stroke-width="7"/>
      <path d="M225 548 H900 Q935 548 955 530 V575 H270 Q235 575 225 548 Z" fill="{ICE}" stroke="{TEAL}" stroke-width="9" stroke-linejoin="round"/>
      <path d="M945 568 H985 V605" fill="none" stroke="{TEAL}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M585 370 q-20 32 0 55 q20-23 0-55 M750 365 q-20 32 0 55 q20-23 0-55" fill="{TEAL}" opacity=".8"/>'''
    return canvas("Обслуживание кондиционера", "Фильтр, испаритель, тангенциальная крыльчатка и дренажный поддон", body)


def repair() -> str:
    body = f'''{indoor_unit(150, 230, 300)}{outdoor_unit(775, 360, 215, True)}
      <path d="M450 350 C560 280 685 300 785 405" fill="none" stroke="{DEEP}" stroke-width="12"/>
      <path d="M450 375 C575 325 680 340 785 435" fill="none" stroke="{TEAL}" stroke-width="12"/>
      <circle cx="395" cy="335" r="18" fill="{TEAL}" stroke="#FFFFFF" stroke-width="6"/><circle cx="825" cy="420" r="18" fill="{TEAL}" stroke="#FFFFFF" stroke-width="6"/>
      <circle cx="610" cy="305" r="68" fill="{ICE}" stroke="{CORAL}" stroke-width="9" filter="url(#shadow)"/>
      <path d="M580 275 l60 60 M640 275 l-60 60" stroke="{CORAL}" stroke-width="13" stroke-linecap="round"/>
      <path d="M555 500 q55-65 110 0 l72 72 l-38 38 l-72-72 q-65 35-112-12" fill="none" stroke="{DEEP}" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>'''
    return canvas("Ремонт кондиционера", "Диагностика внутреннего блока, трассы и наружного блока", body, CORAL)


def dismantling() -> str:
    body = f'''{indoor_unit(175, 190, 305)}{outdoor_unit(740, 205, 220)}
      <path d="M325 330 V475 M850 435 V505" stroke="{TEAL}" stroke-width="12" stroke-linecap="round"/>
      <path d="M295 445 l30 30 l30-30 M820 475 l30 30 l30-30" fill="none" stroke="{TEAL}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M140 500 h370 l55 68 l-55 82 h-370 l-55-82 z" fill="{ICE}" stroke="{DEEP}" stroke-width="8"/>
      <path d="M690 520 h330 l48 60 l-48 70 h-330 l-48-70 z" fill="{ICE}" stroke="{DEEP}" stroke-width="8"/>
      <path d="M575 350 H628 M672 350 H725" stroke="{AMBER}" stroke-width="12" stroke-linecap="round"/>
      <circle cx="635" cy="350" r="10" fill="#FFFFFF" stroke="{AMBER}" stroke-width="7"/><circle cx="665" cy="350" r="10" fill="#FFFFFF" stroke="{AMBER}" stroke-width="7"/>
      <path d="M610 325 l18 25 l-18 25 M690 325 l-18 25 l18 25" fill="none" stroke="{AMBER}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>'''
    return canvas("Демонтаж кондиционера", "Внутренний и наружный блоки сняты и отделены от трассы", body, AMBER)


def preinstall() -> str:
    body = f'''<path d="M210 650 V390 Q210 330 270 330 H650 Q690 330 710 300" fill="none" stroke="{MIST}" stroke-width="86" stroke-linecap="round" stroke-linejoin="round" opacity=".55"/>
      <path d="M175 650 V385 Q175 310 250 310 H655 Q692 310 710 298" fill="none" stroke="{DEEP}" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M210 650 V410 Q210 345 275 345 H655 Q690 345 710 312" fill="none" stroke="{DEEP}" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M245 650 V440 Q245 378 305 378 H630 Q680 378 710 323" fill="none" stroke="{AMBER}" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M710 315 C610 325 470 345 335 380 Q280 395 280 455 V650" fill="none" stroke="{TEAL}" stroke-width="15" stroke-linecap="round"/>
      {indoor_unit(710, 195, 325)}
      <circle cx="710" cy="307" r="17" fill="{TEAL}" stroke="#FFFFFF" stroke-width="5"/>'''
    return canvas("Закладка коммуникаций", "Трасса и дренаж заранее подходят к нижнему левому вводу блока", body, AMBER)


def vrf() -> str:
    units = "".join(indoor_unit(x, y, 190) for x, y in ((610, 95), (885, 95), (610, 555), (885, 555)))
    branches = "".join(
        f'''<path d="M{x-55} {main_y} L{x} {unit_y}" fill="none" stroke="{DEEP}" stroke-width="11" stroke-linecap="round"/>
          <path d="M{x-35} {main_y+25} L{x+20} {unit_y}" fill="none" stroke="{TEAL}" stroke-width="11" stroke-linecap="round"/>
          <circle cx="{x-55}" cy="{main_y}" r="9" fill="{DEEP}"/><circle cx="{x-35}" cy="{main_y+25}" r="9" fill="{TEAL}"/>'''
        for x, main_y, unit_y in ((610, 250, 180), (885, 250, 180), (610, 470, 555), (885, 470, 555))
    )
    body = f'''{outdoor_unit(145, 300, 230)}
      <path d="M375 400 H475 V250 H1025 M475 400 V470 H1025" fill="none" stroke="{DEEP}" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M375 430 H500 V275 H1025 M500 430 V495 H1025" fill="none" stroke="{TEAL}" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/>
      {branches}{units}'''
    return canvas("VRF и мультизональные системы", "Парная магистраль с разветвителями питает четыре зоны здания", body)


def server_room() -> str:
    body = f'''<rect x="565" y="180" width="300" height="420" rx="30" fill="{ICE}" stroke="{DEEP}" stroke-width="12"/>
      <path d="M620 260 H810 M620 335 H810 M620 410 H810 M620 485 H810" stroke="{DEEP}" stroke-width="9"/>
      <circle cx="790" cy="260" r="11" fill="{TEAL}"/><circle cx="790" cy="335" r="11" fill="{TEAL}"/><circle cx="790" cy="410" r="11" fill="{TEAL}"/>
      {indoor_unit(105, 145, 270)}{indoor_unit(105, 505, 270)}
      <rect x="95" y="495" width="290" height="112" rx="25" fill="none" stroke="{DEEP}" stroke-width="7" stroke-dasharray="18 14" opacity=".58"/>
      {airflow(350, 255, 545, 350)}{airflow(875, 320, 1060, 210, AMBER)}
      <path d="M245 405 C310 440 330 475 270 500" fill="none" stroke="{DEEP}" stroke-width="9" stroke-linecap="round"/>
      <path d="M245 405 l28 3 l-12 25 M270 500 l-28-3 l12-25" fill="none" stroke="{DEEP}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="510" cy="145" r="43" fill="#FFFFFF" stroke="{TEAL}" stroke-width="8"/><path d="M510 123 v27 M510 150 l20 12" stroke="{DEEP}" stroke-width="8" stroke-linecap="round"/>'''
    return canvas("Серверные и технические помещения", "Активный и резервный блоки работают по ротации, холодный и горячий потоки разделены", body, DEEP)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "installation.svg": installation(),
        "maintenance.svg": maintenance(),
        "repair.svg": repair(),
        "dismantling.svg": dismantling(),
        "preinstallation.svg": preinstall(),
        "vrf.svg": vrf(),
        "server-room.svg": server_room(),
    }
    for name, content in files.items():
        path = OUT / name
        path.write_text(content, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
