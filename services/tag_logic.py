from typing import List, Dict, Optional

def calculate_area_tag(cooling_kw: float) -> Optional[str]:
    """
    Calculates the Area Tag slug based on cooling power in kW.
    Rule: 
    < 2.4 kW -> area-20
    < 3.0 kW -> area-25
    < 4.0 kW -> area-35
    < 6.0 kW -> area-50 (Assumption based on user pattern)
    >= 6.0 kW -> area-50-plus
    """
    if cooling_kw < 2.4:
        return "area-20"
    if 2.4 <= cooling_kw < 3.0:
        return "area-25"
    if cooling_kw < 4.0:
        return "area-35"
    if cooling_kw < 6.0:
        return "area-50"
    return "area-50-plus"

def get_auto_tags(specs: Dict[str, any]) -> List[str]:
    """
    Returns a list of TAG SLUGS (not titles) based on specs.
    We need to match these slugs with database Tags.
    """
    tags = []
    
    # 1. Area based on Cooling Power
    # Check if we have pre-parsed float value, otherwise try to find in dict
    # Assuming the dict keys match what OnlinerParser produces
    
    # Note: parsers usually return 'specs' as raw text dict. 
    # But OnlinerParser extracts 'power_cooling' into target_specs transiently? 
    # Actually OnlinerParser returns 'specs' (text) and flattened generic fields. 
    # We should probably pass the extracted numeric values if available or re-parse.
    
    # Let's assume we pass the dict of extract metrics: { 'power_cooling': 2.5, 'is_inverter': True ... }
    
    if specs.get('power_cooling'):
        area_slug = calculate_area_tag(specs['power_cooling'])
        if area_slug:
            tags.append(area_slug)
            
    # 2. Inverter
    if specs.get('is_inverter'):
        tags.append("inverter")
    else:
        # If explicitly not inverter? Or just default. 
        # User data has "on-off" for non-inverter. 
        # Hard to know for sure if missing means on-off. 
        tags.append("on-off") 

    return tags
