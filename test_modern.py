import json

def _extract_type(node) -> str:
    if not isinstance(node, dict):
        return ""
    
    lower_map = {str(k).casefold(): v for k, v in node.items()}
    
    # Legacy
    if "generatorname" in lower_map:
        gn = str(lower_map["generatorname"]).lower()
        if gn == "flat": return "minecraft\\:flat"
        if gn == "largebiomes": return "minecraft\\:large_biomes"
        if gn == "amplified": return "minecraft\\:amplified"
        if gn == "default": return "minecraft\\:normal"
        
    # Modern
    wgs = lower_map.get("worldgensettings")
    if isinstance(wgs, dict):
        wgs_lower = {str(k).casefold(): v for k, v in wgs.items()}
        dims = wgs_lower.get("dimensions")
        if isinstance(dims, dict):
            dims_lower = {str(k).casefold(): v for k, v in dims.items()}
            overworld = dims_lower.get("minecraft:overworld") or dims_lower.get("overworld")
            if isinstance(overworld, dict):
                ow_lower = {str(k).casefold(): v for k, v in overworld.items()}
                
                # Check generator
                gen = ow_lower.get("generator")
                if isinstance(gen, dict):
                    gen_lower = {str(k).casefold(): v for k, v in gen.items()}
                    t = str(gen_lower.get("type", "")).lower()
                    
                    if t == "minecraft:flat" or t == "flat":
                        return "minecraft\\:flat"
                        
                    if t == "minecraft:noise" or t == "noise":
                        # Check settings
                        s = str(gen_lower.get("settings", "")).lower()
                        if "amplified" in s: return "minecraft\\:amplified"
                        if "large_biomes" in s: return "minecraft\\:large_biomes"
                        if "floating_islands" in s: return "minecraft\\:single_biome_surface"
                        
                        # Check biome_source
                        bs = gen_lower.get("biome_source", {})
                        if isinstance(bs, dict):
                            bs_lower = {str(k).casefold(): v for k, v in bs.items()}
                            p = str(bs_lower.get("preset", "")).lower()
                            if "large_biomes" in p: return "minecraft\\:large_biomes"
                            if "amplified" in p: return "minecraft\\:amplified"
                            
                        # If still nothing, it's normal
                        return "minecraft\\:normal"
                        
    for value in node.values():
        if isinstance(value, dict):
            res = _extract_type(value)
            if res: return res
    return ""

print(_extract_type({"WorldGenSettings": {"dimensions": {"minecraft:overworld": {"generator": {"type": "minecraft:noise", "biome_source": {"preset": "minecraft:large_biomes"}}}}}}))
