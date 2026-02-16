from typing import List, Dict

def get_auto_tags(metrics: Dict[str, any], specs: Dict[str, any] = {}) -> List[str]:
    """
    Returns a list of TAG SLUGS based on parsed metrics and specs.
    Includes only still-supported automatic tags:
    - Winter heating
    - Indoor block type (wall/ceiling/duct/cassette)

    Legacy technical tags (area-* / compressor-type) are intentionally disabled.
    """
    tags = []

    # Winter Heating Capability
    min_temp = metrics.get('min_temp_heating')
    if min_temp is not None and min_temp <= -15:
        if min_temp <= -30: tags.append("winter-30")
        elif min_temp <= -25: tags.append("winter-25")
        elif min_temp <= -20: tags.append("winter-20")
        elif min_temp <= -15: tags.append("winter-15")

    # Wall Type Check
    # 'Тип внутреннего блока' : 'настенный'
    unit_type = specs.get('Тип внутреннего блока', '').lower()
    if 'настенный' in unit_type:
        tags.append("wall")
    elif 'подпотолочный' in unit_type:
        tags.append("ceiling")
    elif 'канальный' in unit_type:
        tags.append("duct")
    elif 'кассетный' in unit_type:
        tags.append("cassette")

    return tags
