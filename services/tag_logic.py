from typing import List, Dict, Optional

def calculate_area_tag(cooling_kw: float) -> Optional[str]:
    """
    Calculates the Area Tag slug based on cooling power in kW.
    Rule: 
    < 2.4 kW -> area-20
    < 3.0 kW -> area-25
    < 4.0 kW -> area-35
    < 6.0 kW -> area-50
    >= 6.0 kW -> area-50-plus
    """
    if cooling_kw < 2.4:
        return "area-20"
    if 2.4 <= cooling_kw < 3.0:
        return "area-25"
    if 3.0 <= cooling_kw < 4.0:
        return "area-35"
    if 4.0 <= cooling_kw < 6.0:
        return "area-50"
    return "area-50-plus"

def get_auto_tags(metrics: Dict[str, any], specs: Dict[str, any] = {}) -> List[str]:
    """
    Returns a list of TAG SLUGS based on parsed metrics and specs.
    Includes: Area, Inverter status, Winter heating, and Type (Wall).
    """
    tags = []
    
    # 1. Area based on Cooling Power
    if metrics.get('power_cooling'):
        area_slug = calculate_area_tag(metrics['power_cooling'])
        if area_slug:
            tags.append(area_slug)
            
    # 2. Inverter Status
    if metrics.get('is_inverter'):
        tags.append("inverter")
    else:
        tags.append("on-off") 

    # 3. Winter Heating Capability
    min_temp = metrics.get('min_temp_heating')
    if min_temp is not None and min_temp <= -15:
        if min_temp <= -30: tags.append("winter-30")
        elif min_temp <= -25: tags.append("winter-25")
        elif min_temp <= -20: tags.append("winter-20")
        elif min_temp <= -15: tags.append("winter-15")

    # 4. Wall Type Check
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
